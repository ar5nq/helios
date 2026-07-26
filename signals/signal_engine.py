"""
Instead of exporting to MT5, a promoted genome becomes a SIGNAL SOURCE.
Each time its rule condition fires on the latest bar, a signal is logged here.
The user marks it: taken/skipped, then later: win/loss.

This log is what re-scores the strategy over time (decay detection),
same spirit as the MT5 version, minus any auto-execution.
"""
import json
import os
import uuid
from datetime import datetime, timezone

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "signal_log.json")


def _load() -> list:
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH) as f:
            return json.load(f)
    return []


def _save(log: list):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def emit_signal(genome_id: str, symbol: str, timeframe: str, direction: str,
                 entry: float, stop: float, target: float, note: str = "") -> dict:
    """Create a new pending signal. direction is 'BUY' or 'SELL'."""
    log = _load()
    signal = {
        "id": uuid.uuid4().hex[:8].upper(),
        "genome_id": genome_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "note": note,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "taken": None,       # True / False / None (undecided)
        "outcome": None,     # "WIN" / "LOSS" / "BREAKEVEN" / None
        "closed_at": None,
    }
    log.append(signal)
    _save(log)
    return signal


def mark_taken(signal_id: str, taken: bool) -> dict:
    log = _load()
    for s in log:
        if s["id"] == signal_id:
            s["taken"] = taken
            _save(log)
            return s
    raise ValueError(f"No signal with id {signal_id}")


def report_outcome(signal_id: str, outcome: str) -> dict:
    """outcome: 'WIN', 'LOSS', or 'BREAKEVEN' -- reported by the user regardless
    of whether they took the trade, so decay tracking stays accurate."""
    assert outcome in ("WIN", "LOSS", "BREAKEVEN")
    log = _load()
    for s in log:
        if s["id"] == signal_id:
            s["outcome"] = outcome
            s["closed_at"] = datetime.now(timezone.utc).isoformat()
            _save(log)
            return s
    raise ValueError(f"No signal with id {signal_id}")


def list_signals(pending_only: bool = True) -> list:
    """pending_only=True: signals that don't yet have BOTH taken and outcome set.
    You can still record an outcome even if taken=False (a signal you skipped
    but want to track hypothetically), so 'pending' here just means either
    field is still unanswered."""
    log = _load()
    if not pending_only:
        return log
    return [s for s in log if s["taken"] is None or s["outcome"] is None]


def genome_live_stats(genome_id: str) -> dict:
    """Live (post-vault) win rate for a genome, based on reported outcomes only."""
    log = _load()
    closed = [s for s in log if s["genome_id"] == genome_id and s["outcome"] is not None]
    wins = sum(1 for s in closed if s["outcome"] == "WIN")
    total = len(closed)
    return {
        "genome_id": genome_id,
        "closed_signals": total,
        "wins": wins,
        "live_win_rate": round(100 * wins / total, 1) if total else None,
    }
