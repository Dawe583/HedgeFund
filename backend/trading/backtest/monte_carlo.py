"""Monte Carlo strategy evaluation — bootstrap over realized trade returns.

Answers: what do the NEXT 100 trades look like if edge persists? Produces
percentile fan paths, drawdown distribution and risk-of-ruin style stats.
"""

from __future__ import annotations

import numpy as np


def monte_carlo_trades(
    trade_returns_pct: list[float],
    n_sims: int = 500,
    horizon: int = 100,
    risk_per_trade: float = 1.0,
    start_equity: float = 100.0,
    seed: int = 7,
) -> dict:
    """Resample historical per-trade returns (in % of equity risked).

    Each sim compounds `horizon` trades sampled with replacement.
    Returns percentile bands + summary stats. Deterministic via seed.
    """
    rng = np.random.default_rng(seed)
    rets = np.asarray([r for r in trade_returns_pct if r == r], dtype=float)
    if len(rets) < 10:
        return {"error": "need >= 10 closed trades"}

    # returns are % of notional; convert to % of equity via fixed-fraction sizing
    eq_paths = np.zeros((n_sims, horizon + 1))
    eq_paths[:, 0] = start_equity

    idx = rng.integers(0, len(rets), size=(n_sims, horizon))
    samples = rets[idx]  # (n_sims, horizon)
    growth = 1.0 + samples * (risk_per_trade / 100.0)
    growth = np.clip(growth, 0.05, None)  # no negative equity
    eq_paths[:, 1:] = start_equity * np.cumprod(growth, axis=1)

    pct = {5: [], 25: [], 50: [], 75: [], 95: []}
    for t in range(horizon + 1):
        col = eq_paths[:, t]
        for q in pct:
            pct[q].append(float(np.percentile(col, q)))

    final = eq_paths[:, -1]
    peak = np.maximum.accumulate(eq_paths, axis=1)
    dd = ((eq_paths - peak) / peak).min(axis=1)

    return {
        "n_trades_hist": len(rets),
        "n_sims": n_sims,
        "horizon": horizon,
        "risk_per_trade_pct": risk_per_trade,
        "bands": {
            str(q): [round(v, 3) for v in vals] for q, vals in pct.items()
        },
        "final_equity": {
            "p5": round(float(np.percentile(final, 5)), 2),
            "p25": round(float(np.percentile(final, 25)), 2),
            "median": round(float(np.percentile(final, 50)), 2),
            "p75": round(float(np.percentile(final, 75)), 2),
            "p95": round(float(np.percentile(final, 95)), 2),
        },
        "max_drawdown": {
            "median_pct": round(float(np.percentile(dd, 50)) * -100, 2),
            "p95_pct": round(float(np.percentile(dd, 5)) * -100, 2),
            "worst_pct": round(float(dd.min()) * -100, 2),
        },
        "prob_profit": round(float((final > start_equity).mean()), 4),
        "prob_ruin_20": round(float((eq_paths.min(axis=1) <= start_equity * 0.80).mean()), 4),
    }


def summarize_edge(trade_returns_pct: list[float]) -> dict:
    """Quick sanity stats used next to the MC chart."""
    a = np.asarray(trade_returns_pct, dtype=float)
    if len(a) < 2:
        return {}
    wins = a[a > 0]
    losses = a[a <= 0]
    return {
        "trades_n": len(a),
        "win_rate": round(float(len(wins) / len(a)), 4),
        "avg_win_pct": round(float(wins.mean()) if len(wins) else 0.0, 4),
        "avg_loss_pct": round(float(losses.mean()) if len(losses) else 0.0, 4),
        "expectancy_pct": round(float(a.mean()), 4),
        "std_pct": round(float(a.std()), 4),
        "sharpe_per_trade": round(float(a.mean() / a.std()) if a.std() > 0 else 0.0, 3),
    }
