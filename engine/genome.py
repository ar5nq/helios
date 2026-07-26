"""
A Strategy Genome is a JSON-serializable set of genes describing:
  - bias filter (higher-timeframe trend condition)
  - signal generator (the actual entry trigger)
  - execution rule (stop/target logic)

This mirrors a "Signal / Bias / Filter / Exec / Mgmt" composition
so a strategy's genetic makeup is inspectable at a glance.
"""
import random
import uuid

INDICATORS = ["SMA", "EMA", "RSI", "MACD", "ATR", "BOLLINGER", "CCI", "WILLIAMS_R", "FVG", "OTE"]
BIAS_MODES = ["HTF_TREND", "NONE", "TRAILING"]
FILTER_MODES = ["NONE", "ATR_REGIME", "CHOP", "RSI_RANGE"]
EXEC_MODES = ["FIXED_RR", "TRAILING_STOP", "ATR_STOP"]

def _rid():
    return uuid.uuid4().hex[:6].upper()

INDICATOR_NAMES = {
    "SMA": "MA Cross", "EMA": "EMA Trend", "RSI": "RSI Reversal",
    "MACD": "MACD Cross", "ATR": "Vol Breakout", "BOLLINGER": "Band Breakout",
    "CCI": "CCI Reversion", "WILLIAMS_R": "Williams Reversion",
    "FVG": "FVG Tap", "OTE": "OTE Retracement",
}
BIAS_NAMES = {"HTF_TREND": "HTF", "TRAILING": "Trail", "NONE": None}
FILTER_NAMES = {
    "ATR_REGIME": "Vol-Filtered", "CHOP": "Anti-Chop",
    "RSI_RANGE": "RSI-Range", "NONE": None,
}


MECHANISM_NAMES = {
    "FIXED_RR": "Fixed RR",
    "TRAILING_STOP": "Trailing Runner",
    "ATR_STOP": "Vol-Adaptive Stop",
}


def genome_mechanism(genome: dict) -> str:
    return MECHANISM_NAMES.get(genome.get("exec_mode"), genome.get("exec_mode", "?"))


INDICATOR_EXPLAIN = {
    "SMA": "enters when price crosses above/below a moving average -- a basic trend-following trigger",
    "EMA": "enters when price crosses above/below a faster-reacting moving average -- trend-following, quicker to trigger than SMA",
    "RSI": "enters on RSI reaching oversold/overbought levels -- a mean-reversion trigger, betting price snaps back",
    "MACD": "enters when the MACD line crosses its signal line -- a momentum-shift trigger",
    "ATR": "enters on a volatility breakout -- price moving further than normal in one bar, betting momentum continues",
    "BOLLINGER": "enters when price breaks outside its Bollinger Band -- a volatility-breakout trigger",
    "CCI": "enters when CCI hits an extreme reading -- a mean-reversion trigger similar to RSI",
    "WILLIAMS_R": "enters on Williams %R oversold/overbought extremes -- another mean-reversion trigger",
    "FVG": "enters when price taps back into an unfilled Fair Value Gap -- an ICT-style imbalance-fill trigger",
    "OTE": "enters when price retraces into the 61.8-79% Fibonacci zone of a recent swing -- ICT's Optimal Trade Entry",
}
BIAS_EXPLAIN = {
    "HTF_TREND": "only takes trades that agree with the direction of a higher-timeframe trend filter",
    "TRAILING": "only takes trades that agree with a slower trailing trend read -- looser than HTF_TREND",
    "NONE": "has no trend filter -- it takes every signal regardless of the broader direction",
}
FILTER_EXPLAIN = {
    "ATR_REGIME": "only trades when volatility is above its recent average -- skips quiet/dead periods",
    "CHOP": "only trades when the market isn't choppy/sideways -- skips low-conviction ranging periods",
    "RSI_RANGE": "only trades when RSI isn't already at an extreme -- avoids chasing exhausted moves",
    "NONE": "has no extra filter -- every raw signal gets through",
}
MECHANISM_EXPLAIN = {
    "FIXED_RR": "uses a fixed stop distance based on recent price range, with a fixed reward multiple",
    "TRAILING_STOP": "uses a wider stop (1.5x ATR) to give the trade room to run -- meant for trades you let breathe",
    "ATR_STOP": "sizes its stop directly off current volatility (ATR) -- tightens up in calm markets, widens in wild ones",
}


def explain_genome(genome: dict) -> str:
    """A plain-English paragraph explaining what this strategy actually does
    and how to think about managing a trade from it."""
    indicator = INDICATOR_EXPLAIN.get(genome.get("signal_indicator"), "uses a custom trigger")
    bias = BIAS_EXPLAIN.get(genome.get("bias"), "")
    filt = FILTER_EXPLAIN.get(genome.get("filter"), "")
    mechanism = MECHANISM_EXPLAIN.get(genome.get("exec_mode"), "")
    rr = genome.get("rr", 1.5)

    parts = [
        f"This strategy {indicator}.",
        f"It {bias}.",
        f"It {filt}.",
        f"For trade management, it {mechanism}, targeting a 1:{rr} reward-to-risk ratio.",
    ]
    return " ".join(parts)


def genome_label(genome: dict) -> str:
    """Human-readable name built from what the strategy actually does,
    e.g. 'RSI Reversal (HTF, Anti-Chop)' instead of a hex id."""
    base = INDICATOR_NAMES.get(genome.get("signal_indicator"), genome.get("signal_indicator", "?"))
    tags = [t for t in (BIAS_NAMES.get(genome.get("bias")), FILTER_NAMES.get(genome.get("filter"))) if t]
    return f"{base} ({', '.join(tags)})" if tags else base


def random_genome(symbol: str, timeframe: str) -> dict:
    return {
        "id": _rid(),
        "symbol": symbol,
        "timeframe": timeframe,
        "bias": random.choice(BIAS_MODES),
        "signal_indicator": random.choice(INDICATORS),
        "signal_params": {
            "period": random.choice([7, 14, 21, 50, 100]),
            "threshold": round(random.uniform(0.2, 0.8), 2),
        },
        "filter": random.choice(FILTER_MODES),
        "exec_mode": random.choice(EXEC_MODES),
        "rr": round(random.uniform(0.5, 3.0), 2),
        "generation": 0,
        "parents": [],
    }

def mutate(genome: dict, rate: float = 0.25) -> dict:
    child = dict(genome)
    child["id"] = _rid()
    child["parents"] = [genome["id"]]
    child["generation"] = genome.get("generation", 0) + 1

    if random.random() < rate:
        child["signal_indicator"] = random.choice(INDICATORS)
    if random.random() < rate:
        child["signal_params"] = {
            "period": random.choice([7, 14, 21, 50, 100]),
            "threshold": round(random.uniform(0.2, 0.8), 2),
        }
    if random.random() < rate:
        child["bias"] = random.choice(BIAS_MODES)
    if random.random() < rate:
        child["filter"] = random.choice(FILTER_MODES)
    if random.random() < rate:
        child["exec_mode"] = random.choice(EXEC_MODES)
    if random.random() < rate:
        child["rr"] = round(max(0.3, child["rr"] + random.uniform(-0.5, 0.5)), 2)
    return child

def crossover(a: dict, b: dict) -> dict:
    child = {
        "id": _rid(),
        "symbol": a["symbol"],
        "timeframe": a["timeframe"],
        "bias": random.choice([a["bias"], b["bias"]]),
        "signal_indicator": random.choice([a["signal_indicator"], b["signal_indicator"]]),
        "signal_params": random.choice([a["signal_params"], b["signal_params"]]),
        "filter": random.choice([a["filter"], b["filter"]]),
        "exec_mode": random.choice([a["exec_mode"], b["exec_mode"]]),
        "rr": round((a["rr"] + b["rr"]) / 2, 2),
        "generation": max(a.get("generation", 0), b.get("generation", 0)) + 1,
        "parents": [a["id"], b["id"]],
    }
    return child
