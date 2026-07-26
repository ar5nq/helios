"""
Pulls the week's economic calendar from ForexFactory's public JSON feed
(the same feed widely used by third-party FF calendar widgets/bots).
No official API/auth exists for this -- if the feed URL or format changes,
this needs updating.

Also flags "high impact" events the same way Financial Juice-style alert
tools do, so you get a heads-up before news that could blow out a signal.
"""
import requests
from datetime import datetime, timezone

FF_WEEK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

IMPACT_RANK = {"High": 3, "Medium": 2, "Low": 1, "Holiday": 0}


def fetch_week() -> list:
    resp = requests.get(FF_WEEK_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.json()


def high_impact_today(events: list, currencies: list[str] | None = None) -> list:
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


def format_alert(event: dict) -> str:
    return (f"[HIGH IMPACT] {event.get('country')} {event.get('title')} "
            f"at {event.get('date')} -- forecast {event.get('forecast')}, "
            f"previous {event.get('previous')}")
