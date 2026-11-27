# Whole-system analysis — five independent audits, one synthesis

Date: 2026-11-27. Method: five parallel independent audits over the same
HEAD (1882d7b), each read-only, each citing file:line — strategy landscape,
trading core, research methodology, data infrastructure, product surface —
plus a full knowledge-graph rebuild (4,979 nodes, 10 layers, 919 files;
`.ua/knowledge-graph.json`). This document is the synthesis: where the
audits agree, the finding is load-bearing. Where they don't, the
disagreement is recorded honestly.

## 1. What the system is, measured

An institutional-grade evidence pipeline with zero evidence of edge
flowing through it: ~38k LOC of trading code in 48h, 524 ledger rows, 11
dead families, an honestly empty paper desk, mandate machinery with zero
audit rows, and the best-documented negative-results corpus in retail
quant. The knowledge graph confirms the shape: 300 nodes of alpha-factor
zoo, 228 test files, a trading-desk layer that is structurally complete
and operationally unexercised.

## 2. Findings the audits converged on — load-bearing

### F-1. The "regime wall" may be a statistical artifact, not a market fact

The program's central mystery — everything dies exactly at the
in-sample/out-of-sample boundary — has never been subjected to power
analysis. Phase B cells carry 13–16 trades; a true Sharpe ~1 edge needs
~60+ independent trades for 80% power at one-sided 5%. The pipeline is
incapable of confirming realistic edges at the boundary *by construction*.
"Regime decay" and "statistically invisible" are currently
indistinguishable in the ledger, and the program has been spending family
budgets to measure the difference with an instrument that cannot see it.
This is the single most consequential open question: the program may have
been correctly measuring noise, or incorrectly burying edge. Nobody knows.

### F-2. The permutation veto is structurally inverted and still active

`permutation-methodology-2026-11-26.md` proved with ledger evidence that
the ordering-permutation test certifies ordering-luck and rejects
steady-edge consistency — the precise inversion of its purpose. The
methodology doc said the veto should be lost for flat-dispersion cells.
**No code implements this.** `monte_carlo_test` remains a veto gate in
`gate_stats` (`research.py:461`). The gate currently rejects exactly the
strategies the program is looking for.

### F-3. Spot and perp tapes share one primary key

Binance `/api/v3/klines` (spot), the Hyperliquid-perp fallback, and ccxt
`binanceusdm` (perp) all write the same `(symbol, timeframe)` key with no
venue column. Funding rates — perp events — are joined by timestamp onto
what may be a spot series. The desk trades perps; the validation may run
on spot. F2 (funding-carry) measured an edge whose venue identity is
ambiguous. Magnitude: small, exactly the size funding edges are.

### F-4. The kill-switch is a risk diary, not a risk system

Rails measure realized-only equity; unrealized PnL never moves the
kill-switch, the daily-loss rail, or drawdown (`kernel.py`/`rails.py` —
"honestly vacuous" in `rails.py:23-28`). A gap-through-stop week can blow
past the 12% kill-switch with every rail green. Additionally the trip
memory dies with the process: restart resets peak equity. For a system
designed to run unattended, both holes are real.

### F-5. `walk_forward` overstates every wf verdict in the ledger

Metrics are computed over warmup+test concatenated
(`backtest/engine.py:218-241`) — 500 warmup bars of in-sample equity
inside every "out-of-sample" fold. Strategies are never re-fit per fold.
Every `wf x/5` number in the ledger inherits the flaw; fixing it may
reverse borderline verdicts in either direction.

### F-6. Honesty is culture, not enforcement

Nothing in code: counts family cells against declared budgets, prevents
`validate_core` from being pointed at out-of-sample data interactively,
verifies declaration-before-measurement ordering, or hash-chains the
ledger. The discipline held in practice — genuinely rare — but the
program's central marketing claim ("enforced in code") is true of the
gate and false of the program around it.

### F-7. The most valuable artifact is invisible in the product

`cmd_predict` — the only forward-looking measurement the entire ML program
produces — exists only as terminal JSON. Zero endpoints, zero UI. The
product displays operational truth well and epistemic truth barely at all:
no search-ledger browser, no family scoreboard, no prediction track
record. Meanwhile the write endpoints (kill-switch!) are unauthenticated
localhost POSTs — fine at one machine, the first thing that breaks the
moment deployment topology changes.

### F-8. Caches that can serve stale truth silently

The alpha-signal cache is keyed `(module, symbols, timeframe)` with no
data component — a panel computed on pre-fix data feeds live signals after
re-ingestion, forever. Ten stale pickles already sit in `data/alpha_cache/`.
`ml_rolling` is position-keyed, not content-keyed: repaired holes of equal
length produce stale hits. No eviction, no freshness check anywhere in the
ingest path: a validation can run on a series that stopped updating weeks
ago and nothing notices.

### F-9. Uniqueness is real but narrow — and it is not alpha

Versus Vibe-Trading, Freqtrade/Jesse, QuantConnect/Lean: this system is
the only one with declaration-before-measurement as practice, an
append-only ledger where the count of failures is first-class evidence,
published negative results with incident doctrine, kernel parity with a
measured divergence budget, and a lifecycle no agent can write into. None
of that is copyable *as a track record* — the corpus compounds and cannot
be backfilled. But the code is copyable in a weekend, and no validated
edge exists. The honest verdict: the moat today is epistemic reliability,
not trading capability.

## 3. What this changes immediately

Ranked by value-per-effort, all independent of the edge question:

1. **Power-analysis gate on phase B** — before sweeping, compute minimum
   detectable Sharpe at the expected trade count; cells below 50% power
   record `untestable`, not `rejected`. This is the program-critical fix:
   until boundary power is quantified, the regime question is unanswerable
   and every family verdict carries an asterisk.
2. **Remove/repair the permutation veto** — implement the methodology
   doc's own rule in `gate_stats`. One afternoon; the gate stops
   systematically rejecting its target.
3. **Block bootstrap** — stationary bootstrap (mean block ~20 bars)
   replacing i.i.d. resampling; the tape is serially dependent and the CI
   is falsely tight.
4. **Deflated Sharpe per family** — Bailey/López de Prado DSR with trial
   counts from the ledger itself; converts budget discipline from prose
   into a statistic. Zero new compute — pure mining of existing rows.
5. **Venue separation in the candle schema** — `venue` column, perp
   klines as the trading truth, funding joins keyed to perp series.
6. **Mark-to-market rails + persistent kill-switch state** — the two
   risk-diary holes, both wiring rather than design.
7. **Content-keyed caches** — alpha cache keyed by data digest; eviction
   discipline; freshness check on `max(open_time)` before any validation.
8. **Fix `walk_forward` scoring** — test-slice-only metrics; re-fit hook.
   Then re-read borderline verdicts honestly.
9. **Budget enforcement in code** — `evaluate_candidate` flags/refuses
   cells past the declared budget; machine-readable budget table beside
   GRIDS.
10. **The predict surface** — endpoint + dashboard strip + persisted
    predictions scored at horizon close (the track-record instrument).
    ~3.5 dev-days, the single biggest product upgrade.

## 4. The three arcs — the giant plans

(Synthesized from the strategy audit; detail in the companion plan docs.)

**Arc A — Depth: answer the boundary question or close the program
honestly.** Fix the statistical instrument first (F-1/F-2/F-3 fixes, one
week), then re-read the ledger under corrected power — some deaths may
reverse. Then the two untried slow hypotheses (funding-carry with real
funding history; multi-week trend on 3y of daily). Then the decision: if
nothing survives corrected measurement, the program closes with the final
document — the search space, the budgets, the verdict — written in full.

**Arc B — Breadth: follow the measurement's own efficiency ordering.**
Gold showed the strongest ML skill (+0.083), equities the weakest — the
tape itself pointed. Daily-bar slow momentum on metals/rates/FX proxies
is the most replicated anomaly in existence, cheap in data, and compatible
with one person's life (no 24/7 desk). Risk: converges toward being a
worse QuantConnect; uniqueness drops.

**Arc C — Product: the corpus is the deliverable.** The negative-results
pipeline as a public artifact: the research journal, the toolkit extracted
standalone, the constrained-agent demo (researcher agent powered, its
hit-rate measured on the same ledger as the human's — the first
selection-bias-immune LLM research loop with receipts). Guaranteed-valuable
output regardless of the tape; reputational, not technical, moat.

**Recommendation: A first, because it is mostly in flight and its output
decides everything — then exactly one of B or C, never both.** If corrected
measurement finds nothing: the project is C, honestly re-branded. If it
finds something: the project is A, and C becomes an attention liability.
B only if the owner concludes the honest answer is "edge exists but not
in crypto intraday" — which the current evidence weakly already says.

## 5. The 90-day sequence (the operational giant plan)

**Weeks 1–2 — statistical instrument repair (Arc A, foundation).**
Permutation veto fix, block bootstrap, power gate, DSR, walk-forward
scoring fix. All in `validation/` + `search.py` — small diffs, existing
tests updated, no new subsystems. Then: ledger re-read under corrected
power — a mining exercise, zero sweep compute.

**Weeks 3–4 — data truth repair.** Venue column + migration, perp klines
as trading truth, content-keyed caches, freshness precondition in
`validate_core`, yahoo retry/validation harness, alpha-cache eviction.
The correctness surface stops lying before any new measurement depends
on it.

**Weeks 5–6 — the verdicts.** Re-sweep the two slow hypotheses under the
corrected instrument (declared G-families, capped budgets). Funding-carry
gets honest venue truth for the first time. Write the boundary synthesis:
what power did we actually have, what died of noise vs of underpowered
tests vs of regime.

**Weeks 7–8 — risk truth repair.** Mark-to-market rails, persistent
kill-switch, fill-model unification, cost-curve v1 (size/vol dependent).
Prerequisite for any future live decision — and for trusting the paper
engine's evidence at all.

**Weeks 9–10 — the product catches up.** Predict surface + track record,
ledger browser, family scoreboard, alert egress (one webhook), minimal
auth on write endpoints, live refresh discipline. The evidence room
(portal) is already live; the private dashboard gets the same epistemic
surface.

**Weeks 11–12 — the decision, written.** Either: a validated edge under a
corrected instrument → paper soak re-run properly, divergence budget
measured, M5 audit updated, capital question answered in writing. Or:
closure document — search space, budgets, power analysis, verdicts — and
the pivot decision A→C executed in the open.

**Deliberately NOT done in 90 days:** no new asset classes, no live-path
work beyond the existing mandate skeleton, no multi-user anything, no
options, no intraday equities data, no new agent capabilities beyond
powering the one researcher agent that exists.

## 6. Cross-cutting risks the audits named

1. **Scope explosion is already materializing** — 38k LOC/48h is
   AI-velocity output; the soak already failed its headline criterion and
   a runbook described a CLI that no longer exists. The doctrine "a rail
   that cannot explain itself is removed" must apply to the codebase
   itself: tables with zero rows and machinery with zero users get
   deleted or justified.
2. **The empty-roster trap** — the operational plane has never run under
   its intended load. Cheapest fix in the whole system: register a
   declared negative-control strategy (random entries) to paper as an
   instrumentation control, so veto tape, divergence, reconciliation, and
   lifecycle finally run against expectations known by construction.
3. **Free-tier data fragility** — the soak already demonstrated silent
   degradation; the strategy that finally validates must not depend on a
   feed nobody watches. Freshness monitoring is week 3–4 work for exactly
   this reason.
4. **Single-maintainer bandwidth** — the wealth OS tolerates neglect;
   the trading laboratory does not. Every addition must be justified
   against the deletion test.

*This document was synthesized from five independent subagent audits; the
full audit texts are the evidence and live in the session archive. Where
this file and the audits disagree, the audits win and this file gets
corrected.*
