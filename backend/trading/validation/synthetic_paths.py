"""Synthetic-path Monte Carlo — the generalization tier the validation plane
was missing, requested by the owner 2026-11-28.

The three existing tiers all replay the SAME tape: permutation shuffles the
trades' ordering, bootstrap resamples their PnL, walk-forward re-slices the
windows. None of them answers the question the persistence measurement made
load-bearing (f12-final-verdict-2026-11-28.md: skill peaks early, then decays
to zero): **what does the strategy do on price paths that did not happen?**

A synthetic path is built by stationary block bootstrap over the tape's
bars, chained through close-to-close returns so the synthetic series is
continuous, with intra-bar range structure, volume and funding rate carried
from the source bar of each resampled step. The strategy then runs the full
kernel backtest on the synthetic feature frame — signals, feedback, sizing,
costs all live — so path-dependence is measured, not approximated. That is
the premium this tier pays its compute for: a trade permutation cannot see
that a strategy's stops reshape its own exposure to vol clustering; a fresh
price path can.

Cost honesty, written before use: one simulation is one full kernel backtest.
For non-ML bots a sim costs seconds; for ML families whose predictions are
rolling retrains it costs minutes to tens of minutes. n_simulations is the
caller's budget decision and belongs in the plan, not in a default that
pretends otherwise — the default here is a floor for a meaningful
distribution, not a recommendation.

Causal discipline: the resample draws each target bar from a source bar in
the same tape, and the chaining uses only close-to-close multiplication, so
no synthetic bar carries information from its own future. The bootstrapped
blocks preserve local vol/regime structure with mean length `mean_block`;
they do not preserve calendar structure (a synthetic night bar can carry a
day move) — acceptable for crypto, recorded as a caveat for equities.
"""

from __future__ import annotations

from numbers import Integral

import numpy as np
import pandas as pd


def stationary_bootstrap_indices(n: int, length: int, mean_block: int, rng) -> np.ndarray:
    """Politis-Romano stationary bootstrap as INDEX positions into a tape of
    length n. Same algorithm as validation._stationary_bootstrap, but the
    resample is exposed as positions so every column (price ratios, volume,
    funding) is drawn from the SAME source bar — the joint structure within
    each bar survives, which a column-independent resample would destroy.

    Positions may wrap modulo n: the tape is treated as a ring, the standard
    treatment, because boundary effects would otherwise shorten every block.
    """
    if n < 2 or mean_block < 1:
        return np.arange(length) % max(n, 1)
    p = 1.0 / mean_block
    out = np.empty(length, dtype=int)
    idx = int(rng.integers(0, n))
    for filled in range(length):
        if filled and rng.random() < p:
            idx = int(rng.integers(0, n))
        out[filled] = idx % n
        idx += 1
    return out


def make_synthetic_ohlcv(df: pd.DataFrame, seed: int, mean_block: int = 20) -> pd.DataFrame:
    """One synthetic OHLCV path from a real frame, same length and index.

    Chain construction, all ratios transplanted from the source bar src[t]:
      close[t] = close[t-1] * c2c[src[t]]     — close-to-close move, chained
      open[t]  = close[t-1] * gap[src[t]]     — the overnight/intra gap
      high[t]  = open[t] * ho[src[t]]         — intra-bar range structure
      low[t]   = open[t] * lo[src[t]]
    with the OHLC envelope forced consistent afterwards. Volume and funding
    travel with the source bar unchanged.

    Only the raw OHLCV (+ optional volume, _funding_rate) columns survive —
    every computed feature is invalidated by the price swap and MUST be
    rebuilt downstream; carrying them over would be lookahead in exactly
    the way the feature causality rules forbid.
    """
    n = len(df)
    if n < 30:
        raise ValueError(f"need at least 30 bars for a meaningful resample, got {n}")
    rng = np.random.default_rng(seed)
    src = stationary_bootstrap_indices(n, n, mean_block, rng)

    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        c2c = np.where(prev_close != 0, close / prev_close, 1.0)
        gap = np.where(prev_close != 0, open_ / prev_close, 1.0)
        ho = np.where(open_ != 0, high / open_, 1.0)
        lo = np.where(open_ != 0, low / open_, 1.0)
    for arr in (c2c, gap, ho, lo):
        arr[~np.isfinite(arr)] = 1.0
    c2c[0] = 1.0

    new_close = np.empty(n)
    new_open = np.empty(n)
    new_high = np.empty(n)
    new_low = np.empty(n)
    new_close[0] = float(close[0])  # the chain seeds at the tape's first close
    new_open[0] = float(open_[0])
    for t in range(1, n):
        s = src[t]
        new_close[t] = new_close[t - 1] * float(c2c[s])
        new_open[t] = new_close[t - 1] * float(gap[s])
        new_high[t] = new_open[t] * float(ho[s])
        new_low[t] = new_open[t] * float(lo[s])
    # bar 0 range: no chaining yet, transplant the source bar's shape
    s0 = src[0]
    new_high[0] = new_open[0] * float(ho[s0])
    new_low[0] = new_open[0] * float(lo[s0])
    # OHLC envelope consistency: the transplanted range can miss the close
    # when gap and intra-bar ratios combine — force the bracket, never
    # silently feed the kernel a bar whose close sits outside its own range
    new_high = np.maximum.reduce([new_high, new_open, new_close])
    new_low = np.minimum.reduce([new_low, new_open, new_close])

    out = pd.DataFrame(
        {"open": new_open, "high": new_high, "low": new_low, "close": new_close},
        index=df.index,
    )
    if "volume" in df.columns:
        out["volume"] = df["volume"].to_numpy(dtype=float)[src]
    else:
        out["volume"] = 0.0
    if "_funding_rate" in df.columns:
        out["_funding_rate"] = df["_funding_rate"].to_numpy(dtype=float)[src]
    # provenance: the synthetic frame is perp/spot/equity exactly what its
    # source was — attrs travel so the funding join gate stays honest.
    out.attrs.update(df.attrs)
    out.attrs["synthetic"] = True
    out.attrs["synthetic_seed"] = seed
    return out


def synthetic_path_mc(
    df: pd.DataFrame,
    make_strategy,
    cfg,
    timeframe: str,
    *,
    n_simulations: int = 32,
    seed: int = 42,
    mean_block: int = 20,
    observed_sharpe: float | None = None,
) -> dict:
    """Replay the strategy on synthetic price paths; measure generalization.

    Args:
        df: the ORIGINAL feature-or-raw frame (needs open/high/low/close;
            volume and _funding_rate optional). Only raw columns are used —
            features are rebuilt per synthetic path.
        make_strategy: zero-arg callable returning a FRESH strategy instance
            per simulation. Stateful strategies must never be reused across
            paths, and a callable is the only honest contract for that.
        cfg, timeframe: kernel backtest configuration, unchanged semantics.
        n_simulations: compute budget — each one is a full kernel backtest.
        mean_block: stationary bootstrap mean block in bars.
        observed_sharpe: the strategy's Sharpe on the REAL tape, if already
            measured (the sweep knows it). None measures it here, one extra
            backtest, so the comparison baseline never silently drifts.

    Returns a distribution summary: the fraction of synthetic paths reaching
    the observed Sharpe is the generalization p-value — small means the edge
    is regime-fragile even when it exists, large means the measured Sharpe
    is unremarkable across the regime ensemble. Phipson-Smyth +1 correction
    as in the entries-null tier.
    """
    if isinstance(n_simulations, bool) or not isinstance(n_simulations, Integral) or n_simulations < 2:
        return {"error": f"n_simulations must be >= 2, got {n_simulations}"}
    if isinstance(mean_block, bool) or not isinstance(mean_block, Integral) or mean_block < 1:
        return {"error": f"mean_block must be >= 1, got {mean_block}"}
    missing = [c for c in ("open", "high", "low", "close") if c not in df.columns]
    if missing:
        return {"error": f"frame lacks raw OHLCV columns: {missing} — synthetic paths need the tape, not derived features"}

    from trading.features import build_features
    from trading.kernel import run_kernel_backtest

    # baseline on the real tape — measured through the same path so the
    # comparison is apples-to-apples in every cost and sizing detail.
    if observed_sharpe is None:
        real_feats = df if "ret_1" in df.columns else build_features(df)
        actual = run_kernel_backtest(real_feats, make_strategy(), cfg, timeframe)
        observed_sharpe = float(actual.metrics.get("sharpe", 0.0))

    sharpes: list[float] = []
    trades_counts: list[int] = []
    errors = 0
    for i in range(n_simulations):
        try:
            synth = make_synthetic_ohlcv(df, seed=seed + 1 + i, mean_block=mean_block)
            feats = build_features(synth)
            feats.attrs.update(synth.attrs)
            # injected alpha columns (F10/F11 families) live on the original
            # frame and are invalidated by the price swap; the family hook
            # recomputes them causally when it exists — same contract as the
            # sweep's injector path.
            strategy = make_strategy()
            injector = getattr(strategy, "inject_frame", None)
            if callable(injector):
                feats = injector(feats, "SYNTH")
            result = run_kernel_backtest(feats, strategy, cfg, timeframe)
            sharpes.append(float(result.metrics.get("sharpe", 0.0)))
            trades_counts.append(len(result.trades))
        except Exception as exc:  # one bad path never voids the ensemble
            errors += 1
            if errors <= 2:
                import logging
                logging.getLogger(__name__).warning("synthetic path %d failed: %s", i, exc)

    if not sharpes:
        return {"error": "every synthetic path failed — see log", "observed_sharpe": round(float(observed_sharpe), 4)}

    arr = np.array(sharpes)
    p_gen = float((1 + (arr >= observed_sharpe).sum()) / (len(arr) + 1))
    return {
        "observed_sharpe": round(float(observed_sharpe), 4),
        "synth_mean": round(float(arr.mean()), 4),
        "synth_std": round(float(arr.std()), 4),
        "synth_p05": round(float(np.percentile(arr, 5)), 4),
        "synth_p95": round(float(np.percentile(arr, 95)), 4),
        "frac_positive": round(float((arr > 0).mean()), 4),
        "p_value_generalization": round(p_gen, 4),
        "n_simulations": len(arr),
        "n_errors": errors,
        "mean_trades": round(float(np.mean(trades_counts)), 1) if trades_counts else 0.0,
        "mean_block": mean_block,
    }
