"""
Pulls the week's economic calendar from ForexFactory's public JSON feed
(the same feed widely used by third-party FF calendar widgets/bots).
No official API/auth exists for this -- if the feed URL or format changes,
this needs updating.

Also flags "high impact" events the same way Financial Juice-style alert
tools do, so you get a heads-up before news that could blow out a signal.
"""
from typing import Optional, List
import requests
from datetime import datetime, timezone

FF_WEEK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

IMPACT_RANK = {"High": 3, "Medium": 2, "Low": 1, "Holiday": 0}


def fetch_week() -> list:
    resp = requests.get(FF_WEEK_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.json()


def high_impact_today(events: list, currencies: Optional[List[str]] = None) -> list:
    today = datetime.now(timezone.utc).date()
    out = []
    for e in events:
        try:
            ev_date = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).date()
        except Exception:
            continue
        if ev_date != today:
            continue
        if e.get("impact") != "High":
            continue
        if currencies and e.get("country") not in currencies:
            continue
        out.append(e)
    return out


# ForexFactory's own color scheme: red=High, orange=Medium, yellow=Low.
# Prop firms commonly phrase their news-trading rules the same way
# ("no red news", "yellow is fine") -- so filtering by color name matches
# how you'd actually think about it, not just the raw impact string.
COLOR_TO_MIN_IMPACT = {"red": "High", "orange": "Medium", "yellow": "Low"}


def upcoming_by_color(events: list, color: str = "red",
                       currencies: Optional[List[str]] = None) -> list:
    """color: 'red' (High only), 'orange' (Medium+High), 'yellow' (Low+Medium+High).
    Returns everything from now through the rest of the feed's window, soonest first."""
    min_impact = COLOR_TO_MIN_IMPACT.get(color, "High")
    return high_impact_upcoming(events, currencies=currencies, min_impact=min_impact)


def high_impact_upcoming(events: list, currencies: Optional[List[str]] = None,
                          min_impact: str = "High") -> list:
    """Every event from right now through the rest of the feed's window
    (the FF feed itself only covers 'this week', so this returns the rest
    of the current week, not a rolling N days), sorted soonest-first.
    min_impact: 'High' or 'Medium' or 'Low' -- lower thresholds include
    everything above them too."""
    now = datetime.now(timezone.utc)
    min_rank = IMPACT_RANK.get(min_impact, 3)

    out = []
    for e in events:
        try:
            ev_time = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        if ev_time < now:
            continue  # already passed
        if IMPACT_RANK.get(e.get("impact"), 0) < min_rank:
            continue
        if currencies and e.get("country") not in currencies:
            continue
        out.append(e)

    out.sort(key=lambda e: e["date"])
    return out


def format_alert(event: dict) -> str:
    color_by_impact = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}
    dot = color_by_impact.get(event.get("impact"), "⚪")
    return (f"{dot} [{event.get('impact')}] {event.get('country')} {event.get('title')} "
            f"at {event.get('date')} -- forecast {event.get('forecast')}, "
            f"previous {event.get('previous')}")
