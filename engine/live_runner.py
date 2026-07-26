"""
Polls every vaulted genome on a schedule. When a genome's rule condition
fires on a NEW completed bar (not one it already alerted on), it:
  1. logs a signal via signals.signal_engine.emit_signal
  2. sends a Telegram alert
  3. also checks for today's high-impact news and alerts on those (once per event)

Run continuously with:
  python -m engine.live_runner

State (which bars/news already alerted on) is kept in data/runner_state.json
so restarting the script doesn't spam duplicate alerts.
"""
import json
import os
import time
import traceback

from .data_feed import fetch
from .backtest import latest_signal
from signals.signal_engine import emit_signal
from news.calendar_feed import fetch_week, high_impact_today, format_alert
from notifications.telegram import send_message, format_signal_message, format_news_message

VAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "vault.json")
STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "runner_state.json")

POLL_SECONDS = 60 * 15  # check every 15 minutes; adjust to your fastest timeframe


def _load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def check_genomes_once(notify: bool = True) -> list:
    """Runs one pass over the vault. Returns any new signals fired."""
    vault = _load_json(VAULT_PATH, [])
    state = _load_json(STATE_PATH, {"last_bar_alerted": {}, "news_alerted": []})
    fired = []

    for entry in vault:
        genome_id = entry["id"]
        symbol, timeframe = entry["symbol"], entry["timeframe"]
        try:
            df = fetch(symbol, timeframe)
            sig = latest_signal(df, entry)
        except Exception:
            print(f"[warn] failed to check genome {genome_id}: {traceback.format_exc()}")
            continue

        if sig["direction"] is None:
            continue

        already_alerted = state["last_bar_alerted"].get(genome_id) == sig["bar_time"]
        if already_alerted:
            continue

        signal = emit_signal(
            genome_id=genome_id, symbol=symbol, timeframe=timeframe,
            direction=sig["direction"], entry=sig["entry"],
            stop=sig["stop"], target=sig["target"],
        )
        fired.append(signal)
        state["last_bar_alerted"][genome_id] = sig["bar_time"]

        if notify:
            try:
                send_message(format_signal_message(signal))
            except Exception as e:
                print(f"[warn] telegram send failed: {e}")

    _save_json(STATE_PATH, state)
    return fired


def check_news_once(notify: bool = True) -> list:
    state = _load_json(STATE_PATH, {"last_bar_alerted": {}, "news_alerted": []})
    try:
        events = fetch_week()
    except Exception as e:
        print(f"[warn] news fetch failed: {e}")
        return []

    alerts = high_impact_today(events)
    new_alerts = []
    for e in alerts:
        key = f"{e.get('title')}_{e.get('date')}"
        if key in state["news_alerted"]:
            continue
        new_alerts.append(e)
        state["news_alerted"].append(key)
        if notify:
            try:
                send_message(format_news_message(e))
            except Exception as ex:
                print(f"[warn] telegram send failed: {ex}")

    _save_json(STATE_PATH, state)
    return new_alerts


def run_forever():
    print(f"Helios live runner started. Polling every {POLL_SECONDS}s.")
    while True:
        fired = check_genomes_once()
        news = check_news_once()
        if fired:
            print(f"[{time.strftime('%H:%M:%S')}] fired {len(fired)} new signal(s)")
        if news:
            print(f"[{time.strftime('%H:%M:%S')}] {len(news)} new high-impact news alert(s)")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_forever()
