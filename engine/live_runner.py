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

from .data_feed import fetch, SMT_REFERENCE
from .backtest import latest_signal
from .killzones import current_killzone, is_in_any_killzone
from .active_strategies import get_active
from signals.signal_engine import emit_signal
from news.calendar_feed import fetch_week, high_impact_today, format_alert
from notifications.telegram import send_message, format_signal_message, format_news_message

VAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "vault.json")
STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "runner_state.json")

POLL_SECONDS = 60 * 15  # check every 15 minutes; adjust to your fastest timeframe
ENFORCE_KILLZONES = True  # only fire signals during ICT killzone session windows


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
    """Runs one pass over the vault. Returns any new signals fired.

    Multiple vaulted genomes can have different DNA but happen to trade
    identically on this data (e.g. a filter gene that never actually
    binds on this window) -- see the M5/H1 batches where several distinct
    genome ids had byte-identical backtest stats. Left ungrouped, that
    produces 4+ near-duplicate Telegram alerts for what is functionally
    one trade idea. So: group same-bar fires by (symbol, timeframe,
    direction, rounded entry) and send ONE alert per group, listing every
    genome id that agreed."""
    vault = _load_json(VAULT_PATH, [])
    state = _load_json(STATE_PATH, {"last_bar_alerted": {}, "news_alerted": []})
    fired = []

    if ENFORCE_KILLZONES and not is_in_any_killzone():
        return fired  # outside Asian/London/NY session windows -- don't fire

    active_ids = set(get_active())
    if not active_ids:
        return fired  # nothing activated yet -- stay silent rather than fire everything at once

    vault = [g for g in vault if g["id"] in active_ids]

    candidates = []  # (entry_dict, sig_dict) pairs that fired this cycle
    for entry in vault:
        genome_id = entry["id"]
        symbol, timeframe = entry["symbol"], entry["timeframe"]
        try:
            df = fetch(symbol, timeframe)
            reference_df = None
            if entry.get("signal_indicator") == "SMT":
                ref_symbol = SMT_REFERENCE.get(symbol)
                if ref_symbol:
                    reference_df = fetch(ref_symbol, timeframe)
            sig = latest_signal(df, entry, reference_df)
        except Exception:
            print(f"[warn] failed to check genome {genome_id}: {traceback.format_exc()}")
            continue

        if sig["is_stale"]:
            continue  # market closed / no real trading in this bar -- don't fire on dead data

        if sig["direction"] is None:
            continue

        already_alerted = state["last_bar_alerted"].get(genome_id) == sig["bar_time"]
        if already_alerted:
            continue

        candidates.append((entry, sig))

    # group by what the trade actually looks like, not by which genome found it
    groups = {}
    for entry, sig in candidates:
        key = (entry["symbol"], entry["timeframe"], sig["direction"], round(sig["entry"], 2))
        groups.setdefault(key, []).append((entry, sig))

    for (symbol, timeframe, direction, entry_price), members in groups.items():
        # pick the highest-fitness genome in the group as the representative
        # for stop/target sizing (their sig dicts may differ slightly on
        # stop distance depending on exec_mode)
        members.sort(key=lambda m: m[0].get("score", {}).get("fitness", 0), reverse=True)
        rep_entry, rep_sig = members[0]
        genome_ids = [e["id"] for e, _ in members]
        killzone = current_killzone() or "unknown"

        note_parts = [f"{killzone} killzone"]
        if len(genome_ids) > 1:
            note_parts.append(f"confirmed by {len(genome_ids)} genome(s): {', '.join(genome_ids)}")

        signal = emit_signal(
            genome_id=rep_entry["id"], symbol=symbol, timeframe=timeframe,
            direction=direction, entry=rep_sig["entry"],
            stop=rep_sig["stop"], target=rep_sig["target"],
            note=" | ".join(note_parts),
        )
        fired.append(signal)

        for e, s in members:
            state["last_bar_alerted"][e["id"]] = s["bar_time"]

        if notify:
            try:
                msg = format_signal_message(signal)
                if len(genome_ids) > 1:
                    msg += f"\n(agreed by {len(genome_ids)} vaulted genomes)"
                send_message(msg)
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
