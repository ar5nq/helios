"""
Opening Range Breakout (ORB) and a specific ICT-style variant:
  1. Mark the high/low of a defined session window (default 8:12-9:12 ET)
  2. Watch which side gets swept first (buy-side = above the range high,
     sell-side = below the range low)
  3. Once swept, wait for a CISD (Change in State of Delivery) -- price
     closing back through a short-term structure point in the OPPOSITE
     direction of the sweep
  4. Enter in that reverse direction

All times are in America/New_York, same convention as engine/killzones.py.
"""
from datetime import time
from typing import Optional
import pandas as pd
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")


def _to_et(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(NY_TZ)
    return df


def compute_daily_orb(df: pd.DataFrame, start: tuple = (8, 12), end: tuple = (9, 12)) -> pd.DataFrame:
    """Returns a DataFrame indexed by calendar date (ET) with columns
    or_high, or_low for each day's opening range window."""
    df_et = _to_et(df)
    start_t, end_t = time(*start), time(*end)
    mask = (df_et.index.time >= start_t) & (df_et.index.time < end_t)
    window = df_et[mask]
    if window.empty:
        return pd.DataFrame(columns=["or_high", "or_low"])

    daily = window.groupby(window.index.date).agg(or_high=("High", "max"), or_low=("Low", "min"))
    return daily


def detect_orb_breakout(df: pd.DataFrame, start: tuple = (8, 12), end: tuple = (9, 12)) -> pd.Series:
    """Simple ORB: fires once per day when price closes beyond that day's
    opening-range high (long) or low (short), after the window has closed."""
    df_et = _to_et(df)
    daily_orb = compute_daily_orb(df, start, end)
    end_t = time(*end)

    sig = pd.Series(0, index=df.index)
    fired_today = set()

    for i, (ts, row) in enumerate(df_et.iterrows()):
        date = ts.date()
        if ts.time() < end_t or date not in daily_orb.index:
            continue
        if date in fired_today:
            continue
        or_high, or_low = daily_orb.loc[date, "or_high"], daily_orb.loc[date, "or_low"]
        if row["Close"] > or_high:
            sig.iloc[i] = 1
            fired_today.add(date)
        elif row["Close"] < or_low:
            sig.iloc[i] = -1
            fired_today.add(date)

    return sig


def detect_orb_liquidity_cisd(df: pd.DataFrame, start: tuple = (8, 12), end: tuple = (9, 12),
                               cisd_lookback: int = 6) -> pd.Series:
    """Your specific strategy:
    1. After the ORB window, watch for one side to get swept (price trades
       beyond the range high OR low -- whichever happens FIRST that day).
    2. Once swept, watch the next `cisd_lookback` bars for a CISD: price
       closing back through the most recent short-term swing point in the
       OPPOSITE direction of the sweep (a structural shift).
    3. Fire in the REVERSE direction of the original sweep."""
    df_et = _to_et(df)
    daily_orb = compute_daily_orb(df, start, end)
    end_t = time(*end)

    sig = pd.Series(0, index=df.index)
    day_state = {}  # date -> {'swept': 'buy'/'sell'/None, 'swept_at': int, 'sweep_price': float}

    close = df_et["Close"]

    for i, (ts, row) in enumerate(df_et.iterrows()):
        date = ts.date()
        if ts.time() < end_t or date not in daily_orb.index:
            continue

        state = day_state.setdefault(date, {"swept": None, "swept_at": None})
        or_high, or_low = daily_orb.loc[date, "or_high"], daily_orb.loc[date, "or_low"]

        if state["swept"] is None:
            if row["High"] > or_high:
                state["swept"] = "buy"     # buy-side liquidity taken -> expect reversal DOWN
                state["swept_at"] = i
            elif row["Low"] < or_low:
                state["swept"] = "sell"    # sell-side liquidity taken -> expect reversal UP
                state["swept_at"] = i
            continue

        # already swept -- look for CISD within the lookback window
        bars_since_sweep = i - state["swept_at"]
        if bars_since_sweep <= 0 or bars_since_sweep > cisd_lookback:
            continue

        recent_structure = close.iloc[max(0, i - cisd_lookback):i]
        if recent_structure.empty:
            continue

        if state["swept"] == "buy":
            # CISD down: price closes below the lowest close since the sweep
            if row["Close"] < recent_structure.min():
                sig.iloc[i] = -1  # reverse of the buy-side sweep = short
                state["swept"] = "done"
        elif state["swept"] == "sell":
            # CISD up: price closes above the highest close since the sweep
            if row["Close"] > recent_structure.max():
                sig.iloc[i] = 1  # reverse of the sell-side sweep = long
                state["swept"] = "done"

    return sig
