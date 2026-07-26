"""
ICT-style killzones: specific session windows where price action is
considered higher-probability to trade, vs the dead zones between them.

Times are in America/New_York local time (handles DST automatically via
zoneinfo), since that's the convention ICT killzones are normally quoted in.
"""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")

# (start_hour, start_min, end_hour, end_min) in ET. "asian" wraps past midnight.
KILLZONES = {
    "asian": (20, 0, 0, 0),          # 8:00 PM - 12:00 AM ET
    "london": (2, 0, 5, 0),          # 2:00 AM - 5:00 AM ET
    "ny_am": (7, 0, 10, 0),          # 7:00 AM - 10:00 AM ET
    "london_close": (10, 0, 12, 0),  # 10:00 AM - 12:00 PM ET
}


def _in_window(now_time, start_h, start_m, end_h, end_m) -> bool:
    start = (start_h, start_m)
    end = (end_h, end_m)
    now = (now_time.hour, now_time.minute)
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # wraps past midnight (asian killzone)


def current_killzone(now_utc: Optional[datetime] = None) -> Optional[str]:
    """Returns the name of the killzone we're currently in, or None if
    we're in a dead zone between sessions."""
    now_utc = now_utc or datetime.now(ZoneInfo("UTC"))
    now_et = now_utc.astimezone(NY_TZ)
    for name, (sh, sm, eh, em) in KILLZONES.items():
        if _in_window(now_et, sh, sm, eh, em):
            return name
    return None


def is_in_any_killzone(now_utc: Optional[datetime] = None) -> bool:
    return current_killzone(now_utc) is not None
