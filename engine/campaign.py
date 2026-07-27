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
from .data_feed import fetch, SMT_REFERENCE

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


def _genome_signature(g: dict) -> tuple:
    """Identity based on actual strategy config, not the random id -- so we can
    detect when the population has collapsed onto duplicates."""
    return (g["bias"], g["signal_indicator"], tuple(sorted(g["signal_params"].items())),
            g["filter"], g["exec_mode"], round(g["rr"], 1))


def run_campaign(symbol: str, timeframe: str, population: int = 40,
                  generations: int = 5, survive_top: int = 10,
                  fitness_gate: float = 1.0, immigrant_frac: float = 0.3,
                  min_test_trades: int = 25) -> dict:
    df = fetch(symbol, timeframe)

    reference_df = None
    ref_symbol = SMT_REFERENCE.get(symbol)
    if ref_symbol:
        try:
            reference_df = fetch(ref_symbol, timeframe)
        except Exception:
            reference_df = None  # SMT genomes will just fail their backtest and get skipped
    # Guarantee every indicator type is represented at least once in the
    # starting population -- otherwise, with 16 indicators and a small
    # population, rare ones (FVG, SMT, order blocks, etc.) can go entirely
    # untested purely by random chance, every single campaign.
    from .genome import INDICATORS
    pop = []
    for indicator in INDICATORS[:population]:
        g = random_genome(symbol, timeframe)
        g["signal_indicator"] = indicator
        pop.append(g)
    while len(pop) < population:
        pop.append(random_genome(symbol, timeframe))

    history = []
    all_candidates = []  # (genome, result) from EVERY generation, not just the last

    for gen in range(generations):
        scored = []
        for g in pop:
            try:
                result = run_backtest(df, g, reference_df=reference_df)
            except Exception:
                continue
            scored.append((g, result))

        scored.sort(key=lambda x: x[1]["fitness"], reverse=True)
        all_candidates.extend(scored)

        # de-duplicate survivors by actual strategy config so identical clones
        # don't fill up all 10 "survivor" slots
        seen_signatures = set()
        top = []
        for g, r in scored:
            sig = _genome_signature(g)
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)
            top.append((g, r))
            if len(top) >= survive_top:
                break

        history.append({
            "generation": gen + 1,
            "best_fitness": top[0][1]["fitness"] if top else None,
            "unique_survivors": len(top),
        })

        # breed next generation: keep unique elites, fill some slots with fresh
        # random "immigrants" (new genetic material), rest via crossover/mutation
        import random
        next_pop = [g for g, _ in top]
        n_immigrants = max(1, int(population * immigrant_frac))
        next_pop += [random_genome(symbol, timeframe) for _ in range(n_immigrants)]

        while len(next_pop) < population and top:
            a, b = random.sample([g for g, _ in top], min(2, len(top)))
            child = crossover(a, b) if a["id"] != b["id"] else mutate(a, rate=0.5)
            next_pop.append(child)
        pop = next_pop

    # final vaulting: anything unique that cleared BOTH the fitness gate and the
    # minimum out-of-sample trade count, checked across EVERY generation's
    # population -- not just the last one. A genome (e.g. a rare ORB strategy)
    # can score well in generation 1 but get bred out by generation 3 if its
    # small sample size makes its fitness look mediocre in that one run; without
    # checking every generation, a genuinely good result like that would never
    # get vaulted at all.
    vault = _load_vault()
    seen_signatures = set()
    promoted = []
    rejected_thin_sample = 0
    # prefer the best-fitness version of each unique genome signature across
    # all generations, not just whichever one happened to appear last
    all_candidates.sort(key=lambda x: x[1]["fitness"], reverse=True)
    for g, r in all_candidates:
        sig = _genome_signature(g)
        if sig in seen_signatures:
            continue
        if r["test"]["trades"] < min_test_trades:
            rejected_thin_sample += 1
            continue
        if r["fitness"] < fitness_gate:
            continue
        seen_signatures.add(sig)
        promoted.append((g, r))

    for genome, r in promoted:
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
        "rejected_thin_sample": rejected_thin_sample,
        "top_survivors": [r for g, r in top],
    }
