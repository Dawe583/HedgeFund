# Research program — day 2 plan, written at day 1's close

Date: 2026-11-26 late evening. Everything here is declared BEFORE the
measurements it describes — the program's discipline does not relax because
day 1 ended with a tantalizing cell.

## What day 1 left on the table, honestly weighed

The regcont-m2-r36-e2.0 ETH cell: +1.00 Sharpe OOS, random-entries null
p 0.02 (n=50), replication ETH in-sample p 0.04 — and BTC out-of-sample
p 0.56, i.e. NO replication across symbols. Selection-adjusted, a best-of-
18 cell hitting a nominal 0.02 has a luck probability around 0.30 under
the null. The honest verdict: tantalizing, unproven, possibly noise. The
regime-gate VALUE measurement (+0.7 to +1.6 Sharpe on matched cells) is
the solid finding; the cell itself is a lead, not an edge.

## Day 2 work, in order

1. **The regime-instrument bake-off** (the lead worth the most): three
   candidate regime instruments beyond the efficiency ratio, measured as
   pure measurement, no new strategy family:
   - funding-crowding state: is the tape's continuation edge conditional
     on funding extremes? Data already ingested (10 symbols x 1095d).
   - volatility regime: rvol state vs forward continuation quality.
   - cross-sectional dispersion state: machinery exists from F3.
   Each measured as: bucket OOS bars by the instrument's state, compare
   the F8 continuation entries' per-trade outcomes across buckets. No new
   candidates, no budget spent — pure measurement of the existing ledger
   rows' trades, recomputed deterministically.
2. **The honest significance path**: if any instrument separates, the
   corrected cell design is a NEW family (F9) declared before sweeping,
   budget 20, never a retcon of F8. If nothing separates, F8's lead is
   dead and the program's directional chapter closes honestly.
3. **Ledger hygiene**: dedupe the repeated evaluation rows' reading
   (ledger keeps them — the count is the point — but analysis queries
   must read distinct cells; the two identical m4 rows tonight read as
   one cell, not two).
4. **Long-blackhole probe verdict** lands in flap-probe-2026-11-26.md —
   operations evidence, independent of the research program.

## What day 2 does not do

- No production/paper movement: M5 item 1 stands, nothing has passed the
  gate out-of-sample with rails on, and the null-test evidence is a lead
  under selection effect, not a certification.
- No budget creative accounting: F8 is closed; continuation with a better
  regime instrument is a new family declared before it is measured.
- No weakening of any gate: the permutation test's veto loss is limited
  to structurally-flat dispersion exactly as documented, and the random-
  entries null joins the evidence, never replaces the discipline.
