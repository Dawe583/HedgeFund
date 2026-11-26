# Regime architecture — the day-one synthesis

Date: 2026-11-26. Companion to the three family verdicts written today
(f1, f5, f7). This document is not a family verdict; it is the design
consequence of reading them together, and it constrains every family
declared after this date.

## The finding, restated without ceremony

Three independent measurements today converge on one sentence: **in this
market, edge presence is regime-dependent, and regime membership is not
stationary across a 3-year tape.**

- F1 (4h trend): momentum ordering significant in-sample (basket
  permutation p 0.015) — an edge that exists — while its Sharpe interval
  cannot clear zero. Trend exists; its harvest is volatility-dominated.
- F5 (1h mean-reversion): gross-negative at 48/48 cells. Fading
  extensions is unconditionally wrong in-sample.
- F7 (1h continuation): statistically validated in-sample at p ≤ 0.032
  with 380–400 trades — then the signal frequency itself collapses 40×
  out-of-sample. The edge did not degrade; it **stopped occurring**.

The F7 shape is the load-bearing one. A parameter-fit artifact degrades
gracefully out-of-sample; a regime edge disappears. What disappeared is
the market state in which 1h extensions continue — and that state had
persisted long enough in-sample to produce a statistically impeccable
validation. The protocol did not fail: it measured exactly what was
there, and it killed exactly what died. What must change is what we ask
candidates to be.

## The architectural consequence

A candidate can no longer be a signal function alone. It must be a
signal function **plus its own regime detector** — a mechanism that
measures, online and causally, whether the edge it exploits is currently
on. The detector is part of the candidate's claim and shares its budget
and verdict. Three consequences follow:

1. **The regime object is edge-specific, not tape-specific.** F5's
   failure proved tape classification (trending/ranging) insufficient —
   the filter changed nothing because continuation did not care about
   tape shape. The question is never "what regime is the market in" but
   "is the mechanism this candidate exploits currently paying". Those
   are different objects: the first is observable in prices, the second
   only in the edge's own recent performance — a trailing, causal,
   honest measurement like the realized edge decay of the strategy's
   own signal outcomes.
2. **Validation must measure regime stability, not just edge presence.**
   Walk-forward is the crude version already in the gate (5 windows).
   The F7 shape — 4/5 profitable in-sample windows then total death —
   shows five windows in 23 months is too coarse to see regime
   membership changing. Candidates must report edge-half-life: how
   quickly the mechanism's measured performance decays out of its best
   window. A validation protocol upgrade, not a weakening — declared
   here before implementation, per the program's rule.
3. **Production truth already implies this.** Rails kill a live strategy
   at 12% drawdown — a crude edge-death detector bolted on after the
   fact. The regime-aware candidate internalizes that measurement: it
   stops signaling when its edge is off rather than being killed for
   trading through its own death. The rails remain as the hard backstop;
   the candidate stops needing them.

## What this is NOT

Not a mandate to fit regime parameters per family — the detector
mechanism is declared per candidate, parameterized inside the same
budget, and validated by the same gate. Not a retreat to regime-switching
meta-models: the candidate stays one mechanism with one honest on/off
measurement. And not a license to resurrect dead families: F7 is dead
as declared. A regime-aware continuation candidate, if one is ever
written, is a NEW candidate in a NEW family with its own budget — and
the count in the ledger keeps growing honestly.

## Immediate consequences for the declared families

- **F4 (breakout)** inherits continuation's regime question wholesale:
  breakouts are extensions by another name. Its budget of 20 is unchanged,
  but the family is unlikely to mean anything until the regime object
  exists — re-ordered behind the measurement work.
- **F2 (funding carry)** is the family least exposed to this problem:
  carry is a transfer, not a price forecast, and its edge existence is
  structural rather than regime-conditional. It moves up the work order.
- **F3 (cross-sectional)** is partially protected by construction:
  ranking is self-normalizing across the basket even when the tape's
  character shifts. Unchanged in priority.

## The measurement work itself

Before the next family runs, one piece of machinery: an edge-decay
report inside the validation payload — walk-forward extended from a
count of profitable windows to per-window Sharpe series with the decay
shape visible, so that a candidate whose edge concentrates in one
regime window reads as what it is. Small, honest, and it changes what
the gate can see. Declared here, in writing, before implementation.
