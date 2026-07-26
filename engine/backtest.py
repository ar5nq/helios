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


def _signal_series(df: pd.DataFrame, genome: dict) -> pd.Series:
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
        # generic momentum fallback for MACD/ATR/BOLLINGER/CCI/WILLIAMS_R placeholders
        mom = close.pct_change(period)
        long = mom > threshold * mom.std()
        short = mom < -threshold * mom.std()

    sig = pd.Series(0, index=df.index)
    sig[long] = 1
    sig[short] = -1
    return sig


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
