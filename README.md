# Giveaway Bot Pro – Professional Telegram Giveaway Bot
**Version:** 1.0 · **Author:** @binaryw0rm · **Ready for 10 000+ participants**

The powerful, cheat-proof giveaway bot for Telegram channels.  
Referral system · Strict video verification by publish date · Full admin panel · Runs 24/7 with auto-restart.

Used by top channels | 100 % protected from cheating | Zero downtime

---

## Features

| Feature                         | Description                                                                 |
|---------------------------------|-----------------------------------------------------------------------------|
| Referral system                 | +1 ticket for every invited friend                                          |
| Video verification by date      | Only videos published AFTER the giveaway start are accepted                 |
| 3 supported platforms          | YouTube Shorts · TikTok · VK Clips                                          |
| Anti-cheat protection           | Checks Shorts duration, publish date, blocks old videos                     |
| Full statistics                 | Participants, total tickets, video tickets, top-10                          |
| Admin panel                     | Create/cancel giveaway, draw winner, remove video tickets, stats, top      |
| Auto-restart (systemd)          | Bot survives crashes, reboots, updates                                      |
| Admin debug                     | You see exact timestamps of video publication and giveaway start           |

---

## Requirements (exact versions used)

```
Python 3.11+
python-telegram-bot==21.5
google-api-python-client
python-dotenv
beautifulsoup4
isodate
requests
```
---

Install everything in one command:

```
pip install python-telegram-bot==21.5 google-api-python-client python-dotenv beautifulsoup4 isodate requests
```
## Configuration (.env)

Create .env in the project root:

```
BOT_TOKEN=YOUR_TOKEN
YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY
ADMIN_ID=YOUR_OR_ADMIN_ID
```

YouTube Data API v3 key – free: https://console.cloud.google.com/apis/credentials

Enable “YouTube Data API v3”.

Create API_KEY in Credentials (you have to set up restrictions for KEY)

---

## Project files

```
giveaway_bot/
  ├── bot.py              ← main code (perfect, don’t touch)
  ├── giveaway.db         ← database (created automatically)
  ├── .env                ← your tokens
  ├── requirements.txt    ← dependencies
  ├── giveaway_bot.service ← systemd service (24/7 + auto-restart)
  └── README.md           ← this file
```
---

## Deploy on VPS – the bot will never die

1. Create systemd service (auto-restart on crash/reboot)

```
sudo nano /etc/systemd/system/giveaway_bot.service
```
Paste:

```
ini

[Unit]
Description=Giveaway Bot Pro – Telegram Giveaway Bot 24/7
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/giveaway_bot
ExecStart=/root/giveaway_bot/venv/bin/python /root/giveaway_bot/bot.py
Restart=always
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=giveaway_bot

[Install]
WantedBy=multi-user.target
```
Enable & start:

```
sudo systemctl daemon-reload
sudo systemctl enable giveaway_bot.service
sudo systemctl start giveaway_bot.service
```

Check status / logs:

```
sudo systemctl status giveaway_bot.service
journalctl -u giveaway_bot.service -f
```

Bot restarts automatically on crash, server reboot, Python errors, etc.
---

## Admin commands (shown automatically in /start)

```
/create iPhone 16 Pro Max 48    – start giveaway (name + hours)
/draw                           – pick winner
/stats                          – full statistics
/top                            – top-10 participants
/cancel                         – cancel current giveaway
/remove_video 123456789         – remove video ticket from user
/submit_video                   – submit video (for participants and your tests)
```
---

## Screenshots

<p align="center">
  <table>
    <tr>
      <td><img src="https://github.com/binaryw0rm/Giveaway-Bot-Pro-Telegram/blob/main/image1.JPG?raw=true" width="250"></td>
      <td><img src="https://github.com/binaryw0rm/Giveaway-Bot-Pro-Telegram/blob/main/image2.JPG?raw=true" width="250"></td>
      <td><img src="https://github.com/binaryw0rm/Giveaway-Bot-Pro-Telegram/blob/main/image3.JPG?raw=true" width="250"></td>
    </tr>
  </table>
</p>


---

## Tips for a massive giveaway

### First create a 1-hour test giveaway → make sure everything works
### Use emojis in the name: /create iPhone 16 Pro Max 168
### Pin the bot in your channel
### Add to channel description: “Giveaway here → @YourBotUsername”
### Encourage video submissions: “Post a Short/TikTok – get +1 ticket!”

---

## License & Author

© 2025 

Free for personal use | Do not resell as your own product

Ready for 50 000+ participants

Reliable as Swiss watches

Beautiful as iPhone

Launch it and watch thousands of participants pour in!

Any questions – @binaryw0rm
