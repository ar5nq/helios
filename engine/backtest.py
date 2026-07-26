"""
Backtests a strategy genome against OHLC price data.
Splits data into TRAIN (in-sample, what the genome was bred on)
and TEST (out-of-sample, unseen) -- mirrors "Only survivors ship."

A genome is only promoted if it performs on TEST data too, not just TRAIN.
"""
import numpy as np
import pandas as pd


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _detect_fvg_signal(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """ICT Fair Value Gap: a bullish FVG is a 3-candle imbalance where
    candle[i-2].High < candle[i].Low (price left a gap on the way up).
    Bearish is the mirror. A gap usually isn't tapped on the same bar it
    forms -- price fills it on some LATER bar -- so we track open gaps and
    check every subsequent bar within `lookback` for a tap back into one."""
    high, low, close = df["High"], df["Low"], df["Close"]
    sig = pd.Series(0, index=df.index)

    bull_gaps = []  # list of (formed_at_index, bottom, top)
    bear_gaps = []

    for i in range(2, len(df)):
        # a new bullish gap forms using candles (i-2, i-1, i)
        if high.iloc[i - 2] < low.iloc[i]:
            bull_gaps.append((i, high.iloc[i - 2], low.iloc[i]))
        if low.iloc[i - 2] > high.iloc[i]:
            bear_gaps.append((i, high.iloc[i], low.iloc[i - 2]))

        # drop gaps too old to matter
        bull_gaps = [g for g in bull_gaps if i - g[0] <= lookback]
        bear_gaps = [g for g in bear_gaps if i - g[0] <= lookback]

        # check if the CURRENT close taps into any open gap (but not the
        # bar it was formed on, since that's the impulse move itself)
        c = close.iloc[i]
        for formed_at, bottom, top in bull_gaps:
            if formed_at != i and bottom <= c <= top:
                sig.iloc[i] = 1
                break
        if sig.iloc[i] == 0:
            for formed_at, bottom, top in bear_gaps:
                if formed_at != i and bottom <= c <= top:
                    sig.iloc[i] = -1
                    break

    return sig


def _detect_ote_signal(df: pd.DataFrame, swing_window: int = 20) -> pd.Series:
    """ICT Optimal Trade Entry: find the most recent swing (rolling high to
    rolling low, or vice versa) and check if price has retraced into the
    61.8%-79% Fibonacci zone of that swing -- the 'OTE zone' -- while the
    swing direction is still intact."""
    high, low, close = df["High"], df["Low"], df["Close"]
    swing_high = high.rolling(swing_window).max()
    swing_low = low.rolling(swing_window).min()
    swing_range = swing_high - swing_low

    # if the swing's high came after its low, it's an up-swing (retracement = pullback down into OTE for a long)
    up_swing = high.rolling(swing_window).apply(lambda w: w.argmax(), raw=True) > \
        low.rolling(swing_window).apply(lambda w: w.argmin(), raw=True)

    ote_top_long = swing_high - swing_range * 0.618
    ote_bottom_long = swing_high - swing_range * 0.79
    ote_top_short = swing_low + swing_range * 0.79
    ote_bottom_short = swing_low + swing_range * 0.618

    sig = pd.Series(0, index=df.index)
    long_zone = (close <= ote_top_long) & (close >= ote_bottom_long) & up_swing
    short_zone = (close >= ote_bottom_short) & (close <= ote_top_short) & (~up_swing)
    sig[long_zone.fillna(False)] = 1
    sig[short_zone.fillna(False)] = -1
    return sig


def _macd_line(close: pd.Series, period: int) -> tuple:
    fast = max(2, period // 2)
    slow = period
    signal_span = max(2, period // 4)
    macd = close.ewm(span=fast).mean() - close.ewm(span=slow).mean()
    signal = macd.ewm(span=signal_span).mean()
    return macd, signal


def _bollinger_bands(close: pd.Series, period: int, threshold: float) -> tuple:
    ma = close.rolling(period).mean()
    std = close.rolling(period).std()
    width = 1.0 + threshold * 2  # threshold widens/narrows the bands
    return ma + width * std, ma - width * std


def _cci(df: pd.DataFrame, period: int) -> pd.Series:
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    ma = typical.rolling(period).mean()
    mean_dev = (typical - ma).abs().rolling(period).mean()
    return (typical - ma) / (0.015 * mean_dev.replace(0, np.nan))


def _williams_r(df: pd.DataFrame, period: int) -> pd.Series:
    highest_high = df["High"].rolling(period).max()
    lowest_low = df["Low"].rolling(period).min()
    return (highest_high - df["Close"]) / (highest_high - lowest_low).replace(0, np.nan) * -100


def _raw_signal(df: pd.DataFrame, genome: dict, reference_df: pd.DataFrame = None) -> pd.Series:
    """The primary entry trigger, before bias/filter gating.
    Every indicator has its own genuinely distinct formula -- no shared
    generic fallback, so 'MACD' and 'CCI' genomes actually trade differently."""
    period = genome["signal_params"]["period"]
    threshold = genome["signal_params"]["threshold"]
    close = df["Close"]
    indicator = genome["signal_indicator"]

    if indicator == "RSI":
        rsi = _rsi(close, period)
        long = rsi < (30 * (1 + (0.5 - threshold)))
        short = rsi > (70 * (1 + (threshold - 0.5)))

    elif indicator in ("SMA", "EMA"):
        ma = close.rolling(period).mean() if indicator == "SMA" else close.ewm(span=period).mean()
        long = close > ma
        short = close < ma

    elif indicator == "MACD":
        macd, signal = _macd_line(close, period)
        long = macd > signal
        short = macd < signal

    elif indicator == "ATR":
        # volatility breakout: long/short when price moves further than
        # threshold x ATR from the prior close
        atr = _atr(df, period)
        move = close.diff()
        long = move > atr * threshold * 2
        short = move < -atr * threshold * 2

    elif indicator == "BOLLINGER":
        upper, lower = _bollinger_bands(close, period, threshold)
        long = close > upper   # breakout above the band
        short = close < lower  # breakout below the band

    elif indicator == "CCI":
        cci = _cci(df, period)
        band = 100 * (1 + threshold)
        long = cci < -band   # oversold -> mean-reversion long
        short = cci > band   # overbought -> mean-reversion short

    elif indicator == "WILLIAMS_R":
        wr = _williams_r(df, period)
        oversold = -80 - threshold * 15
        overbought = -20 + threshold * 15
        long = wr < oversold
        short = wr > overbought

    elif indicator == "FVG":
        raw = _detect_fvg_signal(df)
        long = raw == 1
        short = raw == -1

    elif indicator == "OTE":
        raw = _detect_ote_signal(df, swing_window=max(10, period))
        long = raw == 1
        short = raw == -1

    elif indicator == "SMT":
        if reference_df is None:
            raise ValueError("SMT indicator requires reference_df (a correlated instrument)")
        from .smt import detect_smt_signal
        raw = detect_smt_signal(df, reference_df, window=max(10, period))
        long = raw == 1
        short = raw == -1

    else:
        raise ValueError(f"Unknown signal_indicator: {indicator}")

    sig = pd.Series(0, index=df.index)
    sig[long.fillna(False)] = 1
    sig[short.fillna(False)] = -1
    return sig


def _apply_bias(sig: pd.Series, df: pd.DataFrame, genome: dict) -> pd.Series:
    """Bias gene: only allow signals that agree with a higher-timeframe trend
    direction. This is what 'bias' is supposed to mean -- a macro trend filter
    the entry signal has to agree with, not just cosmetic metadata."""
    bias = genome.get("bias", "NONE")
    close = df["Close"]

    if bias == "HTF_TREND":
        trend_ma = close.rolling(50).mean()
        trend_up = close > trend_ma
    elif bias == "TRAILING":
        # trend defined by a slower-moving trailing average -- catches
        # established trends rather than every short-term crossover
        trend_ma = close.ewm(span=100).mean()
        trend_up = close > trend_ma
    else:  # NONE
        return sig

    gated = sig.copy()
    gated[(sig == 1) & (~trend_up)] = 0
    gated[(sig == -1) & (trend_up)] = 0
    return gated


def _apply_filter(sig: pd.Series, df: pd.DataFrame, genome: dict) -> pd.Series:
    """Filter gene: a condition that must hold for a trade to be taken at all,
    independent of direction (volatility regime, choppiness, RSI extremes)."""
    filt = genome.get("filter", "NONE")
    close = df["Close"]

    if filt == "ATR_REGIME":
        atr = _atr(df, 14)
        allow = atr > atr.rolling(50).median()
    elif filt == "CHOP":
        volatility = close.pct_change().rolling(14).std()
        allow = volatility < volatility.rolling(50).median()  # avoid choppy/sideways stretches
    elif filt == "RSI_RANGE":
        rsi = _rsi(close, 14)
        allow = (rsi > 25) & (rsi < 75)  # avoid already-exhausted extremes
    else:  # NONE
        return sig

    gated = sig.copy()
    gated[~allow.fillna(False)] = 0
    return gated


def _signal_series(df: pd.DataFrame, genome: dict, reference_df: pd.DataFrame = None) -> pd.Series:
    """Full signal pipeline: raw entry trigger -> bias gate -> filter gate.
    All three genome genes now genuinely change trading behavior."""
    sig = _raw_signal(df, genome, reference_df)
    sig = _apply_bias(sig, df, genome)
    sig = _apply_filter(sig, df, genome)
    return sig


def latest_signal(df: pd.DataFrame, genome: dict, reference_df: pd.DataFrame = None) -> dict:
    """Returns the signal direction on the most recent CONFIRMED (closed) bar,
    plus entry/stop/target sized according to the genome's exec_mode and rr.
    Used by the live runner to decide whether to emit a new signal.

    Deliberately drops the very last row before deciding anything: intraday
    feeds (including this one, right at a weekly market reopen) often return
    a still-forming candle as the last row, whose values can keep shifting
    between polls -- evaluating it causes duplicate/unstable signals. Trading
    systems generally only act on bars that have actually closed."""
    df = df.dropna()
    if len(df) < 2:
        return {
            "direction": None, "entry": None, "stop": None, "target": None,
            "bar_time": None, "is_stale": True,
        }
    df = df.iloc[:-1]  # drop the still-forming candle; work only with closed bars

    last = df.iloc[-1]
    # A genuinely traded bar almost never has zero intrabar range. A closed/stale
    # market (e.g. weekend futures close) often gets padded with a flat repeated
    # price instead. Volume alone doesn't work universally -- FX pairs from Yahoo
    # report Volume=0 even while actively trading -- but for futures/index symbols
    # (which DO report real volume), a market that's actually closed can still show
    # a drifting "indicative" price with zero real volume behind it. So: check OHLC
    # flatness always, and ALSO require real volume for symbols where volume is
    # trustworthy.
    is_flat = bool(last["High"] == last["Low"] == last["Open"] == last["Close"])
    symbol = genome.get("symbol", "")
    volume_reliable = symbol in ("NAS100", "US30", "XAUUSD")  # futures -- FX always reports 0
    no_real_volume = volume_reliable and (pd.isna(last.get("Volume")) or last.get("Volume", 0) == 0)

    is_stale = is_flat or no_real_volume

    if is_stale:
        return {
            "direction": None, "entry": None, "stop": None, "target": None,
            "bar_time": str(df.index[-1]), "is_stale": True,
        }

    sig = _signal_series(df, genome, reference_df)
    direction_code = int(sig.iloc[-1])
    close = float(df["Close"].iloc[-1])

    exec_mode = genome.get("exec_mode", "FIXED_RR")
    atr = float(_atr(df, 14).iloc[-1]) if len(df) > 14 else close * 0.002

    if exec_mode == "ATR_STOP":
        stop_distance = max(atr, close * 0.001)
    elif exec_mode == "TRAILING_STOP":
        # trailing stops are typically given more room than a hard fixed stop
        stop_distance = max(atr * 1.5, close * 0.002)
    else:  # FIXED_RR
        recent_range = float((df["High"] - df["Low"]).tail(14).mean())
        stop_distance = max(recent_range, close * 0.002)

    rr = genome.get("rr", 1.5)

    if direction_code == 1:
        direction, stop, target = "BUY", close - stop_distance, close + stop_distance * rr
    elif direction_code == -1:
        direction, stop, target = "SELL", close + stop_distance, close - stop_distance * rr
    else:
        direction, stop, target = None, None, None

    return {
        "direction": direction,
        "entry": round(close, 5) if direction else None,
        "stop": round(stop, 5) if direction else None,
        "target": round(target, 5) if direction else None,
        "bar_time": str(df.index[-1]),
        "is_stale": False,
    }


def _downsample(series: pd.Series, max_points: int = 80) -> list:
    """Keeps the equity curve small enough to store in vault.json without
    bloating it, while still showing the real shape of the curve."""
    if len(series) <= max_points:
        return [round(float(v), 4) for v in series]
    step = max(1, len(series) // max_points)
    return [round(float(v), 4) for v in series.iloc[::step]]


def run_backtest(df: pd.DataFrame, genome: dict, train_frac: float = 0.7,
                  reference_df: pd.DataFrame = None) -> dict:
    """Returns a dict of stats for TRAIN and TEST windows, plus a combined fitness score.
    reference_df: only needed if genome uses the SMT indicator (a correlated
    instrument's OHLC data, aligned separately inside _signal_series)."""
    df = df.dropna().copy()
    split = int(len(df) * train_frac)
    train, test = df.iloc[:split], df.iloc[split:]

    ref_train, ref_test = None, None
    if reference_df is not None:
        reference_df = reference_df.dropna().copy()
        ref_split = int(len(reference_df) * train_frac)
        ref_train, ref_test = reference_df.iloc[:ref_split], reference_df.iloc[ref_split:]

    def score_window(window: pd.DataFrame, ref_window: pd.DataFrame = None) -> dict:
        if len(window) < 20:
            return {"return_pct": 0.0, "max_dd_pct": 0.0, "win_rate": 0.0, "trades": 0, "equity_curve": []}
        sig = _signal_series(window, genome, ref_window).shift(1).fillna(0)  # act on next bar
        rets = window["Close"].pct_change().fillna(0)
        strat_rets = sig * rets

        equity = (1 + strat_rets).cumprod()
        running_max = equity.cummax()
        drawdown = (equity / running_max - 1).min()

        trades = sig.diff().fillna(0) != 0
        n_trades = int(trades.sum())
        wins = int(((strat_rets > 0) & (sig != 0)).sum())
        total_signals = int((sig != 0).sum())

        return {
            "return_pct": round((equity.iloc[-1] - 1) * 100, 2),
            "max_dd_pct": round(abs(drawdown) * 100, 2),
            "win_rate": round(100 * wins / total_signals, 1) if total_signals else 0.0,
            "trades": n_trades,
            "equity_curve": _downsample(equity),
        }

    train_stats = score_window(train, ref_train)
    test_stats = score_window(test, ref_test)

    # Fitness rewards OOS return, penalizes OOS drawdown, and penalizes
    # a strategy that only worked in-sample (curve-fitting).
    oos_penalty = max(0, train_stats["return_pct"] - test_stats["return_pct"]) * 0.05
    fitness = (test_stats["return_pct"] / (test_stats["max_dd_pct"] + 1)) - oos_penalty

    return {
        "genome_id": genome["id"],
        "train": train_stats,
        "test": test_stats,
        "fitness": round(fitness, 2),
    }
