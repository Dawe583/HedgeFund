# G/H re-read under the synthetic-path tier — the positive cells examined

Date: 2026-11-28. Companion to `boundary-synthesis-2026-11-27.md`, whose
"measured dead" verdicts for G and H stand. This note exists because the H
scoreboard is not uniform: several cells carry positive Sharpe, and the new
synthetic-path Monte Carlo tier (built the same day, `synthetic-mc-tier-2026-11-28.md`)
answers the question those cells pose — is the positive reading regime-fragile
evidence of life, or noise dressed as one? Written after measurement, against
rows written after the stats repair (2026-11-27 20:04–20:08 UTC, repair landed
10:33 — the instrument these rows were read on is the corrected one).

## 1. What the H ledger actually contains

| cell | sym | trades | sharpe | mds | reading |
|---|---|---|---|---|---|
| h-trend-L63-e1.0-crypto | BTCUSDT | 3 | +1.24 | 1.44 | unresolvable — cannot see its own edge |
| h-trend-L5-e1.0-crypto | ETHUSDT | 27 | +1.00 | 0.48 | resolvable-positive |
| h-trend-L63-e0.5-crypto | BTCUSDT | 18 | +0.92 | 0.59 | resolvable-positive |
| h-trend-L5-e0.5-gld | GLD | 531 | −1.48 | 0.11 | measured dead, decisive n |
| h-trend-L10-e0.5-gld | GLD | 382 | −0.87 | 0.13 | measured dead, decisive n |
| h-trend-L21-e0.5-gld | GLD | 259 | −0.61 | 0.16 | measured dead, decisive n |

Two structural facts before any statistics: the positives live exclusively
in the SHORT lookbacks (L5–L21) on crypto — not in the multi-week design the
family is named for — and GLD, the family's declared prior, is dead with
large n in every configuration. The family as declared measured nothing. The
question is only whether the short-lookback readings are a signal or the
grid's noise floor.

## 2. The generalization measurement

32 synthetic paths per cell, stationary bootstrap mean block 15, full kernel
per path, daily bars:

| cell | observed | ensemble mean | p05…p95 | frac pos | p-gen |
|---|---|---|---|---|---|
| h-trend-L5-e1.0-ETH | +1.00 | +0.35 | −0.97…+1.42 | 0.69 | **0.21** |
| h-trend-L63-e0.5-BTC | +0.92 | −0.10 | −1.49…+1.00 | 0.50 | **0.12** |

Reading: both cells sit inside their own ensemble's noise. A fifth to a
tenth of the paths-that-never-happened produce Sharpe as good as the
observed one — with zero edge by construction. The positives are
indistinguishable from the distribution's ordinary right tail. Combined with
the same-tape gates they already failed (min-trades, bootstrap CI below
zero), the honest verdict is: **not evidence of life — evidence of an
underpowered grid whose noise floor includes these values**.

## 3. What survives, honestly

Not nothing — but what survives is a question, not an edge. The ensemble
mean for L5-ETH is +0.35: fast crypto trend-following on daily bars is
positive on average across unseen paths. That is the regime-conditional
weak signal the persistence measurement (skill peaking early, decaying)
predicts should exist, and it is exactly the strength the current grid
cannot resolve. Pursuing it means a NEW declaration — a redesigned family
with entries frequent enough to beat the 60-trade power bar — not a
reinterpretation of this one. The program's discipline is explicit: no
reinterpretations after measurement.

## 4. G-funding-carry — nothing to re-read

Every G cell is deeply negative (Sharpe −2.03…−3.22), 0/5 walk-forward
windows profitable, all resolvable. Funding carry as designed pays the
transfer instead of collecting it. No positive cell exists to examine; the
tier has nothing to add. Death measured, case closed.
