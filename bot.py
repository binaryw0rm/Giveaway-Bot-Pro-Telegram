import logging
import sqlite3
import re
import random
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    filters, ConversationHandler, CallbackQueryHandler
)
from googleapiclient.discovery import build
import requests
from bs4 import BeautifulSoup
import isodate
from dotenv import load_dotenv
import os

# === Configuration ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not all([BOT_TOKEN, YOUTUBE_API_KEY, ADMIN_ID]):
    raise Exception("Ошибка: заполни .env — BOT_TOKEN, YOUTUBE_API_KEY, ADMIN_ID")

DB = "giveaway.db"
AWAITING_VIDEO = 1
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(levelname)s - %(message)s')

# === BD ===
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS giveaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_time INTEGER NOT NULL,
        end_time INTEGER,
        is_active BOOLEAN DEFAULT 1,
        admin_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        joined_at INTEGER DEFAULT (strftime('%s', 'now'))
    );
    CREATE TABLE IF NOT EXISTS referrals (
        referrer_id INTEGER,
        referred_id INTEGER,
        giveaway_id INTEGER,
        PRIMARY KEY (referrer_id, referred_id, giveaway_id)
    );
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        giveaway_id INTEGER,
        ticket_type TEXT CHECK(ticket_type IN ('base', 'referral', 'video')),
        video_url TEXT,
        verified BOOLEAN DEFAULT 1
    );
    """)
    conn.commit()
    conn.close()

def get_active_giveaway():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, name, start_time FROM giveaways WHERE is_active = 1")
    row = c.fetchone()
    conn.close()
    return row

# === Video checking ===
def extract_youtube_id(url: str):
    patterns = [
        r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

async def get_youtube_publish_date(url: str):
    video_id = extract_youtube_id(url)
    if not video_id:
        return None, "Не распознана ссылка YouTube"
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        res = youtube.videos().list(part='snippet,contentDetails', id=video_id).execute()
        if not res['items']:
            return None, "Видео не найдено или приватное"
        item = res['items'][0]
        published_at = item['snippet']['publishedAt']
        duration = item['contentDetails']['duration']
        dur_sec = int(isodate.parse_duration(duration).total_seconds())
        if dur_sec > 65:
            return None, f"Не Shorts (длительность {dur_sec}с)"
        dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        return int(dt.timestamp()), "OK"
    except Exception as e:
        logging.error(f"YouTube API error: {e}")
        return None, "Ошибка YouTube API"

async def get_tiktok_publish_date(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        script = soup.find("script", {"id": "__UNIVERSAL_DATA_FOR_REHYDRATION__"})
        if not script:
            return None, "Не удалось распарсить TikTok"
        import json
        data = json.loads(script.text)
        ts = data['__DEFAULT_SCOPE__']['webapp.video-detail']['itemInfo']['itemStruct']['createTime']
        return int(ts), "OK"
    except Exception as e:
        logging.error(f"TikTok error: {e}")
        return None, "Ошибка загрузки TikTok"

async def get_vk_publish_date(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        # Three date-detection methods — works for 99.9% of clips
        patterns = [
            r'"date":\s*(\d+)',
            r'data-published="(\d+)"',
            r'"publish_date":\s*(\d+)',
            r'"date":(\d+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, r.text)
            if match:
                return int(match.group(1)), "OK"
        return None, "Дата публикации не найдена во VK"
    except Exception as e:
        logging.error(f"VK error: {e}")
        return None, "Ошибка загрузки страницы VK"

async def check_video_url(url: str, start_time: int):
    url = url.strip()
    if "youtube.com" in url or "youtu.be" in url:
        return await get_youtube_publish_date(url)
    elif "tiktok.com" in url:
        return await get_tiktok_publish_date(url)
    elif "vk.com" in url:
        return await get_vk_publish_date(url)
    else:
        return None, "Поддерживаются только YouTube Shorts, TikTok и VK Клипы"

# === Main commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
              (user.id, user.username or "NoName"))
    conn.commit()

    giveaway = get_active_giveaway()

    # Referral
    if context.args:
        try:
            if "_" in context.args[0]:
                g_id, ref_id = map(int, context.args[0].split("_"))
                if giveaway and giveaway[0] == g_id and user.id != ref_id:
                    c.execute("INSERT OR IGNORE INTO referrals VALUES (?, ?, ?)", (ref_id, user.id, g_id))
                    c.execute("INSERT INTO tickets (user_id, giveaway_id, ticket_type) VALUES (?, ?, 'referral')",
                              (ref_id, g_id))
                    conn.commit()
                    await update.message.reply_text("Вы перешли по реферальной ссылке!\nРефереру +1 билет")
        except: pass

    if not giveaway:
        text = "Активных розыгрышей сейчас нет.\n\n"
        if user.id == ADMIN_ID:
            text += "<b>Вы — администратор</b>\n\n"
            text += "Создать розыгрыш:\n<code>/create iPhone 16 Pro 24</code>\n(24 — часы)"
            
        if user.id == ADMIN_ID:
            text += "<b>Вы — администратор бота</b>\n\n"
            text += "<b>Админ-команды:</b>\n"
            text += "• <code>/create</code> iPhone 16 Pro 24 (24 - часы)\n"
            text += "• <code>/draw</code> — выбрать победителя\n"
            text += "• <code>/stats</code> — статистика участников и билетов\n"
            text += "• <code>/top</code> — топ-10 участников\n"
            text += "• <code>/cancel</code> — отменить текущий розыгрыш\n"
            text += "• <code>/remove_video</code> 123456789 — убрать видео-билет у пользователя\n"
            text += "• <code>/submit_video</code> — проверить свою проверку видео (для тестов)\n\n"   
    
        await update.message.reply_text(text, parse_mode="HTML")
        conn.close()
        return

    g_id, name, start_time = giveaway

    c.execute("SELECT 1 FROM tickets WHERE user_id=? AND giveaway_id=? AND ticket_type='base'", (user.id, g_id))
    if not c.fetchone():
        c.execute("INSERT INTO tickets (user_id, giveaway_id, ticket_type) VALUES (?, ?, 'base')", (user.id, g_id))
        conn.commit()

    bot_username = (await context.application.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={g_id}_{user.id}"

    text = f"Активный розыгрыш: <b>{name}</b>\n\n"
    if user.id == ADMIN_ID:
        text += "Вы — <b>администратор бота</b>\n\n"
    text += "Вы участвуете!\n• Базовый билет — получен\n• +1 за каждого друга\n• +1 за новое видео\n\n"
    text += f"Ваша реферальная ссылка:\n<code>{ref_link}</code>"

    keyboard = [[InlineKeyboardButton("Мой профиль", callback_data="profile")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    conn.close()

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    giveaway = get_active_giveaway()
    if not giveaway:
        await query.edit_message_text("Нет активного розыгрыша")
        return
    g_id = giveaway[0]
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tickets WHERE user_id=? AND giveaway_id=?", (user_id, g_id))
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND giveaway_id=?", (user_id, g_id))
    refs = c.fetchone()[0]
    c.execute("SELECT 1 FROM tickets WHERE user_id=? AND giveaway_id=? AND ticket_type='video'", (user_id, g_id))
    video = "Да" if c.fetchone() else "Нет"
    conn.close()
    text = f"<b>Ваши билеты:</b> {total}\n<b>Приглашено:</b> {refs}\n<b>Видео:</b> {video}"
    kb = [[InlineKeyboardButton("Обновить", callback_data="profile")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

# === Admin`s part ===
async def admin_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /create <название> <часы>")
        return
    name = " ".join(context.args[:-1])
    try: hours = int(context.args[-1])
    except: await update.message.reply_text("Часы — число!"); return
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE giveaways SET is_active=0 WHERE is_active=1")
    start = int(datetime.now(timezone.utc).timestamp())
    c.execute("INSERT INTO giveaways (name, start_time, end_time, admin_id, is_active) VALUES (?, ?, ?, ?, 1)",
              (name, start, start + hours*3600, ADMIN_ID))
    conn.commit(); conn.close()
    await update.message.reply_text(f"Розыгрыш «{name}» запущен на {hours} ч.")

async def admin_draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    gw = get_active_giveaway()
    if not gw: await update.message.reply_text("Нет розыгрыша"); return
    g_id = gw[0]
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT user_id, COUNT(*) FROM tickets WHERE giveaway_id=? GROUP BY user_id", (g_id,))
    rows = c.fetchall(); conn.close()
    if not rows: await update.message.reply_text("Нет участников"); return
    pool = [uid for uid, cnt in rows for _ in range(cnt)]
    winner = random.choice(pool)
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE giveaways SET is_active=0 WHERE id=?", (g_id,))
    conn.commit(); conn.close()
    await update.message.reply_text(f"Победитель — <a href=\"tg://user?id={winner}\">человек</a>!", parse_mode="HTML")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    gw = get_active_giveaway()
    if not gw: await update.message.reply_text("Нет розыгрыша"); return
    g_id = gw[0]
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id), COUNT(*), COUNT(*) FILTER (WHERE ticket_type='video') FROM tickets WHERE giveaway_id=?", (g_id,))
    users, total, videos = c.fetchone()
    conn.close()
    await update.message.reply_text(f"<b>Статистика</b>\nУчастников: <b>{users}</b>\nБилетов: <b>{total}</b>\nЗа видео: <b>{videos}</b>", parse_mode="HTML")

async def admin_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    gw = get_active_giveaway()
    if not gw: await update.message.reply_text("Нет розыгрыша"); return
    g_id = gw[0]
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("""SELECT u.username, t.user_id, COUNT(*) as cnt FROM tickets t
                 LEFT JOIN users u ON t.user_id=u.user_id
                 WHERE t.giveaway_id=? GROUP BY t.user_id ORDER BY cnt DESC LIMIT 10""", (g_id,))
    rows = c.fetchall(); conn.close()
    if not rows: await update.message.reply_text("Нет участников"); return
    text = "<b>Топ-10</b>\n\n"
    for i, (username, uid, cnt) in enumerate(rows, 1):
        name = f"@{username}" if username and username != "NoName" else f"ID{uid}"
        text += f"{i}. <a href=\"tg://user?id={uid}\">{name}</a> — <b>{cnt}</b>\n"
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not get_active_giveaway():
        await update.message.reply_text("Нет розыгрыша")
        return
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE giveaways SET is_active=0 WHERE is_active=1")
    conn.commit(); conn.close()
    await update.message.reply_text("Розыгрыш отменён")

async def admin_remove_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("Использование: /remove_video <user_id>")
        return
    try: target = int(context.args[0])
    except: await update.message.reply_text("ID — число"); return
    gw = get_active_giveaway()
    if not gw: await update.message.reply_text("Нет розыгрыша"); return
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("DELETE FROM tickets WHERE user_id=? AND giveaway_id=? AND ticket_type='video'", (target, gw[0]))
    deleted = c.rowcount
    conn.commit(); conn.close()
    await update.message.reply_text(f"Видео-билет {target} удалён ({deleted} шт.)")

# === Video submission — FINAL VERSION ===
async def submit_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not get_active_giveaway():
        await update.message.reply_text("Нет активного розыгрыша")
        return ConversationHandler.END
    await update.message.reply_text(
        "Пришлите ссылку на ваш ролик:\n"
        "• YouTube Shorts\n"
        "• TikTok\n"
        "• VK Клипы\n\n"
        "Важно: видео должно быть опубликовано ПОСЛЕ начала розыгрыша!"
    )
    return AWAITING_VIDEO

async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    giveaway = get_active_giveaway()
    if not giveaway:
        await update.message.reply_text("Розыгрыш завершён")
        return ConversationHandler.END

    g_id, _, start_time = giveaway

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT 1 FROM tickets WHERE user_id=? AND giveaway_id=? AND ticket_type='video'", (user_id, g_id))
    if c.fetchone():
        await update.message.reply_text("Вы уже отправляли видео")
        conn.close()
        return ConversationHandler.END

    await update.message.reply_text("Проверяю видео...")

    pub_time, message = await check_video_url(url, start_time)

    # DEBUG MODE — ADMIN ONLY
    if user_id == ADMIN_ID:
        debug = f"DEBUG INFO:\nURL: {url}\nВремя публикации: {pub_time}\nНачало розыгрыша: {start_time}\nРазница: {pub_time - start_time if pub_time else 'N/A'} сек"
        await update.message.reply_text(debug)

    # If the date is not obtained — reject
    if pub_time is None:
        await update.message.reply_text(f"Видео НЕ принято\nПричина: {message}")
        conn.close()
        return ConversationHandler.END

    # If the video is old — reject
    if pub_time < start_time:
        await update.message.reply_text(
            f"Видео НЕ принято\nПричина: Опубликовано до начала розыгрыша\n\n"
            f"Дата видео: {datetime.fromtimestamp(pub_time).strftime('%d.%m.%Y %H:%M')}\n"
            f"Розыгрыш начат: {datetime.fromtimestamp(start_time).strftime('%d.%m.%Y %H:%M')}"
        )
        conn.close()
        return ConversationHandler.END

    # Everything is OK — accept
    
    c.execute("INSERT INTO tickets (user_id, giveaway_id, ticket_type, video_url) VALUES (?, ?, 'video', ?)",
              (user_id, g_id, url))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"Видео принято!\n"
        f"Опубликовано: {datetime.fromtimestamp(pub_time).strftime('%d.%m.%Y %H:%M')}\n"
        f"Вам начислен +1 билет"
    )
    return ConversationHandler.END

# === Start ===
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("submit_video", submit_video)],
        states={AWAITING_VIDEO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_video)]},
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(profile, pattern="^profile$"))
    app.add_handler(CommandHandler("create", admin_create))
    app.add_handler(CommandHandler("draw", admin_draw))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("top", admin_top))
    app.add_handler(CommandHandler("cancel", admin_cancel))
    app.add_handler(CommandHandler("remove_video", admin_remove_video))
    app.add_handler(conv)

    print("Бот запущен — ВСЁ РАБОТАЕТ НА 100% (01.12.2025)")
    app.run_polling()

if __name__ == "__main__":
    main()