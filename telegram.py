"""Envío de mensajes a Telegram."""
import os

import requests


def enviar(texto):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("[Telegram no configurado] Mensaje:\n" + texto + "\n")
        return False
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": texto, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=20,
    )
    if r.status_code != 200:
        print(f"Error de Telegram {r.status_code}: {r.text[:300]}")
        return False
    return True
