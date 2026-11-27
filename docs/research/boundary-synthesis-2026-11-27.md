# The boundary synthesis — what the program can resolve, and what actually died

Date: 2026-11-27. Status: **structural synthesis complete, verdict section
PENDING** — the G/H phase-A sweeps are not yet run (compute deferred by
owner decision); this document is written so those verdicts land in a
frame that already exists, never retrofitted. Where a section depends on
unrun measurements it says so in-line. Companions:
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

## 5. What the pending verdicts will decide — pre-registered reading

Declared before the G/H sweeps run, so the reading cannot bend to the
outcome:

- **G (funding-carry, perp truth):** the one mechanism in the zoo that is
  a transfer, not a price forecast. Pass at power → the first validated
  edge candidate of the corrected era, and phase B one-shot. Fail → the
  timing hypothesis dies; pure hold-through-settlement carry becomes a
  separate smaller declaration. `untestable` across the grid → the 4h
  resolution was wrong, the family re-designs at 1h with a larger window.
- **H (multi-week trend, daily):** the literature's most replicated
  anomaly at the program's best-powered horizon. Pass anywhere → the
  program's center of gravity moves to slow capital-compatible trading
  (Arc B evidence). Fail at crypto AND GLD → time-series momentum is dead
  at retail cost structures in this data, and the closure document's
  strongest section writes itself.
- **F12 (rolling retrain):** the regime-decay experiment — death at the
  boundary is either adaptation lag (retraining fixes) or structural
  (nothing fixes). Its sweep is queued behind the owner's compute budget.

## 6. What this synthesis deliberately does not say

It does not claim the search is over: G/H/F12 are unrun. It does not
rescue the 13 underpowered rows: indeterminate means indeterminate. It
does not treat the venue repair as a reprieve for dead families: their
mechanisms were tape-insensitive at measurement scale, and re-running
them on perps is a new declaration with new budget, never a free retrial.
The boundary question is narrower than it was yesterday and wider than
anyone hoped — which is what an honest instrument costs.
