"""
Pulls historical OHLC data for backtesting.
Uses yfinance (free, no API key) -- good enough for FX majors, gold, indices.
Maps human-friendly symbols (XAUUSD, GBPJPY, US30) to Yahoo tickers.
"""
import yfinance as yf
import pandas as pd

SYMBOL_MAP = {
    "XAUUSD": "GC=F",
    "US30": "YM=F",     # Dow futures -- trades Asia/London/NY like a real US30 CFD
    "NAS100": "NQ=F",   # Nasdaq-100 FUTURES, not ^NDX -- ^NDX only updates during
                        # NYSE cash hours (9:30am-4pm ET); NQ=F trades nearly
                        # 24hrs/day Sun evening-Fri evening, matching what
                        # brokers actually quote as "NAS100"
    "US500": "ES=F",    # S&P 500 futures -- used as the SMT divergence reference for NAS100
    "GBPJPY": "GBPJPY=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "EURUSD": "EURUSD=X",
    "EURGBP": "EURGBP=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "CAD=X",
}

# For SMT (Smart Money Divergence): which reference instrument to compare
# a symbol against. NAS100 vs US500 is the classic ICT pairing -- both
# usually make highs/lows together; when they DON'T, that's the divergence.
SMT_REFERENCE = {
    "NAS100": "US500",
    "US500": "NAS100",
}

TF_MAP = {
    "M1": ("7d", "1m"),     # Yahoo hard-limits 1m data to the last 7 days -- no way around this
    "M3": ("7d", "1m"),     # resampled from 1m; same 7-day ceiling as M1
    "M5": ("60d", "5m"),
    "M15": ("60d", "15m"),
    "M30": ("60d", "30m"),
    "H1": ("730d", "1h"),
    "H2": ("730d", "1h"),   # yfinance has no native H2; resampled from H1
    "H4": ("730d", "1h"),   # resampled from H1
    "D1": ("5y", "1d"),
}


def fetch(symbol: str, timeframe: str) -> pd.DataFrame:
    ticker = SYMBOL_MAP.get(symbol)
    if ticker is None:
        raise ValueError(f"Unknown symbol: {symbol}")
    period, interval = TF_MAP.get(timeframe, ("1y", "1d"))

    df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for {symbol} ({ticker})")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if timeframe == "M3" and interval == "1m":
        df = df.resample("3min").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
        }).dropna()

    if timeframe in ("H2", "H4") and interval == "1h":
        rule = "2h" if timeframe == "H2" else "4h"
        df = df.resample(rule).agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
        }).dropna()

    return df
