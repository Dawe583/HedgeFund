# Random-entries null — first blood, 2026-11-26 late evening

The replacement test declared in permutation-methodology-2026-11-26.md is
built and calibrated the same evening, and its first measurement is the
program's first positive evidence of entry-quality information.

## The instrument

`trading/validation/random_entries.py` — the matched control: same tape,
kernel, costs, sizing; same entry count, long/short mix, stop/tp
parameters and holding-period distribution; entries at uniformly random
bars. Entry quality is the ONLY degree of freedom that differs — the null
for "were the entries good?", which the ordering permutation can never
answer.

Calibration: a pure-noise candidate (random entries as the candidate
itself) measures p=1.0 against its own control — the instrument has no
false-positive bias. Two harness bugs found and fixed during construction:
the kernel's confidence_min veto (0.55) silently killed control entries at
confidence 0.5, and trade records carry direction under 'side', not
'direction'.

## First measurements (out-of-sample, 13 months, rails on, ETHUSDT 1h)

| cell | candidate Sharpe | control mean | p (n=50) |
|---|---|---|---|
| regcont-m2-r36-e2.0 | **+1.00** | −0.59 ± 0.84 | **0.02** |
| regcont-m4-r36-e1.5 | +0.27 | −0.76 ± 0.94 | 0.18 |

The m2-r36-e2.0 entries beat 49 of 50 matched random-entry controls. The
random-entry baseline itself is deeply negative (−0.59) — entries at
random on this tape lose to costs and regime noise, exactly as the
catalog control predicted. The candidate's positive Sharpe is not beta:
beta would show in the controls too.

## What this does NOT establish

- One cell, one symbol, one window — replication is running (BTC same
  window, ETH in-sample) and the count discipline applies: the family
  budget is spent, so further F8 variants are off-limits, but measuring
  the EXISTING cells deeper costs no budget.
- The control holds the position open for a drawn holding period with only
  protective exits — adaptive exit logic is part of the candidate's edge
  and is not isolated from entry quality here. The test answers "are the
  candidate's trade sequences better than random entries?", not "is entry
  timing alone the edge". That distinction matters for design, not for
  the gate's question.
- Nothing passes the production gate: permutation p stays flat, walk-
  forward consistency is weak, and M5 item 1 stands. What changed is
  WHERE the evidence points: the regime-gated continuation entries carry
  measurable information, and the instrument that can certify it now
  exists.
