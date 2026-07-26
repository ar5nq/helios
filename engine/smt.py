"""
ICT Smart Money Divergence (SMT): two correlated instruments (e.g. NAS100
and SP500) normally make new highs/lows together. When one makes a new
extreme and the other DOESN'T confirm it, that's smart money divergence --
often a heads-up for a reversal, since it implies one side of the "same"
trade isn't actually agreeing.

This needs TWO instruments' data aligned to the same timestamps, which is
why SMT lives as its own module rather than being just another single-symbol
indicator like the others.
"""
import pandas as pd
from .data_feed import fetch, SMT_REFERENCE


def align_pair(primary_df: pd.DataFrame, reference_df: pd.DataFrame) -> tuple:
    """Aligns two dataframes to their shared timestamps only -- different
    feeds/instruments won't have identical bar timestamps otherwise."""
    common_index = primary_df.index.intersection(reference_df.index)
    return primary_df.loc[common_index], reference_df.loc[common_index]


def _swing_points(series: pd.Series, window: int = 5, kind: str = "high") -> pd.Series:
    """Marks a bar as a swing high/low if it's the max/min within a
    centered window -- standard swing-point detection."""
    if kind == "high":
        rolling = series.rolling(window * 2 + 1, center=True).max()
    else:
        rolling = series.rolling(window * 2 + 1, center=True).min()
    return series == rolling


def detect_smt_signal(primary_df: pd.DataFrame, reference_df: pd.DataFrame,
                       window: int = 20) -> pd.Series:
    """Returns a signal series (1=bullish divergence, -1=bearish divergence, 0=none)
    aligned to primary_df's index.

    Uses rolling-window highs/lows rather than exact pivot-point matching --
    pivot matching is fragile against noise (a tiny spurious wiggle between
    two 'real' swings breaks the pairing). Comparing 'did this window's
    extreme exceed the PRIOR window's extreme' is coarser but far more
    robust and is functionally what SMT divergence means: is one instrument
    making fresh extremes while the other lags behind.

    Bearish SMT: primary's recent-window high > primary's prior-window high,
    but reference's recent-window high <= reference's prior-window high.
    Bullish SMT: mirror, using lows."""
    primary, reference = align_pair(primary_df, reference_df)
    if len(primary) < window * 2:
        return pd.Series(0, index=primary_df.index)

    p_recent_high = primary["High"].rolling(window).max()
    p_prior_high = primary["High"].rolling(window).max().shift(window)
    r_recent_high = reference["High"].rolling(window).max()
    r_prior_high = reference["High"].rolling(window).max().shift(window)

    p_recent_low = primary["Low"].rolling(window).min()
    p_prior_low = primary["Low"].rolling(window).min().shift(window)
    r_recent_low = reference["Low"].rolling(window).min()
    r_prior_low = reference["Low"].rolling(window).min().shift(window)

    bearish = (p_recent_high > p_prior_high) & (r_recent_high <= r_prior_high)
    bullish = (p_recent_low < p_prior_low) & (r_recent_low >= r_prior_low)

    sig = pd.Series(0, index=primary.index)
    sig[bearish.fillna(False)] = -1
    sig[bullish.fillna(False)] = 1
    return sig.reindex(primary_df.index, fill_value=0)


def fetch_smt_pair(symbol: str, timeframe: str):
    """Fetches a symbol and its SMT reference instrument, aligned. Returns
    (primary_df, reference_df) or raises if no reference is configured."""
    reference_symbol = SMT_REFERENCE.get(symbol)
    if reference_symbol is None:
        raise ValueError(f"No SMT reference configured for {symbol}")
    primary_df = fetch(symbol, timeframe)
    reference_df = fetch(reference_symbol, timeframe)
    return align_pair(primary_df, reference_df)


def scan_recent_divergences(primary_df: pd.DataFrame, reference_df: pd.DataFrame,
                             window: int = 5, lookback_bars: int = 200) -> list:
    """Returns a list of every SMT divergence event found in the recent
    window, for display purposes (e.g. a dashboard card per event) --
    'show all important SMTs', not just whether one is active right now."""
    sig = detect_smt_signal(primary_df, reference_df, window)
    recent = sig.tail(lookback_bars)
    events = []
    for ts, val in recent[recent != 0].items():
        events.append({
            "timestamp": str(ts),
            "type": "bullish" if val == 1 else "bearish",
            "primary_price": round(float(primary_df.loc[ts, "Close"]), 5),
        })
    return events
