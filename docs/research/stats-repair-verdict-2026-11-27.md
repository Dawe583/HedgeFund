# Statistics repair + the boundary question answered — verdict

Date: 2026-11-27. The first arc-A work: the statistical instrument
repaired, then the ledger re-read under the corrected instrument. Pure
mining, zero sweep compute. Every number below from
`scripts/power_reread.py` over the append-only ledger (524 rows) —
`docs/research/power-reread.json` carries the per-cell detail.

## What was wrong with the instrument, now fixed in code

1. **The permutation-Sharpe veto was structurally void, not just
   inverted.** Calibration measured it directly: per-trade Sharpe is
   permutation-invariant except through compounding/ruin — simulated
   dispersion is ~zero for EVERY cell, steady or lumpy (std/mean ratio
   0.002–0.003 in both). The veto was noise in both directions: it
   certified the voided devz-era F7 artifacts and rejected genuine
   consistency. Removed entirely (`research.py` `gate_stats`); the
   statistic stays in payloads as a measurement, drawdown-path
   permutation remains as tail-risk evidence.
2. **Bootstrap was iid where the tape is serially dependent.** Volatility
   clustering at hourly granularity means iid resampling tightens the CI
   falsely. Replaced with Politis–Romano stationary block bootstrap,
   mean block 20 bars (`validation.py`). Every future CI is wider and
   more honest than the ledger's historical ones.
3. **Power analysis existed nowhere.** Added `min_detectable_sharpe(n)`
   and `power_verdict` (`research.py`) — SE ≈ 1/√n normal approximation,
   one-sided α .05, power .8, declared optimistic in every direction.

## The boundary question, answered by mining

29 phase-A→B pairs exist in the ledger. Under corrected power:

| measure | count | reading |
|---|---|---|
| confirmable deaths (B-cell could see the A-edge, edge gone) | 9 | **measured regime decay** |
| underpowered deaths (B-cell blind to its own A-edge) | 13 | indeterminate — neither death nor life |
| DSR-significant in-sample edges (trial-count corrected) | 1–2 | the edge was real in-sample |

**The in-sample edges were real, not curve-fit.** The top DSR rows are
the F9 ML cells (BTC IS +2.88 dsr .95, ETH IS +2.71 dsr .95) and they
hold up under trial-count correction — in-sample skill genuinely existed.

**The out-of-sample collapse is measured, not imagined.** The same cells
dropped to +0.08/+0.11 OOS — retention of roughly 1/25 of in-sample
strength in tests that were powered to see half of it. Where power was
confirmable, the edge was gone. The wall is real; what died at it is
now known precisely: edges that existed in-sample and decayed, not
measurement artifacts. The regime question survives as the program's
central question — now with the evidence shaped correctly.

**13 of 29 phase-B verdicts were uninterpretable as written** — the cells
never had the power to confirm their own edges. Their ledger rows stand
(honesty doctrine), but they are evidence of nothing either way, and the
power-reread file is the machine-readable correction layer. Any future
phase-B design that cannot reach its MDS line is a wasted sweep before
it starts: the budget arithmetic now has to clear the power bar first.

## What this changes for the program

- Phase B cells must be sized for power: expected trades × MDS against
  the in-sample edge, before the sweep starts. Cheap cells are noise
  factories.
- The F9/F12 lineage carries the only DSR-significant in-sample skill
  in the program — the overnight F12 rolling-retrain sweep (running as
  `scripts/f12-overnight.sh` when launched) is now unambiguously the
  right experiment, because the premise it tests (regime decay vs
  retraining) is exactly the measured shape of death.
- Re-sweeps under the repaired gate will produce different verdicts than
  the historical rows: wider CIs, no permutation noise. Historical rows
  stand as written; new rows are not directly comparable, and that is
  the honest cost of a repaired instrument.

*Methodology caveats, declared: DSR uses normal skew/kurt defaults and
uniform trade spacing — a ranking instrument, not a verdict. Power uses
the normal independent-trade approximation, optimistic in every direction —
the real detectability floor is never lower than quoted.*
