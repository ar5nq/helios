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

INDICATORS = ["SMA", "EMA", "RSI", "MACD", "ATR", "BOLLINGER", "CCI", "WILLIAMS_R"]
BIAS_MODES = ["HTF_TREND", "NONE", "TRAILING"]
FILTER_MODES = ["NONE", "ATR_REGIME", "CHOP", "RSI_RANGE"]
EXEC_MODES = ["FIXED_RR", "TRAILING_STOP", "ATR_STOP"]

def _rid():
    return uuid.uuid4().hex[:6].upper()

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
