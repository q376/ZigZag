"""
Minimal Telegram notifier using the raw Bot API (no async complexity needed
for one-way alert messages).
"""

import requests
import config


def send_telegram(message: str):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print(f"[telegram disabled] {message}")
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
        if resp.status_code != 200:
            print(f"[telegram error] {resp.status_code}: {resp.text}")
    except requests.RequestException as e:
        print(f"[telegram error] {e}")
