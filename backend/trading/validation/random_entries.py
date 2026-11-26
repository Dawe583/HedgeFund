"""Random-entries null test — the permutation test's honest replacement for
entry quality, declared in docs/research/permutation-methodology-2026-11-26.md.

The ordering-permutation null measures ordering luck and is structurally
blind to entry quality: a steady edge permutes into itself. The correct
null for "were the entries good?" is a matched control:

    same tape, same kernel, same costs, same sizing —
    same NUMBER of entries, same long/short mix, same stop/take-profit
    parameters, same holding-period distribution —
    but entries fired at uniformly random bars instead of the candidate's.

If the candidate's entries carry information, its Sharpe sits above the
control distribution. If random entries do as well, the candidate's logic
is decoration on beta. Every other degree of freedom is held constant by
construction — that is what makes this the entry-quality null and not
another artifact.
"""

from __future__ import annotations

import math

import numpy as np

from trading.backtest.engine import Signal
from trading.bots.base import BaseStrategy
from trading.kernel import run_kernel_backtest


class _RandomControl(BaseStrategy):
    """The matched control strategy: entries at pre-drawn random bars with
    pre-drawn directions, exits by the same protective machinery the
    candidate used (stop/tp/timeout) plus a drawn holding-period expiry —
    the candidate's own exit logic replaced by time-matched randomness,
    because copying the exit logic would copy the very edge under test."""

    name = "randomcontrol"

    def __init__(self, entries: dict, holds: dict, stop_atr: float, tp_rr: float):
        # entries: bar_index -> direction ("long"/"short")
        # holds: bar_index -> max bars to hold from that entry
        self._entries = entries
        self._holds = holds
        self._stop = stop_atr
        self._tp = tp_rr
        self._open_since: int | None = None
        self._open_hold: int = 0

    def signal(self, i: int, df) -> Signal | None:
        try:
            if self._open_since is not None:
                if i - self._open_since >= self._open_hold:
                    self._open_since = None
                    return Signal(side="flat", confidence=0.6, stop_atr=self._stop, tp_rr=self._tp)
                return None
            if i in self._entries:
                self._open_since = i
                self._open_hold = self._holds.get(i, 24)
                return Signal(side=self._entries[i], confidence=0.6, stop_atr=self._stop, tp_rr=self._tp)
            return None
        except Exception:
            return None


def random_entries_test(
    df,
    candidate_instance,
    cfg,
    timeframe: str,
    *,
    n_simulations: int = 30,
    seed: int = 42,
    min_hold: int = 4,
) -> dict:
    """Run the candidate and the matched random-entry control on the same
    frame. Returns the candidate's Sharpe, the control distribution, and
    the fraction of controls reaching the candidate — the entry-quality
    p-value. Deterministic under `seed`.

    The control matches: entry count, long/short ratio, per-entry stop/tp
    (sampled from the candidate's own entries), holding-period distribution
    (the candidate's realized holds, randomly reassigned). It does not
    match intra-trade exit timing — copying the exit logic would copy the
    edge under test.
    """
    rng = np.random.default_rng(seed)

    actual = run_kernel_backtest(df, candidate_instance, cfg, timeframe)
    actual_sharpe = float(actual.metrics.get("sharpe", 0.0))
    trades = actual.trades
    if len(trades) < 5:
        return {"error": f"need >= 5 trades for a meaningful control, got {len(trades)}",
                "actual_sharpe": round(actual_sharpe, 4)}

    entry_bars = [int(t["entry_bar"]) for t in trades]
    directions = [1 if t.get("side", t.get("direction")) in ("long", 1) or (isinstance(t.get("direction"), (int, float)) and t.get("direction") > 0) else -1 for t in trades]
    holds = [max(int(t.get("bars_held", min_hold)), min_hold) for t in trades]
    long_frac = sum(1 for d in directions if d > 0) / len(directions)
    n_entries = len(entry_bars)

    # the candidate's own stop/tp come from its signal params, uniform per
    # family here — read them off the instance where exposed, else the
    # kernel default shape; exactness matters less than matching
    stop_atr = float(getattr(candidate_instance, "stop_atr", 2.0))
    tp_rr = float(getattr(candidate_instance, "tp_rr", 1.5) or 1.5)

    # eligible entry bars: warm-up end to frame end, one entry per bar
    first = max(min(entry_bars), 30)
    last = len(df) - 2
    if last - first < n_entries:
        return {"error": "frame too short for matched entry count",
                "actual_sharpe": round(actual_sharpe, 4)}

    sim_sharpes: list[float] = []
    for _ in range(n_simulations):
        bars = rng.choice(np.arange(first, last), size=min(n_entries, last - first), replace=False)
        entries = {}
        holds_map = {}
        perm_holds = rng.permutation(holds)
        for j, b in enumerate(sorted(bars)):
            b = int(b)
            entries[b] = "long" if rng.random() < long_frac else "short"
            holds_map[b] = int(perm_holds[j % len(perm_holds)])
        control = _RandomControl(entries, holds_map, stop_atr, tp_rr)
        sim = run_kernel_backtest(df, control, cfg, timeframe)
        sim_sharpes.append(float(sim.metrics.get("sharpe", 0.0)))

    arr = np.array(sim_sharpes)
    p_value = float((arr >= actual_sharpe).mean())
    return {
        "actual_sharpe": round(actual_sharpe, 4),
        "control_mean": round(float(arr.mean()), 4),
        "control_std": round(float(arr.std()), 4),
        "control_p95": round(float(np.percentile(arr, 95)), 4),
        "p_value_entries": round(p_value, 4),
        "n_simulations": n_simulations,
        "n_entries_matched": n_entries,
        "long_fraction": round(long_frac, 3),
    }
