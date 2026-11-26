# Research program — day 1 synthesis

Date: 2026-11-26. One day, seven families, two methodology incidents, and
the first honest shape of what this tape does and does not pay for.

## The measured scoreboard (corrected measurements only; pre-fix rows void)

| family | cells | in-sample mean | positive | phase B (OOS 13mo) | verdict |
|---|---|---|---|---|---|
| F1 momentum | 40+ | slow dead, thin fast | — | — | closed |
| F2 funding carry | 16 | −2.41 | 0/16 | — | closed |
| F3 cross-sectional | 12 | −0.56 | 2/12 noise | — | closed |
| F4 vol-breakout | 16 | +0.09 | 11/16 | — | closed: long beta, not edge |
| F5 mean reversion | 48 | −2.58 | 0/48 | — | closed, confirmed twice |
| F6 catalog control | 4 | −5.9..−6.9 | 0/4 | — | closed, tape-independent |
| F7 continuation | 48 | +0.35 | 38/48 | −0.58/−0.69 | closed: ungated dies OOS |
| F8 regime-cont | 16 | +0.49 | 14/16 | mixed, mean −0.46 | closed: gate helps, insufficient |

## The three structural findings

**1. F5's double death defines the tape's direction.** Mean reversion died
at −2.00 in the buggy measurement and −2.58 in the corrected one — fading
extensions loses unconditionally, so continuation is the tape's truth at
1h. Every family built after this knows which direction is noise.

**2. Continuation exists but decays.** Corrected F7: 38/48 positive
in-sample, mean +0.35 — the edge is real in-sample. Out-of-sample: dead.
The decay is measured in window series: in-sample [+2.9, +2.2, +3.1,
−0.6, +2.2] — strength with one dead window — then uniform OOS death.
Edges here are regime-conditional, not permanent.

**3. The regime gate measurably helps and does not suffice.** Same entries,
same exits, only the ER gate differs: ungated OOS −0.58/−0.69, gated OOS
+0.27/+0.04 on the matched ETH cells — a measured +0.7-0.9 Sharpe of
regime-filtering value. But the full F8 OOS distribution is mixed (mean
−0.46, 7/18 positive): the efficiency ratio at 16-36 bars is too crude a
regime measure, or the regime that matters is not the one ER sees.

## The two methodology incidents — the day's most valuable output

1. **dev_z scaling bug**: three bots measured deviation thresholds 100x
   tighter than declared (atr_pct double-divided). Found because byte-
   identical outputs across entry_dev variants are impossible when the
   parameter binds. F5/F7/F8 verdicts void, re-measured, ledger keeps both.
   Lesson now encoded: instrument parameter binding before trusting grids.
2. **Permutation power asymmetry**: the gate certifies volatile paths
   (ordering luck) and rejects steady edges (ordering-invariant by
   construction). The pre-fix F7 "survivors" were ordering artifacts; the
   corrected positive families can't pass their own gate. Doctrine:
   permutation p loses its veto when permutation dispersion is structurally
   flat; phase B is the arbiter. Replacement test (random-entries null) is
   declared research work, not yet built.

## What day 2 owes

- The regime question is THE question. Candidate instruments beyond ER:
  funding-crowding state (data already ingested), cross-sectional
  dispersion state (machinery exists), volatility-regime state.
- The random-entries permutation replacement — without it, positive
  in-sample families cannot be honestly certified or honestly killed.
- Nothing trades, nothing goes near paper: no candidate has passed the
  gate out-of-sample, and the program's own measurement machinery caught
  two ways it could have lied to itself in a single day.
