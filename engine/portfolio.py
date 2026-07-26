"""
Given a set of vaulted strategies, scores how diversified they actually are
-- not just "different symbols" but real correlation between their test
(out-of-sample) equity curves. Two strategies that make money on the exact
same days aren't actually diversifying you, even if their DNA looks different.
"""
import numpy as np


def _returns_from_curve(curve: list) -> np.ndarray:
    arr = np.array(curve, dtype=float)
    if len(arr) < 2:
        return np.array([])
    return np.diff(arr) / arr[:-1]


def pairwise_correlation(genome_a: dict, genome_b: dict) -> float:
    """Correlation between two strategies' out-of-sample return series.
    Returns None if either has too little data to compare."""
    curve_a = genome_a.get("score", {}).get("test", {}).get("equity_curve", [])
    curve_b = genome_b.get("score", {}).get("test", {}).get("equity_curve", [])
    ra, rb = _returns_from_curve(curve_a), _returns_from_curve(curve_b)
    n = min(len(ra), len(rb))
    if n < 5:
        return None
    ra, rb = ra[:n], rb[:n]
    if ra.std() == 0 or rb.std() == 0:
        return None
    return round(float(np.corrcoef(ra, rb)[0, 1]), 3)


def _concentration(values: list) -> float:
    """% share of the most common value -- 100% = all identical (bad),
    lower = more spread out (good)."""
    if not values:
        return 0.0
    from collections import Counter
    counts = Counter(values)
    return round(100 * max(counts.values()) / len(values), 1)


def _grade_from_score(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _bucket_breakdown(values: list) -> dict:
    """Returns bucket count and the top bucket's share -- e.g. '5 buckets,
    top NAS100 60%' -- matching the reference's per-axis bucket display."""
    if not values:
        return {"buckets": 0, "top_value": None, "top_pct": 0.0}
    from collections import Counter
    counts = Counter(values)
    top_value, top_count = counts.most_common(1)[0]
    return {
        "buckets": len(counts),
        "top_value": top_value,
        "top_pct": round(100 * top_count / len(values), 1),
    }


def analyze_portfolio(genomes: list) -> dict:
    """genomes: list of full vault entries (with score/test/equity_curve).
    Returns diversity sub-grades, bucket breakdowns, and an overall grade,
    matching the reference Diversity Grade panel's structure."""
    if len(genomes) < 2:
        return {
            "overall_grade": "N/A", "members": len(genomes),
            "note": "Need at least 2 strategies to measure diversity.",
        }

    symbols = [g["symbol"] for g in genomes]
    timeframes = [g["timeframe"] for g in genomes]
    indicators = [g["signal_indicator"] for g in genomes]
    mechanisms = [g.get("exec_mode") for g in genomes]

    symbol_conc = _concentration(symbols)
    timeframe_conc = _concentration(timeframes)
    indicator_conc = _concentration(indicators)
    mechanism_conc = _concentration(mechanisms)

    correlations = []
    for i in range(len(genomes)):
        for j in range(i + 1, len(genomes)):
            c = pairwise_correlation(genomes[i], genomes[j])
            if c is not None:
                correlations.append(c)
    avg_corr = round(float(np.mean(correlations)), 3) if correlations else None

    # Four sub-grades, same spirit as the reference panel:
    # Concentration: symbol/timeframe/indicator spread
    concentration_score = 100 - ((symbol_conc + timeframe_conc + indicator_conc) / 3)
    # Size: penalize very small portfolios (less than ~10 members is thin)
    size_score = min(100, round((len(genomes) / 15) * 100))
    # Exposure: mechanism (exec_mode) spread -- are all trades managed the same way
    exposure_score = 100 - mechanism_conc
    # Correlation: only positive correlation hurts; negative/zero is fine or good
    if avg_corr is None:
        correlation_score = 50
    elif avg_corr <= 0:
        correlation_score = 100
    else:
        correlation_score = 100 - (avg_corr * 100)

    overall_score = round((concentration_score + size_score + exposure_score + correlation_score) / 4, 1)

    tests = [g.get("score", {}).get("test", {}) for g in genomes]
    combined_return = round(sum(t.get("return_pct", 0) for t in tests) / len(tests), 2)
    combined_dd = round(max((t.get("max_dd_pct", 0) for t in tests), default=0), 2)

    return {
        "members": len(genomes),
        "overall_grade": _grade_from_score(overall_score),
        "overall_score": overall_score,
        "sub_grades": {
            "concentration": {"grade": _grade_from_score(concentration_score), "score": round(concentration_score, 1)},
            "size": {"grade": _grade_from_score(size_score), "score": round(size_score, 1)},
            "exposure": {"grade": _grade_from_score(exposure_score), "score": round(exposure_score, 1)},
            "correlation": {"grade": _grade_from_score(correlation_score), "score": round(correlation_score, 1)},
        },
        "buckets": {
            "symbol": _bucket_breakdown(symbols),
            "timeframe": _bucket_breakdown(timeframes),
            "indicator": _bucket_breakdown(indicators),
            "mechanism": _bucket_breakdown(mechanisms),
        },
        "avg_pairwise_correlation": avg_corr,
        "combined_avg_test_return_pct": combined_return,
        "combined_worst_test_dd_pct": combined_dd,
    }
