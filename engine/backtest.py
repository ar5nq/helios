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


def _raw_signal(df: pd.DataFrame, genome: dict) -> pd.Series:
    """The primary entry trigger, before bias/filter gating."""
    period = genome["signal_params"]["period"]
    threshold = genome["signal_params"]["threshold"]
    close = df["Close"]

    if genome["signal_indicator"] == "RSI":
        rsi = _rsi(close, period)
        long = rsi < (30 * (1 + (0.5 - threshold)))
        short = rsi > (70 * (1 + (threshold - 0.5)))
    elif genome["signal_indicator"] in ("SMA", "EMA"):
        ma = close.rolling(period).mean() if genome["signal_indicator"] == "SMA" else close.ewm(span=period).mean()
        long = close > ma
        short = close < ma
    else:
        # generic momentum proxy for MACD/ATR/BOLLINGER/CCI/WILLIAMS_R
        mom = close.pct_change(period)
        long = mom > threshold * mom.std()
        short = mom < -threshold * mom.std()

    sig = pd.Series(0, index=df.index)
    sig[long] = 1
    sig[short] = -1
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


def _signal_series(df: pd.DataFrame, genome: dict) -> pd.Series:
    """Full signal pipeline: raw entry trigger -> bias gate -> filter gate.
    All three genome genes now genuinely change trading behavior."""
    sig = _raw_signal(df, genome)
    sig = _apply_bias(sig, df, genome)
    sig = _apply_filter(sig, df, genome)
    return sig


def latest_signal(df: pd.DataFrame, genome: dict) -> dict:
    """Returns the signal direction on the most recent completed bar, plus
    entry/stop/target sized according to the genome's exec_mode and risk:reward.
    Used by the live runner to decide whether to emit a new signal."""
    df = df.dropna()
    sig = _signal_series(df, genome)
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
    }


def run_backtest(df: pd.DataFrame, genome: dict, train_frac: float = 0.7) -> dict:
    """Returns a dict of stats for TRAIN and TEST windows, plus a combined fitness score."""
    df = df.dropna().copy()
    split = int(len(df) * train_frac)
    train, test = df.iloc[:split], df.iloc[split:]

    def score_window(window: pd.DataFrame) -> dict:
        if len(window) < 20:
            return {"return_pct": 0.0, "max_dd_pct": 0.0, "win_rate": 0.0, "trades": 0}
        sig = _signal_series(window, genome).shift(1).fillna(0)  # act on next bar
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
        }

    train_stats = score_window(train)
    test_stats = score_window(test)

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
