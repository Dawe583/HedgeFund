# F12 phase A — all 8 cells rejected, and the death is directional, not cost

Date: 2026-11-27. The rolling-regime ML family (program amendment 2026-11-26,
budget 16 cells, 8 in phase A) completed its first honest measurement: every
cell rejected, zero errors, every row resolvable at its trade count.

## The verdicts, measured

| cell | symbol | trades | sharpe | perm-p | resolvable at |
|---|---|---|---|---|---|
| mlroll-w2000-c24 | BTCUSDT | 641 | -5.49 | 1.00 | ±0.098 |
| mlroll-w2000-c24 | ETHUSDT | 601 | -3.74 | 0.99 | ±0.101 |
| mlroll-w2000-c48 | BTCUSDT | 647 | -6.12 | 1.00 | ±0.098 |
| mlroll-w2000-c48 | ETHUSDT | 600 | -4.21 | 1.00 | ±0.102 |
| mlroll-w4000-c24 | BTCUSDT | 559 | -5.39 | 1.00 | ±0.105 |
| mlroll-w4000-c24 | ETHUSDT | 490 | -3.07 | 0.92 | ±0.112 |
| mlroll-w4000-c48 | BTCUSDT | 546 | -6.00 | 1.00 | ±0.106 |
| mlroll-w4000-c48 | ETHUSDT | 491 | -2.38 | 0.86 | ±0.112 |

Mean Sharpe -4.55, range -6.12 to -2.38. Walk-forward consistency: 0/5 windows
profitable in six cells, 1/5 in two. Permutation p-values near 1.0 — random
orderings of the same trades do BETTER than the observed ordering almost
always, which is what a systematic loser looks like, not what noise looks like.

## The decomposition that matters

Before the verdicts were written down as cost casualties, the zero-cost
counterfactual was measured: same cached predictions (content-keyed artifact,
the exact series the sweep measured), same entries, same exits, the kernel's
cost model switched off. On the in-sample tail of BTCUSDT w2000-c24:

- real costs: sharpe -3.67, return -12.21%
- zero costs: sharpe -3.59, return -12.19%

The round-trip burden (~37 bps, measured against the cost curve) explains
almost nothing. The strategy loses because its entries precede adverse moves:
the rolling momentum model's high-z predictions are anti-predictive out of the
training window. In-sample. The mechanism candidates, written after the
measurement and marked as candidates, not findings:

1. Momentum-regime inversion: the model fits trend continuation inside each
   rolling window, and crypto's hourly tape pays mean reversion at exactly the
   horizons the features measure. The embargo is honest; the learned sign is
   wrong for the regime the predictions land in.
2. Expanding z-score drift: entry thresholds are relative to an expanding
   prediction distribution, so entries cluster where the distribution shifts,
   not where the signal is strong — measured z-range on the tail was -2.63 to
   +3.43, wide enough for the threshold to mean different things in different
   quarters.

## What this does NOT license

An anti-predictive signal inverted is a predictive signal — and grabbing it
now would be the classic refit-after-measurement: the inversion was measured
on the same tape it would trade. Per the program's discipline (a parameter
combination once measured dead stays dead, a new direction needs a new
declaration and a new budget), the inverted-momentum direction is a candidate
for the NEXT amendment — declared before measurement, powered before compute —
never a quiet re-run of these cells with the sign flipped.

## Persistence and phase B

The overnight chain continues: persistence measurement (rolling out-of-fold
correlation per quarter-segment, the array_split bug fixed mid-run — the first
honest number: GLD decays +0.143 → -0.195 front to back) and phase B on the
regime-boundary question. Both run under the repaired instrumentation. Their
verdicts land in the ledger as separate rows; this document is the phase-A
record only.
