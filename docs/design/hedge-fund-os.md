# Hedge Fund OS — Architecture Design

Status: accepted (spikes resolved 2026-11-25), pending owner review.
Date: 2026-11-25. Audience: the owner-developer.
Scope: joins what the HedgeFund repo (the Aurelio wealth OS), ScalpFX (paper
trading desk) and Vibe-Trading (research/validation lab) already are into one
system that can grow from wealth tracking through validated paper trading
toward a live-readiness audit — without ever skipping a gate.

This document decides architecture, not alpha. As ScalpFX's own documentation
states: neither current desk has positive expectancy. The system's honest
answer to that is not a better strategy — it is a pipeline in which a strategy
cannot reach capital without evidence. Everything below is in service of that
pipeline.

Both validation spikes resolved positive on 2026-11-25 (nautilus kernel,
viz libraries) — the design below reflects their findings; see §2 and
`.spikes/*/SPIKE-REPORT.md` for the measured facts.

---

## 1. What exists, measured (the ground this stands on)

Facts verified in the repositories on 2026-11-25. Where the design reuses a
component, the path is given.

**HedgeFund / Aurelio** (`/Users/dawe/Developer/HedgeFund`):
- Backend: FastAPI + SQLAlchemy/SQLite + Alembic (37 migration files), 123
  test files in `backend/tests/`. All writes through `crud`/`unit_of_work`;
  reads through routers.
- The architectural manifest `docs/how-aurelio-reasons.md` is binding for this
  design: anchor+events model, provenance on every number, the card
  confirmation gate ("the model proposes; you write"), stale-as-fingerprint
  (409 on changed dependencies), the adversarial chain (blind analyst /
  confidant / conditional revision / synthesis, `backend/app/chain.py`, 694
  lines), app-computed sizing (`backend/app/sizing.py`), ETF look-through, FX
  conversion rules, a read-only MCP server with SQLite-enforced `mode=ro`.
- Frontend: React 19 + Vite + Tailwind, single app
  (`frontend/src/components/`: Dashboard, Portfolio, Wealth, ChatPanel,
  Analysis, Watchlist…).
- `OpenTerminal/` in the repo root is a vendored foreign Express+Next.js
  market terminal: no integration, no shared data. Dead weight today.

**ScalpFX** (`/Users/dawe/Developer/ScalpFX`):
- `backend/scalpfx/paper.py` (1192 lines): one asyncio process, 10 s tick,
  flock single-instance guard, per-bot evaluation on closed candles, simulated
  fills with fees/slippage, SL/TP intrabar (stop-first, gap-through fills at
  the worse price), trailing + time stops, hourly pruning, 60 passing backend
  tests. Runs 24/7 on a Raspberry Pi 4 against SQLite WAL.
- `backend/scalpfx/backtest/engine.py` (194 lines): strict anti-lookahead —
  signal on bar i−1 fills at open of bar i; walk-forward folds with strict
  temporal ordering. NB: the paper engine does **not** share this fill model
  (paper fills at the close of the last closed bar, up to 2 bars after the
  signal). Backtest/paper parity is already broken inside ScalpFX itself —
  one of the load-bearing reasons for the kernel decision in §2.
- Risk rails (`risk.py`, `risk_guard.py`): daily loss 5 %, kill-switch at 12 %
  drawdown from peak, gross exposure cap 2.0× equity, loss-streak cooldown
  (3 losses → 4 h pause, pure functions, zero dependencies), max positions
  caps, news-blackout placeholder. Persisted manual kill-switch shared
  API↔worker through the DB.
- ML (`ml/`): numpy logistic regression, 11 features, triple-barrier labels,
  4-fold walk-forward with 24-bar embargo, champion/challenger promotion
  (challenger must beat champion's mean OOS accuracy), PSI drift on `vol_z`,
  weights serialized into `model_versions.weights_blob` — the worker hot-loads
  the champion without retraining.
- Agents (`agents/`): deterministic-first design — every agent has a
  fallback and an LLM failure is indistinguishable from a missing key;
  `RequestBudget` rations the OpenRouter free tier by priority tiers
  (high/normal/low stand down at 100/80/50 % of the day budget); `Prime`
  runs free local gates first (news blackout, ATR/vol/trend filters,
  funding/OI, EV check from realized stats) and spends at most one merged
  LLM call per candidate; `LearningLoop` implements layered memory
  (working 7 d → shallow 30 d → deep) with periodic reflection into
  `agent_memory` plus a curated `docs/LESSONS.md` tail injected into prompts.
- Sizing chain (paper.py ~lines 600-650) is convoluted: risk base → size_mult
  → quant_mult → dynamic leverage 2-25× → vol scaling → quality multiplier →
  two caps. It works, it is tested, and nobody can defend every multiplication.
  Redesign, don't port 1:1.
- Debt: hardcoded single symbol (`SYMBOL = "BTCUSDT"` at module level, used
  in every query despite the schema being symbol-ready), config drift,
  dead deployment code (supabase/fly/docker-compose), venue adapters
  written but not integrated (`venues/hyperliquid_live.py`), spot used as a
  perp proxy, no CI, one `_maybe_close_positions` uses the 1m close of the
  last-iterated bot for all positions across timeframes.
- Dashboard: Next.js 15, 16 functions, deployed as static snapshots committed
  on a timer — read-only with no path back into the system.

**Vibe-Trading** (`/Users/dawe/Developer/Vibe-Trading`, fork of
HKUDS/vibe-trading, MIT):
- `agent/backtest/validation.py` is practically self-contained: Monte Carlo
  permutation test on the trade vector (p-values for Sharpe and max drawdown
  against shuffled orderings of the same trades), i.i.d. bootstrap Sharpe CI
  with `prob_positive`, windowed consistency analysis. Depends only on
  numpy/pandas and `backtest/metrics.py` + `backtest/models.py` — extraction
  is three files, ~60 KB, zero langchain. **This is the one part lifted as
  code.**
- Data loaders (`agent/backtest/loaders/`, ~45 sources): registry +
  market-specific fallback chains, per-source availability probing,
  price-caliber warnings. Conceptually the right model for the data plane;
  the code is wired into the framework's config/network layer, so the
  pattern is copied, not the files.
- Live governance (`agent/src/live/`): mandate (immutable hard caps, consent
  expiry, the only write path is a human endpoint, deliberately not an agent
  tool), order guard (fail-closed check chain before any broker call,
  verdicts ALLOW/DENY/PAUSE_FOR_REAUTH), halt sentinel file with filesystem-
  level enforcement independent of the LLM, append-only audit with hash chain
  and fsync. Architecture to imitate when M5 comes; not portable as code.
- The repo as a whole (577k lines, langchain) is a reference and a library
  of patterns. It is never a runtime dependency.

**crypto-tracker** (`/Users/dawe/Developer/crypto-tracker`):
- TypeScript monitor: Base/ETH whale tracking, new-pool detection, gold RWA
  spread alerts, Telegram/webhook alerting, read-only JSON API on :8787.
  Stays out of the core system; its alerting pattern is noted for the
  dashboard's alert rail. Optional data feed, never a dependency.

**Jane Street / Citadel open source**: Citadel publishes nothing. Jane
Street's stack is OCaml — unusable as code in this Python/React system.
What transfers is principle, and it is adopted here as such:
incremental recomputation (recompute what changed, cache the rest — the
anchor+events model is already this), expect tests as executable truth
(Aurelio's test names already read as sentences), and adversarial review as
a structure rather than a culture (already the chain). These are cited as
principles in §9, never as libraries.

**nautilus_trader 1.x** (LGPL-3.0, Rust core + Python API): backtest/live
parity is its central design property (the same strategy class runs in
both), daily bars are first-class, Python 3.12 supported, no mandatory
Redis, IBKR adapter covering paper and live. **Validated by the spike**
(`.spikes/nautilus/SPIKE-REPORT.md`, 2026-11-25): version 1.231.0 installs
in 25 s on Python 3.12.14 (wheel ~148 MB, venv 651 MB); a SMA-cross
backtest on 752 real yfinance daily bars (SPY/QQQ) ran end-to-end on the
first attempt — 20 fills, PnL +20,222 USD on a 100k account, `engine.run()`
wall-clock 0.04–0.08 s for 752 bars, with Sharpe/Sortino/profit-factor/
expectancy statistics computed by the analyzer for free (max drawdown must
be derived from the equity series — it exists only in the HTML tearsheet).
Practical notes recorded there: pin `nautilus_trader==1.231.0` exactly,
because the 2.x line is an incompatible pre-release and the public
documentation site documents 2.x — the source of truth for 1.x is the
repository at tag `v1.231.0` (`docs/concepts/backtesting/`,
`examples/backtest/`) plus the installed package's docstrings; import cost
is ~1–2 s per process, so import at startup, never lazily per call.
LGPL note: dynamic linking against the unmodified published wheel imposes
no obligations on this private single-user system; we never patch or
vendor the Rust core.

---

## 2. Kernel decision: nautilus_trader — confirmed

**Decision: nautilus_trader 1.x (pinned `==1.231.0`) is the execution/
backtest kernel — confirmed by the spike on 2026-11-25. The ScalpFX policy
layers (risk rails, ML gate, agent budget/memory, sizing) are ported as
owned Python around the kernel, not into it.**

The three honest options:

**A. nautilus as kernel.** What it buys: backtest/live parity as someone
else's maintained invariant — the single most expensive property to build
and keep honest ourselves, and the one ScalpFX already violates internally
(§1). Multi-asset, multi-venue, correct event-driven ordering, daily bars
first-class, an IBKR adapter that covers both paper and live — which is the
only live path this system will ever consider first (a regulated broker,
not a crypto perp venue). Mature margin/fill models instead of our hand-rolled
slippage arithmetic. What it costs: a 148 MB dependency, a framework's
concepts to learn, a Rust core we cannot read fluently, and real work to
express ScalpFX's rails inside its actor/strategy model rather than inside
one readable asyncio loop.

**B. Evolve ScalpFX's engine.** Cheaper this month, more expensive every
month after. The engine is a single-symbol proof of concept whose schema
pretends otherwise; making it multi-asset means redesigning the bot registry,
per-symbol equity, the close-position bug, the fill model — and then building
venue adapters, margin models and corporate-action handling that nautilus
already has and we would write once, wrong, and then again. Worse: option B
preserves the structural flaw that two different engines (backtest vs paper)
must be kept semantically equal by discipline alone. That is exactly the
failure mode the whole design exists to prevent: a number you cannot trace
to one cause. Rejected.

**C. Hybrid: nautilus for backtests, ScalpFX engine for paper.** Rejected on
the same grounds — it *institutionalizes* the backtest/live split. The parity
is the product.

**The gate — PASSED, with one finding that shapes the design.** The spike
demonstrated: a backtest on real daily bars running end-to-end on the
first attempt with correct account progression and free analyzer
statistics (§1); parity of the strategy class across backtest/live by
design. The one finding that matters architecturally: **a market order
issued from `on_bar` on daily bars fills at the CLOSE of the signalling
bar, not at the open of the next one.** Verified empirically in the spike:
with and without the `ts_init` close-delta shift, the fill price is the
signalling day's close. Nautilus does not create lookahead (the strategy
only ever sees closed bars), but it does not enforce the conservative
next-open fill that ScalpFX's `backtest/engine.py` treats as the
anti-lookahead standard either. Therefore the next-open execution model is
a property of *our* harness, not of the kernel: strategies must implement
it explicitly — signal delayed by one bar, or limit orders placed for the
next bar's open — and the M2 acceptance must prove it (§7, §9). The
default same-close fill is not wrong for daily strategies, but it is
mildly optimistic, and optimism in validation is exactly what the pipeline
exists to exclude. The fallback engine path (B-minus) is retired.

**Sizing is redesigned, not ported.** The seven-multiplier chain becomes
three explicit, separately testable stages, each logging its input and
output into the order's provenance: risk budget (equity × risk-per-trade,
the only place leverage-free risk is set), conviction scaling (one bounded
multiplier from the ML gate and the local quality score, replacing both
`quant_mult` and `quality_size_mult`), and hard caps (exposure, gross
exposure, position count). Leverage, if ever used, is a mandate property
approved per strategy, not a dynamic function of conviction.

---

## 3. The planes

```
┌────────────────────────────────────────────────────────────────┐
│ PRESENTATION — one React app (Aurelio frontend, extended)      │
├────────────────────────────────────────────────────────────────┤
│ INTELLIGENCE — LLM agents: wealth chain + trading agents,      │
│   shared budget system, shared memory, cards for every write   │
├────────────────┬───────────────────────────────────────────────┤
│ LEDGER PLANE   │ TRADING PLANE                                 │
│ (Aurelio, as   │ engine process: kernel + strategies + rails   │
│  it is)        │ research: validation gate, backtests, ML      │
├────────────────┴───────────────────────────────────────────────┤
│ DATA PLANE — one store: market data, FX, fund composition      │
├────────────────────────────────────────────────────────────────┤
│ SQLite, WAL mode, one file. Alembic owns the schema.           │
└────────────────────────────────────────────────────────────────┘
```

### 3.1 Ledger plane — wealth OS

Responsibilities: everything Aurelio already does — anchor+events wealth,
cash projection, look-through, goals, tax-as-estimate, the chain.

- **Reuse:** the entire `backend/app/` package unchanged. `positions`,
  `analytics`, `fx`, `prices`, `composition`, `catalogue` are the system's
  wealth math. Nothing here is rewritten.
- **New:** one consolidated endpoint and dashboard section joining ledger
  wealth with trading equity (§5, the "no double counting" rule). A new
  institution type or convention representing the trading account.
- **Deleted/unused:** nothing in the ledger plane.

### 3.2 Trading plane

Responsibilities: strategy definitions, signal generation, risk rails,
order/fill bookkeeping, paper execution, backtest execution, lifecycle
state of strategies. Writes flow into the same database.

- **Reuse:** `risk_guard.py` verbatim (pure functions), `risk.py` concepts
  (limits, kill-switch persistence pattern), `ml/` pipeline almost verbatim
  (numpy logreg, walk-forward, PSI, champion/challenger, weights_blob
  hot-load), the agents' deterministic-fallback discipline, `Prime`'s
  local-gates-first pattern, `LearningLoop` memory tiers, the budget
  system. ScalpFX's own `backtest/engine.py` is superseded by the kernel;
  its anti-lookahead fill model survives as the harness's execution
  standard (§7).
- **New:** the nautilus kernel adapter layer, the strategy
  lifecycle state machine (§6), the approval-card integration (§6), the
  redesigned sizing (§2), multi-symbol by construction (symbol is a
  dimension of every strategy registration, never a module constant),
  backtest/paper parity through the kernel, next-open execution enforced
  by the harness on top of it (§7).
- **Deleted/not carried over:** `BOT_SPECS` hardcoding, the spot-as-perp
  proxy, dead deployment code, the Next.js snapshot dashboard, `venues/`
  adapters written against a venue we will not trade first, the convoluted
  sizing chain, the 1m-close-for-all-positions close logic.

### 3.3 Data plane

Responsibilities: ingest market data once, serve it uniformly to backtests,
paper engine, wealth revaluation and research. Owns: candles/bars store,
corporate-action-aware equities data, FX rates, fund composition.

- **Reuse:** Aurelio's `prices.py`/`yahoo_rates.py`/`fx.py` (ECB + Yahoo FX,
  price cache, close-of-day rules — including the hard-won "a day's close
  belongs to that day, or the app waits" discipline), ScalpFX's
  `feeds/binance.py` websocket ingestion and `upsert_candles` chunking.
- **New:** a loader registry with per-market fallback chains, copied as a
  pattern from Vibe's `loaders/registry.py` (availability probing,
  `MARKET_DATA_ORDER_<MARKET>` override constrained to permutations,
  caliber warnings). yfinance for equities/ETF daily; Binance/Hyperliquid
  websockets for crypto intraday; OpenBB (Apache-2.0) evaluated in M1 as the
  macro/equities fundamentals layer — adopted only if it earns it over raw
  yfinance for what we actually read.
- **Key unification decision:** one `bars`/`candles` store keyed by
  (source, symbol, timeframe, open_time) with per-row provenance. The
  wealth plane's `price_cache` and the trading plane's candle history are
  the same concept at different cadences; they share the store and the
  close-waiting discipline. yfinance's empty-row traps documented in the
  manifest apply to trading data ingestion identically.
- **Not carried over:** OpenBB as a platform, OpenTerminal entirely,
  crypto-tracker's chain-specific ingestion (optional adapter later, never
  core).

### 3.4 Research plane

Responsibilities: the validation gate every strategy must pass before paper;
backtest runs and their provenance; model training/promotion; experiment
records.

- **Reuse, as code:** the vendored validation trio from Vibe —
  `validation.py`, `metrics.py`, `models.py` (~60 KB, numpy/pandas only,
  MIT) — copied into our tree as `trading/validation/` with its license
  header, then adapted to our trade record shape. This is the system's
  statistical spine: permutation test p-values, bootstrap Sharpe CI with
  `prob_positive`, windowed consistency.
- **Reuse:** ScalpFX's walk-forward folds, `monte_carlo.py` bootstrap fan
  (complements, not replaces, the permutation test — the permutation test
  answers "is this ordering luck", the bootstrap fan answers "what does the
  distribution of outcomes look like").
- **New:** the gate itself as an enforced lifecycle transition (§6); a
  `research` CLI that runs backtest+validation and writes the verdict row;
  walk-forward *parameter* validation (Vibe's version is consistency-only;
  ours must retrain/fit per fold because our strategies have fitted
  components).
- **Explicitly not built:** a research IDE, notebook infrastructure,
  parallel grid search. Single-user, boring: the gate runs in minutes on
  daily/4h bars.

### 3.5 Intelligence plane

Responsibilities: all LLM usage in the system. Two families sharing one
infrastructure: the wealth chain (Aurelio's adversarial analyst/confidant/
revision/synthesis) and the trading agents (quant/reviewer gates, analyst
commentary, learner/memory reflection). Plus the chat interface.

- **Reuse:** `chain.py` and `chat.py` unchanged in structure; ScalpFX's
  `budget.py` generalized into the shared request budget — one budget for
  the whole system, one priority table, because the constraint (OpenRouter
  free-tier requests/day) is per account, not per subsystem. ScalpFX's
  memory tiers and the `LESSONS.md` curator pattern.
- **New:** trading-agent insights become first-class rows the dashboard
  reads; the memory loop extends to post-trade review linked to fills by
  FK. The asymmetry discipline of the chain is adopted for trading:
  a pre-trade reviewer never sees the position sizing figures it is not
  supposed to anchor on; what it sees is code, not prompt politeness.
- **Unchanged invariant:** no agent writes anything anywhere. Signals,
  vetoes, insights and lessons are *proposals and observations*. Writes are
  the deterministic code's job, gated by cards where a human decision is
  involved (§6).

### 3.6 Presentation plane

- **Reuse:** the Aurelio React app as the single frontend — its design
  discipline (proportional/tabular digits rule, cards, fingerprint
  staleness, notice patterns) extends to the trading panels.
- **New:** trading sections (§7). Charts: **lightweight-charts 5.3.0**
  (Apache-2.0) for price/equity series — verified working out of the box
  in Vite 8 with zero config; **Perspective 5.10.0** for the streaming
  blotter/analytics tables — verified in the `.spikes/viz` spike
  (dev and production bundle, streaming `table.update()` end-to-end), with
  exactly one integration contract: `.wasm` binaries must be imported with
  the `?url` suffix, an explicit bootstrap `init()` runs once in
  `main.tsx` before first use (registering `server32`/`server64` as thunks
  so only the supported binary downloads), the datagrid/charts plugins are
  separate side-effect imports, and all Perspective packages on the page
  must share the exact release. The `PerspectiveStarletteHandler` serves
  the server side from the FastAPI process.
- **Deleted:** the ScalpFX Next.js dashboard (superseded), the snapshot-
  commit deployment mechanism.

---

## 4. Integration topology — boring on purpose

**Three processes, one machine, one database file:**

1. **`web`** — uvicorn running the FastAPI app: Aurelio routers plus new
   trading/research routers. Serves the React build. This process must stay
   exactly what it is: a request/response web app that can restart freely.
2. **`engine`** — the trading worker: kernel + strategies + risk rails +
   data ingestion (websocket streams). Runs 24/7 under a supervisor
   (launchd on the Mac, systemd on the Pi — same pattern as ScalpFX today).
   Never imports FastAPI; its interface to the world is the database and
   the kill-switch rows. flock single-instance guard carried over.
3. **`research`** — not a daemon: CLI invocations (backtests, validation
   runs, retraining) either by the developer or by the engine's scheduler
   (as today: auto-retrain weekly, in-process).

**One SQLite database in WAL mode, one schema, Alembic-owned.** Measured
precedent in-tree: Aurelio's MCP server already proves a second process can
read this database concurrently (`tests/test_mcp_server.py` documents WAL
behavior under writer transactions), and ScalpFX already runs an API and a
worker against one SQLite WAL file 24/7 on a Pi. The writes are small (a
fill is a row, an equity point a row); the engine is the only writer of
trading tables and the web app of ledger tables, with card confirmations
writing trading-lifecycle rows through the normal `unit_of_work` path.
Postgres is rejected: one user, one machine, a backup story that is `cp`.

**Why not microservices:** there is one user and one machine; a service
boundary is a network you have to debug. The two-process split exists for
exactly one reason: the engine must keep trading while the dashboard is
closed, restarted or broken — and the dashboard must never be able to wedge
the engine (a slow query, a GC pause, a deploy). The database is the
interface: the web process reads trading state; it never calls into the
engine. Commands to the engine (kill-switch reset, strategy pause after
approval) are rows written transactionally that the engine polls each tick —
the pattern ScalpFX already runs for its kill-switch.

**Where the code lives:** inside the HedgeFund repo, as a new package
`backend/trading/` beside `backend/app/` — same Alembic history, same test
layout, same `uv` project. ScalpFX becomes the donor repo: pieces are
ported file-by-file with their tests, not imported as a dependency.
Vibe-Trading donates exactly the validation trio. crypto-tracker stays
separate. OpenTerminal is removed from the repo (vendored, unintegrated,
licensable clutter — removal is an M0 task).

---

## 5. Trading data model — provenance first

New tables, all in the same Alembic lineage. Naming follows Aurelio's
style (plain plurals). The spine: **every number in the trading plane can
be walked back to a signal, a decision chain, and the exact inputs each
stage saw.**

```
strategies ──────────── registered strategy definitions
  └ strategy_versions    immutable parameter/code-version rows
       └ signals         every signal every version emitted (incl. rejected)
            └ order_intents   the sizing/gate decision chain per signal
                 └ orders     what was actually sent to the (paper) venue
                      └ executions/fills
positions_engine         open engine positions (derived cache of fills,
                         rebuilt never mutated — fills are truth)
trades                   closed round-trips with full provenance
equity_points            per-strategy and portfolio equity curve
strategy_states          lifecycle state machine rows (append-only history)
backtest_runs            a run: config hash, data window, code version
backtest_validations     verdict rows: permutation p, Sharpe CI, WF folds
model_versions           champion/challenger registry (carried from ScalpFX)
agent_insights           (carried) — now with optional FK to trades/fills
agent_predictions        (carried)
agent_memory             (carried)
risk_events              every rail that fired: kill, daily-loss, cooldown,
                         exposure cap — with the numbers that tripped it
approval_cards           lifecycle/live-mode confirmations (see §6)
data_ingest_log          per-source ingestion provenance: what, when, how many rows
```

Design rules, each inherited from an existing scar:

- **Signals are recorded even when rejected.** A signal vetoed by the ML
  gate, the risk rails or the loss-streak guard is a row with the stage
  that stopped it (`gate_source`, carried over from ScalpFX). Otherwise the
  system can never answer "is the gate too strict?" — the same logic as
  Aurelio's "nothing leaves the totals without saying where it went".
- **`order_intents` is the sizing provenance.** Three stages (§2), each
  writing its input value, its output value and its parameters version.
  The convoluted single number of today becomes a legible chain.
- **Fills are the truth; positions are a cache.** `positions_engine` is
  rebuilt from fills, never independently mutated — the anchor+events
  discipline applied to the engine: today's position is the sum of fills,
  full stop. If the kernel maintains its own positions, ours are the audit
  projection and reconciliation compares them on a schedule; a mismatch is
  a `risk_events` row and a dashboard alert, never silent.
- **Backtest provenance is complete or the run is invalid.** A
  `backtest_runs` row records the exact data window, the strategy version
  hash, the kernel/engine version, fee/slippage assumptions and the config
  hash. Validation rows reference it. A strategy version can only enter
  `validated` state pointing at a validation row whose every threshold
  passed — the transition is impossible without the evidence, enforced in
  code, not in process discipline.
- **Engine positions ≠ wealth positions, deliberately.** The wealth ledger
  records what the broker statement says (the anchor+events model — a
  broker snapshot is exactly a "situation" in Aurelio's sense). The engine
  records what it believes it holds. These are two different statements
  about overlapping money and the design keeps them apart:
  - The trading account is one `institution` in the ledger; its ledger-side
    value comes from broker statements/cash anchors like any other account.
  - Engine equity is shown beside it, labelled as engine-reported,
    never summed into net worth. **The consolidated total is ledger wealth
    (which includes the broker-reported trading account) — with engine
    equity displayed as a comparison line, and a reconciliation gap
    (broker statement vs engine) surfaced exactly like Aurelio's
    positions-that-vanished reporting.** This inherits "a wrong number can
    be traced either to a wrong photograph or to a wrong event": the
    photograph is the broker statement, the events are the fills.
- **Equity points keep the pruning discipline** (cap rows, denser cadence
  on movement) carried from ScalpFX — provenance does not mean hoarding
  noise; the fills are permanent, the curve is a rendering.

---

## 6. Risk & governance architecture

Defense in depth, ordered by distance from the money. The ordering
principle, copied from Vibe's live governance because it is the correct
one: **the closer to execution, the dumber and more independent the rail.**

**Layer 0 — hard rails, in the engine, before any order exists:**
- kill-switch: drawdown from peak equity (12 % carried over, configurable
  per mandate), plus the persisted manual kill-switch row; tripping it
  stops new entries immediately and (configurable per mandate) flattens.
- daily loss limit (5 %), loss-streak cooldown (3 losses → 4 h, pure
  functions carried verbatim), gross exposure cap, per-position caps,
  position count caps.
- Every firing writes `risk_events` with the inputs. A rail that cannot
  explain itself is removed, not trusted — the provenance rule applies to
  the brakes first.

**Layer 1 — the lifecycle state machine.** A strategy version moves:

```
research → validated → paper → candidate_live → live
```

- `research → validated`: automatic but conditional — possible only when a
  `backtest_validations` row exists for this version passing every gate
  (§research: permutation p-value, Sharpe CI lower bound, walk-forward
  consistency, minimum trade count). No evidence, no transition.
- `validated → paper`: automatic on registration; paper is free.
- `paper → candidate_live`: **approval card, human, mandatory.** The card
  carries the paper track record summary (duration, trades, realized vs
  backtest divergence) with staleness fingerprint — confirming a card whose
  inputs moved returns 409, exactly as in the wealth chat.
- `candidate_live → live`: **approval card plus a mandate** (below). Never
  one click. M5 audits this path; nothing in this design ever flips it
  automatically.

Transitions are rows in `strategy_states`, append-only; state is the
latest row, re-basing is impossible — the anchor+events discipline again.

**Layer 2 — the mandate (live only, designed now, built in M5).** Copied
in concept from Vibe's `mandate/`: an immutable row of hard caps — max
order notional, max exposure, allowed instruments, max trades per day,
consent expiry (default 30 days, after which live trading halts itself),
funding bounds. The only write path is a confirmation flow in the UI; the
mandate is deliberately not reachable by any agent or strategy. Before any
live order: halt check → mandate expiry → order guard chain (instrument
allowed? notional within cap? exposure within cap? daily count within
cap?) — fail-closed, verdicts allow/deny/pause-for-reauth.

**Layer 3 — human-in-the-loop for orders.** Paper trading: no per-order
approval (that would make paper worthless as a test of the strategy).
Live: per-order approval is the default until the mandate system earns
trust — an order intent becomes a card, the card carries the full decision
chain (signal, sizing stages, rails state), confirming it releases the
order, and its fingerprint includes the strategy state and mandate version
but never the live price (a card does not expire because the market moves —
the manifest's rule extends verbatim).

**Layer 4 — the halt sentinel.** A file-level kill switch independent of
all software discipline (Vibe's pattern): existence of the sentinel file
halts order submission at the venue-adapter boundary, fail-closed even if
the file is corrupt. Cheap insurance for the day everything else is wrong.

**The AI rule, extended.** Aurelio's rule — the model proposes, you write —
extends to trading as: **the model may propose a signal, a veto, an insight,
a lifecycle recommendation; it may never transition a state, size an order
by itself, or touch a mandate.** Gates that affect execution are either
deterministic code (rails, ML champion) or human (cards). The LLM reviewer's
veto is advisory-recorded: it blocks a paper entry as part of the strategy's
*definition* (and thus part of what's backtested), not as an out-of-band
override — otherwise the paper test measures a different strategy than the
backtest did.

---

## 7. The strategy framework

**Interface** (nautilus `Strategy` subclass underneath; the contract below
is the invariant our harness enforces on top):

```python
class Strategy:
    def signal(self, ctx) -> Signal | None
    # ctx: bars up to and including the just-closed bar, features.
    # NEVER: equity, positions, fees, other strategies, the database.
```

The contract is ScalpFX's `BaseStrategy` (`bots/base.py`) verbatim in
spirit: pure functions of market data, anti-lookahead enforced by
construction. Two distinct guarantees, because the spike separated them
(§2): the kernel guarantees a strategy **never sees future data** — only
closed bars reach `on_bar`. What the kernel does not guarantee is the
**fill timing**: its default is the close of the signalling bar, while our
standard is the next bar's open (the conservative execution model of
ScalpFX's `backtest/engine.py`). The harness therefore wraps every
strategy: signals are delayed one bar before order placement (or placed
as limit orders at the next open), in backtest and paper identically —
same wrapper in both, which is what keeps parity meaningful. A test in M2
proves a harness-wrapped strategy fills no earlier than the bar after its
signal. `Signal` carries side,
confidence, stop distance, take-profit — never size; sizing is the system's
job (§2) because risk is a portfolio property, not a strategy opinion.

**Registration:** a strategy is code plus a `strategies`/`strategy_versions`
row: parameter set, code hash, timeframe, universe. Two instances of the
same logic with different parameters are two versions; the lifecycle tracks
versions, because "the strategy" that passed validation is exactly one
parameter set on one universe — anything else is a new promise.

**Validation gate, enforced before paper:**
1. Anti-lookahead audit, now in two parts: the harness never hands future
   data to the strategy (a test writes a cheating strategy and proves it
   cannot see ahead), and the execution wrapper enforces next-open fills
   (a test asserts no fill timestamp precedes the bar after the signal).
2. Backtest over the full available history: minimum trade count (Vibe's
   permutation test itself demands ≥3; we set the bar at 30 for the CI to
   mean anything — exact number fixed in M2 by measurement, recorded in
   the validation row).
3. Monte Carlo permutation test: p-value for Sharpe below threshold
   (default 0.05), or the ordering of these trades is indistinguishable
   from luck.
4. Bootstrap Sharpe CI: lower bound of the 95 % interval above zero, or
   `prob_positive` above threshold.
5. Walk-forward: out-of-sample folds positive in aggregate; consistency
   windows majority-profitable.
6. Divergence budget declared per strategy: how far paper may drift from
   backtest before the lifecycle flags it (this becomes the paper →
   candidate_live evidence).

**Migration path for the existing four** (`bots/scalp_bot.py` ScalpTrend,
`hft_bot.py` HFTMomentum, `breakout_bot.py`, `meanrev_bot.py`): each is
ported as a pure strategy in M2/M3 — they are already structurally pure,
which is the one thing ScalpFX got right from the start. They enter at
`research`, run the gate honestly, and the design expects — per ScalpFX's
own documented expectancy — most to fail it. That is the gate working,
not the gate being wrong. They remain useful as the pipeline's test
subjects: a system that passes a losing strategy is broken in the way that
matters.

---

## 8. Dashboard information architecture

One React app. New sections join the existing navigation; nothing about the
wealth pages changes except the addition of the consolidated view.

```
FUND OVERVIEW (extends today's Dashboard)
  total wealth (ledger, includes broker-reported trading account)
  trading equity (engine-reported, beside, never summed)
  reconciliation gap line — broker statement vs engine, with date
  allocation: wealth look-through + trading exposure merged at display time

TRADING OPS
  positions (engine), open orders/intents, today's signals incl. rejected
  risk state: rails dashboard — kill-switch, daily loss, cooldowns,
    exposure caps, each with the numbers, each green/red
  per-strategy panel: state in lifecycle, equity curve, paper-vs-backtest
    divergence meter, recent trades with provenance drill-down
    (trade → order intent → sizing chain → signal → version)
  kill-switch control: guarded (two-step), writes through API; engine
    reads the row next tick

RESEARCH
  backtest runs table: strategy version, window, metrics, validation
    verdict badges (permutation p, CI, WF) — clicking opens the equity
    fan (bootstrap paths, Vibe's percentile bands), trade list, config
  validation queue: versions awaiting gates, failures with reasons
  model registry: champion/challenger, OOS metrics, PSI drift

INTELLIGENCE
  agent insights feed (trading) + chain runs (wealth), one stream, filterable
  memory browser: working/shallow/deep tiers, lessons log
  budget panel: day spend vs caps by priority tier

ALERTS
  risk events stream; reconciliation gaps; stale feed warnings;
  validation failures; delivery stays in-app (Telegram/webhook is an
  optional M5+ extra, pattern available in crypto-tracker)
```

Design rules carried from the Aurelio frontend: tabular digits in columns,
proportional in isolation; every figure carries its provenance on hover/
drill-down; a stale control is a fingerprint, not a timer; notices say what
is missing rather than pretending precision (the engine-offline state is a
first-class visual state, not an empty dashboard). Charts:
lightweight-charts for price/equity; Perspective for the blotter tables
(integration contract in §3.6 — `?url` wasm imports plus bootstrap init).
Live updates: the web process streams via websocket/SSE from the database
— the engine never serves the UI.

---

## 9. Milestones

Effort is in focused working days (±50 % — single-developer estimates are
what they are). Each milestone ends with a working thing, verified, never
a scaffold.

### M0 — Repository hygiene and CI (2-3 days, no dependencies)
- Move ScalpFX's backend into `HedgeFund/backend/trading/` as ported modules
  with their tests (preserving git history where cheap; correctness of the
  port verified by the tests travelling with it). Delete: supabase/fly/
  docker artifacts, `venues/`, the Next.js dashboard remains in ScalpFX
  (repo archived read-only after migration).
- Remove `OpenTerminal/` from the HedgeFund repo.
- CI: one GitHub Actions workflow running both test suites (Aurelio's 123,
  ScalpFX's 60) on Python 3.12. No lint ratchets, no coverage gates — the
  suites are the contract.
- Unify configuration: one `.env` pattern, one settings module per plane,
  documented; kill the config drift.
- **Acceptance:** green CI on the merged tree; `uv run pytest` passes in
  `backend/`; ScalpFX's Pi deployment either keeps running off the old repo
  until M3 or is consciously paused — recorded decision, not drift.
- **Out of scope:** any new feature, any refactoring beyond what the move
  requires.

### M1 — Data plane (4-6 days, depends on M0)
- Unified `bars` store with per-market loader registry and fallback chains
  (pattern copied from Vibe), yfinance equities/ETF daily + Binance crypto
  intraday as the first two loaders. `data_ingest_log` provenance.
- Migrate wealth price ingestion onto the same store without breaking the
  close-waiting rules (`prices._close_on` discipline stays authoritative —
  123 tests defend it).
- OpenBB evaluation as a time-boxed experiment (half a day): adopt only if
  it demonstrably covers something we read that yfinance does not.
- **Acceptance:** one command backfills SPY/QQQ daily and BTCUSDT 1m..4h;
  wealth revaluation and trading ingestion read the same store; ingestion
  rows carry source provenance; tests for the fallback chain and the
  empty-row traps (NaN vs missing row).
- **Out of scope:** realtime streaming to the UI, macro/fundamentals beyond
  the experiment.

### M2 — Backtest + validation end-to-end on one strategy (5-8 days, depends on M1)
- Vendor Vibe's validation trio into `backend/trading/validation/`; port
  ScalpTrend as the reference pure strategy.
- **Kernel confirmed:** backtests run on nautilus 1.231.0 behind the
  harness. The harness implements the next-open execution wrapper (§7) on
  top of the kernel's default same-close fill. A one-time reference diff
  against the ported `backtest/engine.py` on the ScalpTrend migration
  documents expected fill-model differences (fill timing is deliberate;
  everything else must match within rounding).
- The validation gate implemented as code: permutation p, Sharpe CI,
  walk-forward, minimum trades, all written to `backtest_validations`;
  `research` CLI runs the whole pipeline and prints the verdict.
- **Acceptance:** one command takes ScalpTrend from code to a validated/
  rejected verdict with a complete provenance row; the verdict is honestly
  reproducible (seeded); a deliberately lookahead-poisoned strategy variant
  is caught (a test writes a cheating strategy and proves the harness gives
  it no future data); and a second test asserts the execution wrapper —
  no fill timestamp precedes the open of the bar after its signal (the
  kernel's default close-of-signal-bar fill may never leak through).
- **Out of scope:** paper execution, multi-strategy portfolios, parameter
  optimization (explicitly — optimization before validation infrastructure
  is how curve-fitting is born).

### M3 — Paper engine 24/7 (6-9 days, depends on M2)
- Engine process: nautilus kernel + the harness wrapper + ported risk
  rails + redesigned three-stage sizing + ML champion/challenger pipeline +
  agent budget/memory integration. Multi-symbol by construction, even if
  only BTCUSDT trades.
- Lifecycle state machine live; `validated → paper` registration flow.
- Runs continuously for a soak period; reconciliation between engine
  positions and fills projection verified daily in tests.
- **Acceptance:** two weeks of uninterrupted paper operation with at least
  one validated strategy; every signal recorded including rejections;
  `risk_events` explain themselves; restart-safety proven (kill the process
  mid-tick, state resumes consistent — flock guard, peak equity, open
  positions); the existing four strategies migrated through the gate with
  honest verdicts.
- **Out of scope:** any live path, leverage, additional venues.

### M4 — Unified dashboard (5-7 days, can overlap M3 after week one)
- Trading ops, research, intelligence sections in the Aurelio React app per
  §8; consolidated fund overview with the reconciliation line.
- lightweight-charts integrated (no Vite config needed); Perspective
  integrated per the §3.6 integration contract (`?url` wasm imports,
  bootstrap init in `main.tsx`).
- Kill-switch control and lifecycle approval cards in the UI.
- **Acceptance:** the owner can answer, from one page: total wealth,
  trading equity, what every strategy is doing and why, what the agents
  said, what the rails did — without opening a terminal. ScalpFX's Next.js
  dashboard formally retired.
- **Out of scope:** visual redesign of the wealth pages, mobile.

### M5 — Live-readiness audit (5-8 days, depends on M3 + M4; not live trading)
- Build — but do not arm — the mandate and order-guard layer: mandate rows,
  guard chain, halt sentinel, per-order approval cards, audit ledger
  (append-only, hash-chained — Vibe's pattern, our schema).
- The audit itself: a written review of every assumption in the chain —
  fill models vs real venue behavior, fee/slippage honesty, what paper
  cannot measure (queue position, partial fills, latency), reconciliation
  procedures against broker statements, the capital question (which
  account, how much, funded how), tax treatment of the trading account.
- **Acceptance:** a document (the audit) that either concludes "ready for
  a small live pilot on venue X with mandate Y" or lists exactly what is
  missing; the mandate machinery demonstrably blocks a violating order in
  tests even when every software layer above it is bypassed (sentinel file
  test); no live order capability exists without a signed-off audit —
  meaning the venue adapter is wired to testnet/paper only.
- **Out of scope:** live trading itself. That decision is the owner's,
  after the audit, outside this plan.

**Explicitly never in any milestone:** multi-user support, hosted
deployment, mobile apps, options/futures portfolio margin engines, tax
engine beyond declared estimates (the manifest's line), automated strategy
generation.

---

## 10. Decision registry (ADR-lite)

| # | Decision | Chosen | Alternative | Why | Reversibility |
|---|---|---|---|---|---|
| D1 | Execution/backtest kernel | nautilus_trader `==1.231.0` pinned — confirmed by spike 2026-11-25 | evolve ScalpFX engine; hybrid | backtest/live parity as a maintained invariant; multi-asset; IBKR paper+live path; ScalpFX already violates parity internally; spike measured a correct first-attempt backtest at 0.04–0.08 s / 752 bars | medium-high: policy layers are ours, kernel is behind an adapter |
| D2 | Validation statistics | vendor Vibe's trio (MIT, 3 files, numpy/pandas-only) | reimplement; depend on vibe-trading | self-contained, proven, correct license; depending on 577k lines for 60 KB is absurd | high: it's our copy |
| D3 | Database topology | one SQLite WAL file, one schema, Alembic | separate DBs per plane; Postgres | single-user localhost; cross-plane joins; WAL concurrency already proven in both repos; backup = cp | medium: split later is extractable; merge later would not be |
| D4 | Process topology | web + engine (+ research CLI), DB as interface | one process; microservices | engine must survive dashboard restarts and vice versa; a service mesh for one user is a network to debug | medium-high: processes already only share the DB |
| D5 | Trading code location | `backend/trading/` in HedgeFund, ported not imported | keep ScalpFX repo; pip-dependency | one Alembic lineage, one test run, one CI; porting with tests preserves correctness | medium: the port is the migration |
| D6 | Dashboard | extend the Aurelio React app | federate ScalpFX Next.js | one design discipline; snapshot-commit deployment is read-only dead-end | medium |
| D7 | Validation gate enforcement | lifecycle transitions impossible without verdict rows | documentation/discipline | what is not enforced in code erodes; the evidence is the transition | high |
| D8 | AI authority | agents propose/record; deterministic gates or humans decide | LLM vetoes as overrides; LLM sizing | a veto outside the strategy definition makes backtest≠paper; sizing is arithmetic, not prose | low-cost to tighten further, expensive to loosen — correct asymmetry |
| D9 | Kill/halt enforcement | DB rows + filesystem sentinel, engine polls; independent layers | in-app state only | the closer to execution, the dumber and more independent the rail | high |
| D10 | Sizing | three explicit logged stages | port the seven-multiplier chain | every multiplication must be defensible; provenance per stage | high |
| D11 | Charting/analytics UI | lightweight-charts + Perspective — both confirmed by spike 2026-11-25 | custom canvas; plain tables only | both verified in Vite 8 dev and prod bundle; Perspective's contract is one `?url` wasm import rule plus bootstrap init; degradable to plain tables if it ever misbehaves | high: presentation-layer only |
| D12 | Market data | unified store, loader registry + fallback chains | per-plane ingestion as today | the same close rules apply everywhere; two ingestion paths are two truths | medium |
| D13 | Wealth/trading consolidation | engine equity beside, never summed; reconciliation gap surfaced | sum engine equity into net worth | double counting: the broker statement already contains the money | n/a — this is a correctness rule, not a preference |
| D14 | Live path | mandate + order guard + approval cards + audit, built in M5, armed never | direct venue keys; deferred design | Vibe's governance is the correct shape; designing it late means retrofitting trust | irreversible once armed — hence the audit gate |
| D15 | LLM budget | one shared budget across wealth+trading, priority tiers | per-subsystem budgets | the constraint is per OpenRouter account, not per subsystem | high |

---

## 11. Open risks and non-recommendations

**Verified problems this design does not solve:**
- **No proven edge exists.** Every current strategy is expected to fail its
  gate. The system makes that failure cheap, fast and legible — and then
  the actual work starts: finding one strategy that passes. That work is
  research, not engineering, and no architecture de-risks it.
- **Paper measures the wrong thing partially.** Fill quality, queue
  position, latency, partial fills, funding costs and borrow are invisible
  in paper. The divergence budget (§7) and the M5 audit are the honest
  answer; a paper track record is evidence, not proof.
- **nautilus opacity risk.** If the Rust core misbehaves in a way tests
  don't catch, we debug through a language boundary. Mitigations: the
  adapter keeps our own audit projection of positions/fills and reconciles;
  the pin on `==1.231.0` plus the harness-level fill-timing tests mean an
  upstream surprise has to pass our own acceptance before it matters.
  Operational notes carried from the spike: never read the public
  documentation site for 1.x (it documents pre-release 2.x) — the source
  of truth is the repo at tag `v1.231.0`; import cost is ~1–2 s, so the
  kernel imports at process startup.
- **SQLite writer contention under load.** Fine at 10 s ticks and
  request-scale web traffic, unproven at high-frequency ingestion.
  Intraday 1m multi-symbol ingestion is the first stress point — M1's
  acceptance includes a burst test. If it fails, candles move to a separate
  file before positions do; provenance tables never leave the main file.
- **Free-tier LLM economics are a shared ceiling.** Wealth chain + trading
  agents on 45-100 requests/day means the budget is the design constraint
  it already is in ScalpFX: deterministic-first everywhere, LLM where
  judgment is the product. Do not "fix" this by spending money before the
  pipeline proves value.

**Non-recommendations — things explicitly not to do:**
- Do not upgrade nautilus casually: the pin exists because the 2.x line is
  an incompatible pre-release; an upgrade is a spike, not a dependabot
  merge.
- Do not build multi-venue abstraction before the first venue exists.
  One venue, chosen in M5 (IBKR paper is the leading candidate — regulated,
  real equities/ETFs, matches the wealth plane's universe; crypto perps are
  the worse first live venue in every dimension except convenience).
- Do not optimize strategy parameters before M2's validation infrastructure
  exists. Optimization without a permutation test is curve-fitting with
  extra steps.
- Do not federate dashboards, add a message bus, introduce Docker
  orchestration, or adopt a second database engine. Each is a networking
  problem purchased with a single user's money.
- Do not integrate crypto-tracker or OpenTerminal into the core. The first
  is an optional alerting/feed pattern source; the second is deleted in M0.
- Do not let any LLM output touch sizing, mandates, lifecycle transitions
  or order release — not "for now", not "with a small cap".
- Do not arm live trading outside the M5 audit process, whatever the paper
  results look like. A good paper run is a candidate, not a license.

**Unverified as of writing:**
- nautilus multi-symbol and intraday (1m) operation — the spike validated
  daily bars only; M1/M3 acceptance extends evidence there before the
  engine depends on it.
- OpenBB's actual coverage advantage for what this system reads — time-boxed
  experiment in M1, no commitment either way.
- The harness's next-open execution wrapper is designed but unbuilt —
  the kernel's same-close fill default is a measured fact, the wrapper is
  M2 work with its own acceptance tests.

---

*This document is a design, not a status. The spikes, the milestones and
their tests are the status. Where they disagree with this file, this file
loses and gets updated.*
