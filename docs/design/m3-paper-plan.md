# M3 slice plan — the paper engine 24/7 on the nautilus kernel

Date: 2026-11-25. Companion to `hedge-fund-os.md` §12 M3 (lines 726+); where the
two disagree, the measured facts below win and the parent document gets updated
at the end of the milestone.

Status: accepted as direction; **slice 1 landed 2026-11-26** (as `trading/desk/`,
the planned `trading/paper/` package renamed). Measured at
landing: parity exact 6/6 parallel runs under CPU contention with quiescence
pacing (pre-fix 6/6 divergent — kernel-diff §6), restart safety verified as a
kill-the-process subprocess pair rather than in-process simulation (the worker
is a process, so the test kills one), shallow-history restarts close honestly
unrecoverable-age positions instead of inventing their age.

## Why this plan exists

M2 put validation backtests on the kernel behind the harness. M3 puts paper
trading on the **same** kernel — the design's "same wrapper, both contexts" is
what makes backtest/paper parity meaningful instead of aspirational.

## What M2 measured that M3 builds on

1. **Next-open fills are impossible with bar-only data** (probes +
   `docs/research/kernel-diff-2026-11-25.md`). The harness runs one-bar-delayed
   close-of-bar fills, in backtest and paper *identically* — paper therefore
   uses the exact mechanism the backtest validated, no second execution model.
2. **`nautilus-1.231.0` ships `adapters/sandbox`**: `SandboxExecutionClient`
   wraps the *same* `SimulatedExchange` the backtest uses, subscribes to live
   msgbus data (`data.*` → matching engine), and plugs into a `TradingNode`.
   Paper execution semantics equal backtest semantics by construction, not by
   reimplementation.
3. **`adapters/binance` ships a live data client** (WS klines, spot and
   USDT-futures) — the production feed for slice 1. Instrument exists as
   `BTCUSDT-PERP.BINANCE` (measured in the M2 probes).

## What the legacy `paper.py` carries over — and what it does not

Carried over (ported, reviewed):

- `risk_guard` loss-streak cooldowns (pure functions, kv-store backed)
- kill-switch + daily-loss rails from `risk.py` (already pure)
- equity point / provenance discipline: state snapshots in kv, restarts rebuild
- the flock single-worker guard (`worker.lock`)
- stale-feed detection and per-bot failure isolation
- budget guards for agents (M4/Prime integration, slice 4)

NOT carried over (design §7/§10/§12 explicitly, or measured broken):

- **BOT_SPECS** — hardcoded desk roster; superseded by the lifecycle registry
  (M4 tables land in M4; slice 1 takes a static config list, registry wiring
  is slice 4's seam).
- **The seven-multiplier sizing chain** (`size_position` × size_mult ×
  quant_mult × leverage/5 × vol_scaled × quality_size, each capping equity
  invisibly). Design §10: redesigned sizing, *multi-symbol by construction* —
  slice 3 owns it, and slice 1 uses the harness/existing confidence sizing
  unchanged (a constant, BOT-INDEPENDENT sizing: same rule for every strategy,
  which is exactly what keeps backtest/paper arithmetic identical).
- **The close-position price bug**: `_maybe_close_positions` evaluates every
  open position against the *last candle of whatever bot is iterating*,
  regardless of that position's own symbol/timeframe. The kernel bracket
  orders make the whole construct unnecessary — SL/TP matching is the venue's
  job, identically in backtest and paper.
- **Dynamic leverage 2–25× conviction scaling** — design §11 caps approved
  per strategy, never a function of conviction.
- The ML champion gate, Prime veto, forecaster fan-out — slice 4 rewires them
  onto the new rails; they are not engine concerns.

## The slice decomposition

### Slice 1 — engine kernel against a live feed (this plan's build target)

`trading/paper/` package:

- `PaperNode`: a `TradingNode` with `BinanceDataClient` (USDT futures WS
  klines) feeding `SandboxExecutionClient` (venue `PAPER`, NETTING, MARGIN,
  zero-margin params like the backtest harness so bookkeeping stays ours).
- The same harness strategy factory as `kernel.py` — literally the same class
  builder, so a paper run is a backtest run with a live clock.
- **Pluggable data seam**: production registers the binance client; tests
  register a thin replay `LiveDataClient` emitting deterministic bars. Same
  node, same strategy, same matching engine — the test measures the engine,
  not a mock of it.
- **Restart-safety**: kernel state (positions/orders) is in-memory; the
  provenance layer is ours. On boot the node reads open positions +
  resting bracket orders from the DB and re-submits the protective legs.
  Acceptance test: kill the node mid-tick with positions open, restart,
  assert the rebuilt state matches the DB and no duplicate entries occur.
- Provenance: every fill writes rows the dashboard reads (positions, trades,
  equity) — tables as today, never kernel-internal state.
- flock single-worker guard, stale-feed detection, per-bot failure isolation:
  ported as-is, they are small and correct.

Tests: replay-feed integration test (deterministic bars → signals → fills →
provenance rows), restart mid-run test, bracket lifecycle test, multi-symbol
construction test (two instruments never share position state).

### Slice 2 — live binance wiring + soak

Real WS feed, testnet-first discipline: run against replay in CI, run one
soak against live binance WS locally (measured, time-boxed). Acceptance:
24h paper operation without a missed tick or a state divergence.

### Slice 3 — redesigned sizing, multi-symbol by construction

Design §10: exposure caps hard, leverage per strategy approved, symbol-unaware
multipliers deleted. Its own tests; blocked on nothing in slice 1 but design
feedback.

### Slice 4 — rails, registry, agents

`risk_guard` integration, the approval-card lifecycle seam (M4 registry feeds
the roster instead of the static list), Prime/ML gates rewired onto kernel
rails, kill-switch dashboard wiring. Acceptance: the lifecycle owns what the
engine may trade — with zero validated strategies today, the honest M3 end
state is an engine that is *ready* and *empty*, which is the gate working.

Implementation notes (landed 2026-11-26):
- **Pre-registry residents.** The soak's running bots (`scalp` on 1m and 4h)
  were booted before the registry existed, from the runner's since-deleted
  static `--bot` path. They are unaffected — a booted process reads no
  registry — and they are NOT migrated into it: a lifecycle row written
  retroactively for a version that never passed the validation gate would
  be a lie, and the tables are the one place the design does not lie. The
  production migration path is forward-only: when a strategy is validated
  (`trading.research validate`) and registered (`trading.research
  register`), the registry-driven runner boots it as `<key>-v<N>` under the
  same flock — a new resident beside the legacy book, whose pre-registry
  trades remain provenance of the pre-registry era and nothing more. The
  `--bot` CLI was removed, not deprecated: a fallback roster is precisely
  the gate not working.
- **Layer-4 halt sentinel**: `<data_dir>/HALT` — existence halts entries and
  defers re-arms; protective orders and closes always flow. In paper the
  harness submission path is the venue boundary (the sandbox is
  kernel-internal); the design's venue-adapter phrasing binds when a real
  adapter exists.
- **flatten-on-trip** defaults off and is honestly vacuous in the harness's
  realized-only accounting: the trip is detected at a settle, the position
  that caused it has already closed, and open positions never move realized
  equity. The flag exists for mark-to-market rails.

### Slice 5 — divergence budget + dashboard

Design §7: declared per-strategy drift budget paper-vs-backtest, surfaced in
the dashboard (fills, positions, today's vetoes, rail state).

## The hard known unknowns, honestly stated

1. **Restart rebuild semantics**: re-submitting protective brackets is not
   identical to never having died — a restart inside a bar can shift entry
   timing by one bar. Documented as a divergence class; the acceptance test
   measures it rather than hiding it.
2. **Sandbox venue + live clock + latency**: M2's measured fill semantics were
   bar-close; with a live clock and WS bars the same holds (bars are the only
   execution-relevant data), but tick-level intrabar behavior is out of scope
   for the paper engine by design — the dashboard reads bar-close truth.
3. **`TradingNode` blocking model**: `run()` owns the loop; the worker wraps
   it in its own thread/process and supervises it (systemd Restart=always,
   per the deployment doc). Test mode drives `run_async` inside pytest-asyncio.
4. **Validation is empty**: 16/16 REJECTED on both engines. M3's engine builds
   regardless; slice 4's registry enforces that nothing trades until a
   strategy passes the gate. That is not a blocker — it is the design's central
   promise being kept.

Slice-5 implementation notes (landed 2026-11-26):
- **The budget lives on the version, not the params.** `strategy_versions`
  gains `budget_dev_ticks` / `budget_entry_lag_bars` / `budget_missed_bars`
  (nullable — undeclared means the zero-drift defaults, honestly reported as
  defaults). The constructor is what the strategy IS; the budget is what the
  lifecycle tolerates. `register_version(..., budget=)` declares it; the
  roster carries it resolved into `DeskSpec.budget`.
- **Honest dimensions, three.** (1) per-fill price deviation in ticks from
  the ROLE-IMPLIED reference — the filling bar's close for market roles
  (fill-at-close parity; in the sandbox structurally zero, so the reading
  is a canary for venue-model fidelity and becomes real evidence the day a
  live venue adapter exists), the order's own level for stop/take-profit
  (deviation there is gap-through slippage, honestly signed; the protective
  distance itself is design, never drift). (2) entry timing lag in bars
  against the signal(k-1)→close(k) contract — exactly the measured async-chain
  divergence class made visible. (3) missed bars, the soak acceptance
  counter. Veto-vs-backtest divergence is NOT drift (it is the rails
  working); rearm cost is a documented divergence class of its own, not a
  budget dimension.
- **Measurement in the provenance path.** The desk's fill hook measures at
  fill-write time (frame lookup by floored bar-open key, tick size from the
  instrument cache) and persists `entry_dev_ticks`/`entry_ref_price`/
  `entry_lag_bars` on open_positions, plus `exit_dev_ticks` on trades.
  A rearmed position's entry evidence is recovered from its open row at
  close time — the restart does not get to erase the original entry's
  measurement. Breaches write `risk_events` rows with rail
  `divergence_budget`: visible, never silent.
- **Distributional comparison gates on n≥30 per side** (the validation
  gate's own statistical bar) and is descriptive when it exists — means,
  medians, whether the paper mean sits inside the backtest's p5–p95 —
  never a p-value over small autocorrelated samples. In M3's production
  reality it is always insufficient-data; the pure function and endpoint
  path are tested, and the honest note is what the dashboard shows.
- **The event-loop flake is fixed at the root.** The full-suite
  `No event loop available in test environment` failures (5 on pristine
  HEAD, growing with node count) were pytest-asyncio's loop lifecycle
  racing nautilus's construction-time `get_event_loop` — never the tests'
  content. `tests_trading/conftest.py` now guarantees every test a fresh
  main-thread loop; 250/250 pass in the combination run.
