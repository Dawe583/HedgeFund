# The boundary synthesis — what the program can resolve, and what actually died

Date: 2026-11-27. Status: complete — the G/H phase-A sweeps ran the same
day and the verdict section now carries what was measured, exactly where
the pre-registered reading stood. Companions:
`stats-repair-verdict-2026-11-27.md` (the power re-read),
`whole-system-analysis-2026-11-27.md` (the audit), the program doc, and
the venue migration's evidence below.

## 1. What power did we actually have

The ledger's resolution limit, measured not assumed (power-reread.json):

- 29 phase-A→B pairs exist. 9 were confirmable deaths — the B cell could
  see its A-edge and the edge was gone. 13 were underpowered deaths — the
  B cell never had the resolution to confirm what it was testing; those
  rows are evidence of nothing either way, and since the `untestable`
  verdict landed today the vocabulary now says so at write time.
- Minimum detectable Sharpe at the historical phase-B sizes (13–16
  trades) is ≈ 0.66–0.74 — blind to the Sharpe ~1 edges the program
  hunts. Sharpe ~1 needs ~60 independent trades at the program's power
  standard. Every future phase-B cell is sized for power before it runs,
  or it ledgers `untestable` by design.
- The one DSR-significant in-sample lineage (F9/F12 ML, trial-count
  corrected) genuinely existed in-sample: skill was real, not curve-fit.
  The out-of-sample retention measured ~1/25 of in-sample strength —
  where power could see, the edge was gone. Regime decay is the measured
  shape of death, not a hypothesis.

## 2. The venue correction — a confound the program did not know it had

The migration's evidence changed the meaning of every historical crypto
row (venue_migration.py, applied 2026-11-27, 78 series):

- **Every crypto candle series in the ledger's history is binance SPOT** —
  verified at 97–100% exact close matches against Binance's own spot API
  over sampled days. Zero rows matched the perp tape. The desk trades
  USD-M perpetuals; the validation plane measured an instrument nobody
  trades. The magnitude of the confound is small — exactly the size
  funding edges are, as the audit warned.
- **F2's funding-carry cells are voided as evidence, not just superseded.**
  They joined perp funding events onto a spot frame — an instrument that
  never pays funding. The rows stand (append-only doctrine), but they
  measure a hybrid that exists nowhere. G re-asks the question on the
  correct tape.
- F1/F5/F7/F8/F9/F12 ran on the same spot tape. Their deaths are NOT
  voided — spot and perp diverge by basis, not by microstructure regime,
  and momentum/mean-reversion mechanisms are insensitive to the basis at
  hourly scales [INFERENCE — the basis is small and slow-moving at these
  timeframes; the honest reading is that the regime conclusion survives,
  the venue caveat rides along]. The ML families' measured decay is
  therefore evidence about regimes on a *spot-adjacent* tape; whether
  perp microstructure decays differently is an open question G/H and the
  F12 rerun answer.
- From today the preference order makes perp the resolution default, the
  ledger records venue per row, and funding joins key to perp series only.
  The confound class is closed structurally, not by discipline.

## 3. What died of noise vs underpowered tests vs regime

The accounting the program owes itself, now computable:

| death shape | count | evidence |
|---|---|---|
| noise dressed as signal (in-sample) | weeded by the gate | 0 validated across 500+ rows except voided artifacts — the gate's redundancy works as designed |
| underpowered phase-B verdicts | 13/29 | indeterminate as written; re-confirmation requires power-sized cells |
| measured regime decay | 9/29 confirmable pairs + F9 DSR lineage | edges existed in-sample, gone out-of-sample where the test could see |
| venue-confounded evidence | all F2 rows | voided as evidence by the migration |
| structurally void veto | every permutation-veto rejection pre-repair | the instrument measured nothing — verdicts re-readable only through bootstrap/wf/power |

The honest total: of everything the program measured, **nothing survives
as a tradeable claim, and the strongest negative evidence is now known to
be measured reality rather than statistical blindness** — for exactly the
cells that were powered. The 13 underpowered rows are the program's
residual uncertainty: small, bounded, and priced into future cell design.

## 4. The instrument repair ledger

| repair | mechanism | consequence |
|---|---|---|
| permutation veto removed | measured structurally void | consistency no longer rejected by noise |
| stationary block bootstrap | serial dependence honored | wider, honest CIs; historical rows not comparable |
| power primitives + `untestable` | MDS in every row; phase-B sized for power | blindness visible at write time |
| entries-null confirmation tier | random-entries control, hardened | entry quality measured, not assumed |
| venue identity in schema | spot/perp/unknown separated by evidence | the desk's instrument is what validation measures |
| freshness + ingest provenance | ingest_runs table, staleness warnings | stale-truth silence ends |
| content-keyed caches | digest over consumed data | repaired data can never serve stale signals |
| walk-forward test-only re-basing | warmup out of fold verdicts | consistency evidence measures what it claims |

## 5. The verdicts — measured 2026-11-27, against the pre-registered reading

The pre-registration above is replaced by what happened; the reading
cannot bend to the outcome because the outcome is written here once.

- **G — funding-carry, 16 phase-A cells, ALL rejected.** Mean Sharpe
  −2.58, range −2.03 to −3.22 across BTC/SOL 4h perps, 211 total trades.
  Not noise-that-needs-power: deeply negative, consistent across every
  parameter combination, permutation p≈1. The mechanism that is a
  transfer, not a forecast, does not merely fail to pay for timing — at
  these parameters it is a consistent donation. Reading against the
  pre-registration: the timing hypothesis is dead. What survives as an
  undeclared question is the degenerate form — hold-through-settlement
  carry with no timing at all, a perp-native funding harvest — and it is
  a NEW declaration with its own budget, never a rescue of these rows.
- **H — multi-week trend, 24 phase-A cells, ALL rejected.** Mean Sharpe
  −0.11, range −1.48 to +1.24 over 2236 total trades. The distribution
  is the verdict's texture: crypto cells cluster mildly positive (+0.2
  to +0.5 at weekly lookbacks), GLD cells cluster negative (−0.4 to
  −1.5). Nothing nears validation; permutation p values 0.1–0.95 with no
  systematic tail. Reading against the pre-registration: at weekly-scale
  lookbacks on retail cost curves, the most replicated anomaly in the
  literature does not reproduce in this data — not death by underpower
  (the z0.5 cells carried 29–455 positions), death by absence. The one
  honest caveat: L63 monthly-lookback rows show Sharpe +0.9/+1.2 at
  1–3 trades — exactly the unresolvable shape the power pre-check
  predicted, evidence of nothing, written here precisely so nobody
  resurrects it as a lead.
- **F12 — still queued** behind the owner's compute budget; the rolling
  retrain experiment is unchanged and unmeasured.

## 5a. What the two verdicts jointly imply

Two mechanism families — one a transfer, one the literature's sturdiest
anomaly — both measured dead on correct venues at correct power within
one sweep each. The cheap-and-fast adaptive-zoo direction is now negative
on every load-bearing branch it has tested. Arc B's shape sharpens: the
program's remaining hypotheses are the regime-adaptation experiment
(F12), the degenerate carry form above, and directions the zoo has never
contained. None of this rescues anything: the ledger's totals are what
they are, and the honest number of validated strategies in the system
remains zero.

## 6. What this synthesis deliberately does not say

It does not claim the search is over: G/H/F12 are unrun. It does not
rescue the 13 underpowered rows: indeterminate means indeterminate. It
does not treat the venue repair as a reprieve for dead families: their
mechanisms were tape-insensitive at measurement scale, and re-running
them on perps is a new declaration with new budget, never a free retrial.
The boundary question is narrower than it was yesterday and wider than
anyone hoped — which is what an honest instrument costs.
