# Alpha bench — the vendored zoo measured on our universes

Date: 2026-11-26. Methodology: the Vibe-Trading CSI 300 study's own filter
(mean IC > 0.02, t-stat > 2, positive share >= 55%) applied to rank IC
against forward returns, honestly adapted — the bench measures what alphas
do on OUR tape, which is the only question this program asks.

## Crypto 10-universe, 4h bars, horizon 6 (= 1 day forward)

**292 measured | 14 alive | 14 reversed | 174 dead | 90 untestable.**

The 28 significant survivors cluster in five themes, and their signatures
(cross-sectional mean alpha per bar) are decorrelated — pairwise
correlations mostly below 0.2, one genuine cluster around gtja191_030/081/097
at 0.6-0.8. This is a library, not one signal in five disguises.

Top survivors by |IC|:

| alpha | verdict | mean IC | t-stat | pos share | theme |
|---|---|---|---|---|---|
| gtja191_159 | reversed | -0.081 | -14.0 | 0.43 | momentum |
| gtja191_153 | alive | +0.079 | +15.3 | 0.58 | momentum |
| gtja191_173 | alive | +0.078 | +15.3 | 0.58 | momentum |
| gtja191_097 | reversed | -0.078 | -15.4 | 0.43 | volatility,volume |
| gtja191_126 | alive | +0.078 | +15.2 | 0.58 | reversal |
| gtja191_093 | alive | +0.078 | +15.2 | 0.58 | microstructure |

Caveat stated plainly: mean IC 0.08 is a RANK correlation across 10 assets.
Per-bar cross-sectional ranks of a small universe carry limited information,
and IC is not PnL — the kernel verdicts in F10 are the honest test of
whether any of this survives costs, stops and gates.

## Equities+metals 6-universe, 1d bars, horizon 1

**292 measured | 0 alive | 0 reversed | 202 dead | 90 untestable.**

Zero significant alphas. The honest reading is a universe-power limit:
cross-sectional ranks of SIX assets cannot carry enough information per
bar for this instrument — a rank of 6 is nearly noise. The verdict is
"unmeasurable on this universe", NOT "alphas are dead in equities".
Widening the equity universe is the fix if equities matter to the program;
the data plane already supports it.

## The untestable 90

Mostly gtja191 alphas requiring volume-weighted intraday structure or deep
windows our 4h tape cannot supply, plus a handful with factor-model
dependencies. They are not failures — they are unmeasured, and the bench
says so instead of guessing.

## What happens next

F10 (declared in program-2026-11-26 before its first sweep) takes five
decorrelated survivors into the kernel. The bench answers "does the alpha
rank the universe informatively"; the kernel answers "does any of that
survive execution reality". These are different questions and the program
has been burned before by confusing them.
