# The permutation test's power asymmetry — measured, not theorized

Date: 2026-11-26, late evening. Trigger: corrected F7 measures 27/28 cells
positive in-sample (mean +0.59) yet not one permutation p below 0.05,
while the pre-fix noise-trading F7 produced 6 "validated" survivors — a
paradox that cannot be about the strategies and must be about the test.

## What the test actually measures

`monte_carlo_test` permutes the DOLLAR PnL sequence and recomputes Sharpe
from per-trade fractional returns (diff / running equity). Because each
trade's return denominator is the equity at its position in the sequence,
ordering changes which trades get amplified: losses early (small equity)
are huge negative returns, wins late (large equity) are tiny positive
ones. The null hypothesis is **ordering luck**, never **entry luck** —
permuting cannot touch when or why entries fired.

## The power asymmetry, both directions measured

1. **Volatile-path strategies (noise-trading continuation, pre-fix F7)**:
   ordering matters enormously — the same PnL sequence rearranged produces
   wildly different Sharpes. A lucky original ordering beats most
   permutations → small p → "validated". The pre-fix F7 survivors were
   exactly this artifact: ordering luck, certified as edge.
2. **Steady-edge strategies (corrected F7/F8)**: ordering matters little —
   trades are uniform, every permutation resembles every other. The
   original ordering cannot dominate the distribution by construction →
   flat p → "rejected" even when the edge is real. The better the
   strategy's consistency, the more certainly the test fails it.

The gate thus systematically certifies volatility-luck and rejects
consistency — the precise inversion of its purpose.

## Evidence in this evening's ledger

- Pre-fix F7 (noise entries): p as low as 0.000-0.005 on 6 cells — all
  void now, all ordering artifacts.
- Corrected F7 (real entries): 27/28 positive, p 0.10-0.86 everywhere.
- Corrected F8 (gated): same shape.
- F5 corrected: 0/29 positive — permutation irrelevant, honestly dead.

## What the program does about it

Nothing in this document weakens the gate retroactively: every verdict
already written stands as written. The forward discipline:

1. **Permutation p stays as ONE signal** but loses its veto for cells whose
   permutation dispersion is structurally flat — detectable in the payload
   itself (simulated_sharpe_std near zero relative to the mean).
2. **Phase B becomes the arbiter it was designed to be**: out-of-sample,
   rails-on, one serial run. Ordering luck cannot survive it — the OOS
   window has no memory of the in-sample ordering — while a real edge can.
   The corrected F7/F8 leaders' phase-B rows are the program's first test
   of this doctrine, measured the same evening.
3. A proper replacement test (entries-vs-random-entries at matched trade
   count, or stationary block bootstrap) is M-research work, declared here,
   not yet built — the multiple-testing budget rules make ad-hoc test
   swaps exactly the curve-fitting the program exists to prevent.
