# F12 final verdict — regime-conditional ML, complete: A, B, persistence

Date: 2026-11-28. The overnight chain finished: phase A (8 cells, in-sample),
phase B (8 cells, out-of-sample with rails), persistence retrain measurement
on crypto and equities, budget 16/16 consumed. The verdict is written once,
against the pre-registered declaration in `program-2026-11-26.md`.

## 1. Phase A — in-sample: 8/8 rejected

| cell | symbol | trades | Sharpe | perm p |
|---|---|---|---|---|
| mlroll-w2000-c24 | ETHUSDT | 601 | −3.74 | 1.00 |
| mlroll-w2000-c24 | BTCUSDT | 641 | −5.49 | 1.00 |
| mlroll-w2000-c48 | ETHUSDT | 600 | −4.21 | 1.00 |
| mlroll-w2000-c48 | BTCUSDT | 647 | −6.12 | 1.00 |
| mlroll-w4000-c24 | BTCUSDT | 559 | −5.39 | 1.00 |
| mlroll-w4000-c24 | ETHUSDT | 490 | −3.07 | 1.00 |
| mlroll-w4000-c48 | BTCUSDT | 546 | −6.00 | 1.00 |
| mlroll-w4000-c48 | ETHUSDT | 491 | −2.38 | 1.00 |

Mean Sharpe −4.55. Break-even per round trip is 0.37% (2.8bp fee + 34.2bp
slippage per side at 1h) — but the zero-cost counterfactual settled the cause:
**−12.19% vs −12.21% net, cost contribution 0.02pp**. Costs did not kill this
edge; the ML momentum signal is anti-predictive in-sample. The in-sample loop
is capturing mean-reversion the entry logic misreads as momentum.

## 2. Phase B — out-of-sample, rails on: 8/8 rejected, all resolvable

| cell | symbol | trades B | Sharpe B | power |
|---|---|---|---|---|
| mlroll-w2000-c24 | ETHUSDT | 23 | −2.73 | resolvable ±0.101 |
| mlroll-w2000-c24 | BTCUSDT | 40 | −1.74 | resolvable ±0.393 |
| mlroll-w2000-c48 | ETHUSDT | 22 | −2.31 | resolvable ±0.53 |
| mlroll-w2000-c48 | BTCUSDT | 54 | −1.59 | resolvable ±0.338 |
| mlroll-w4000-c24 | BTCUSDT | 71 | −1.46 | resolvable ±0.338 |
| mlroll-w4000-c24 | ETHUSDT | 77 | −1.38 | resolvable ±0.283 |
| mlroll-w4000-c48 | BTCUSDT | 67 | −1.44 | resolvable ±0.304 |
| mlroll-w4000-c48 | ETHUSDT | 74 | −1.58 | resolvable ±0.289 |

Mean out-of-sample Sharpe −1.78. The loss SHRINKS out-of-sample (−4.55 →
−1.78): the regime boundary dilutes the anti-predictiveness, consistent with
the persistence shape below — early information decays toward zero.

## 3. Persistence — the regime-decay measurement

Segment correlations of rolling predictions vs forward returns:

| tape | seg1 | seg2 | seg3 | seg4 | seg5 |
|---|---|---|---|---|---|
| BTCUSDT w2000-c24 | +0.024 | +0.089 | +0.065 | −0.004 | −0.011 |
| ETHUSDT w2000-c24 | +0.037 | +0.063 | +0.057 | −0.024 | −0.003 |
| BTCUSDT w4000-c48 | +0.038 | +0.099 | −0.001 | +0.016 | −0.051 |
| ETHUSDT w4000-c48 | −0.033 | +0.094 | +0.062 | +0.025 | −0.009 |
| GLD | +0.143 | +0.024 | −0.195 | −0.007 | — |
| AAPL | −0.002 | +0.107 | +0.048 | +0.000 | — |
| NFLX | +0.036 | −0.108 | −0.092 | −0.042 | — |
| SLV | −0.037 | +0.118 | −0.025 | +0.019 | — |

Crypto: uniform decay, skill peaks at segment 2 (~+0.09) and dies by segment
5. GLD: strongest segment-1 skill of anything measured (+0.143), then gone.
NFLX: noise throughout. The shape the whole system analysis predicted —
regime decay is the measured shape of death, not a hypothesis.

## 4. What the verdict means

F12 is closed. The ML-regime family at the 1h scale carries no tradeable
edge at any of the 16 measured cells, in or out of sample, and the cost
model is exonerated by counterfactual. What survives the autopsy is the
persistence evidence itself: segment-1/2 correlations of +0.06…+0.14 exist
and decay — the program's next families must either harvest faster than the
decay or live at horizons where decay is slower (the H-family daily-bars
bet). Both implications are already in the program document; nothing here
re-opens them.

The measurement infrastructure lessons landed in the same night: the
content-keyed rolling-prediction cache is now prefix-resumable (49× faster
re-entry after an ingest, exact bit-identity proven by contract tests), and
the ingest freshness watcher keeps the tape within the hour — without those
two, this measurement would have cost another full day per re-run.
