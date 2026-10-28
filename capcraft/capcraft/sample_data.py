"""Synthetic sample data, for demos and tests.

EVERYTHING HERE IS MADE UP. The prices come from a seeded random number
generator. The assets are not real companies or funds, and the results
say nothing about real markets. The sample exists so the tools can be tried
without bringing your own data.

For learning only. Not financial advice.
"""
import numpy as np

SAMPLE_ASSETS = [  # name, beta to the made-up market, own monthly drift, own monthly noise
    ("GROWTH", 1.4, 0.002, 0.030),
    ("STEADY", 0.8, 0.001, 0.015),
    ("BONDS", 0.1, 0.003, 0.008),
    ("RISKY", 1.1, -0.001, 0.060),
]
SAMPLE_WEIGHTS = {"GROWTH": 0.35, "STEADY": 0.30, "BONDS": 0.25, "RISKY": 0.10}


def synthetic_price_csv(seed=11, months=60, with_market=True):
    """CSV text of monthly prices for four made-up assets (and, optionally,
    a made-up market column named MARKET), in the layout data.read_prices expects."""
    if months < 3:
        raise ValueError("Need at least 3 months")
    rng = np.random.default_rng(seed)
    market = rng.normal(0.007, 0.040, months)
    noise = rng.normal(0, 1, (months, len(SAMPLE_ASSETS)))
    rets = {}
    if with_market:
        rets["MARKET"] = market
    for k, (name, beta, drift, vol) in enumerate(SAMPLE_ASSETS):
        rets[name] = drift + beta * market + vol * noise[:, k]
    lines = ["Date," + ",".join(rets), "start," + ",".join("100.00" for _ in rets)]
    prices = {n: 100.0 for n in rets}
    for t in range(months):
        for n in rets:
            prices[n] *= 1 + rets[n][t]
        lines.append(f"M{t + 1:02d}," + ",".join(f"{prices[n]:.2f}" for n in rets))
    return "\n".join(lines)
