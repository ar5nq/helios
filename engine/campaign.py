"""
Runs a breeding campaign: generation 0 is random genomes, each subsequent
generation mutates/crosses the fittest survivors of the last one.
Survivors that clear the fitness gate get written to the vault (data/vault.json).
"""
import json
import os
from datetime import datetime, timezone

from .genome import random_genome, mutate, crossover
from .backtest import run_backtest
from .data_feed import fetch

VAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "vault.json")


def _load_vault() -> list:
    if os.path.exists(VAULT_PATH):
        with open(VAULT_PATH) as f:
            return json.load(f)
    return []


def _save_vault(vault: list):
    os.makedirs(os.path.dirname(VAULT_PATH), exist_ok=True)
    with open(VAULT_PATH, "w") as f:
        json.dump(vault, f, indent=2)


def run_campaign(symbol: str, timeframe: str, population: int = 40,
                  generations: int = 5, survive_top: int = 10,
                  fitness_gate: float = 1.0) -> dict:
    df = fetch(symbol, timeframe)
    pop = [random_genome(symbol, timeframe) for _ in range(population)]

    history = []
    for gen in range(generations):
        scored = []
        for g in pop:
            try:
                result = run_backtest(df, g)
            except Exception:
                continue
            scored.append((g, result))

        scored.sort(key=lambda x: x[1]["fitness"], reverse=True)
        top = scored[:survive_top]
        history.append({
            "generation": gen + 1,
            "best_fitness": top[0][1]["fitness"] if top else None,
            "survivors": len(top),
        })

        # breed next generation from top survivors
        next_pop = [g for g, _ in top]
        while len(next_pop) < population and top:
            import random
            a, b = random.sample([g for g, _ in top], min(2, len(top)))
            child = crossover(a, b) if a["id"] != b["id"] else mutate(a)
            next_pop.append(child)
        pop = next_pop

    # final vaulting: anything that cleared the fitness gate on the last run
    vault = _load_vault()
    promoted = [r for g, r in scored if r["fitness"] >= fitness_gate]
    for r in promoted:
        genome = next(g for g, res in scored if res["genome_id"] == r["genome_id"])
        vault.append({
            **genome,
            "score": r,
            "vaulted_at": datetime.now(timezone.utc).isoformat(),
        })
    _save_vault(vault)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "generations_run": generations,
        "history": history,
        "promoted_count": len(promoted),
        "top_survivors": [r for g, r in scored[:survive_top]],
    }
