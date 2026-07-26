"""
Sends messages to your Telegram via a bot you control.

One-time setup (you do this once, in the Telegram app):
  1. Message @BotFather -> /newbot -> follow prompts -> it gives you a BOT TOKEN
  2. Message your new bot anything (e.g. "hi") so it can find your chat
  3. Visit https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates in a browser
     -> find "chat":{"id": 123456789, ...} -> that number is your CHAT_ID
  4. Put both in a .env file (see .env.example) -- never commit real secrets to git
"""
import os
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str, token: str | None = None, chat_id: str | None = None) -> dict:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID. "
            "Set them as environment variables or a .env file -- see notifications/README.md"
        )

    url = TELEGRAM_API.format(token=token)
    resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def format_signal_message(signal: dict) -> str:
    return (
        f"🚨 SIGNAL: {signal['direction']} {signal['symbol']} ({signal['timeframe']})\n"
        f"Entry: {signal['entry']}  Stop: {signal['stop']}  Target: {signal['target']}\n"
        f"Genome: {signal['genome_id']}\n"
        f"id: {signal['id']}"
    )


def format_news_message(event: dict) -> str:
    return (
        f"📰 HIGH IMPACT: {event.get('country')} {event.get('title')}\n"
        f"Time: {event.get('date')}\n"
        f"Forecast: {event.get('forecast')}  Previous: {event.get('previous')}"
    )
