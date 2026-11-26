# M5 live-readiness audit — 2026-11-26

The written review design §M5 requires: every assumption in the chain —
fill models vs real venue behavior, fee/slippage honesty, what paper cannot
measure, reconciliation, the capital question, tax treatment. Every number
below is verbatim from the cited evidence file; nothing is extrapolated
without being labelled as arithmetic.

**Verdict up front: NOT READY for any live pilot on any venue, for a reason
that overrides every other line in this document: no validated edge exists.
The 2026-11-26 kernel sweep — 4 bots × 2 symbols × {4h, 1h}, 365 days of
real Binance klines, production parameters — measured 16/16 REJECTED
(`docs/research/kernel-sweep-2026-11-26.md`). The design states the
precondition plainly (§11): "No proven edge exists… the actual work starts:
finding one strategy that passes." That work is research, not engineering,
and no section of this audit — no mandate, no venue adapter, no
reconciliation procedure — substitutes for it. What follows therefore does
two things: (a) answers the capital/venue/mandate-shape questions so they
are settled *for the day an edge exists*, and (b) lists exactly what is
missing, in order, with what would close each item.**

---

## 1. Fill models vs real venue behavior

### What the sandbox matching engine does — measured

The harness contract: signal(k−1) computed when bar k completes; the market
order fills at **close(k)** (`docs/research/kernel-diff-2026-11-25.md` §1).
The choice is deliberate and the best available: live, a market order sent
when a bar closes executes at approximately the close — but "approximately"
is doing all the work, see §1.3.

| behavior | sandbox truth | evidence |
|---|---|---|
| market order from `on_bar(k)` | fills at close(k) exactly | kernel-diff §1 |
| gap through a stop | fills at the bar **open** — realistic, worse for the trader | kernel-diff §1/§2 |
| intrabar stop+tp both touched | intrabar path O→H→L→C decides | kernel-diff §2 |
| spread in replay | **zero** — the replay feeder synthesizes a zero-spread quote at each bar close | `desk/live.py` decision note 5 |
| spread in live-wired paper | real — production subscribes `@bookTicker`; fills cross the real spread, "honest, sub-cent at BTCUSDT depth" | `desk/live.py` decision note 5 |
| margin | accepted at leverage 50 because the adapter sets `margin_init=1.0` on Binance perps and the sandbox default of 1 would reject legitimate sizing — leverage 50 exists to keep the margin check **non-binding** | `desk/live.py` decision note 3 |
| fees/slippage | zero in the kernel venue; applied in the deterministic reconstruction on top of fills | `kernel.py` lines 20–24, 106–107 |
| order rejects | essentially none at pilot sizes — the one measured rejection class was a reduce-only race inside replay, not venue behavior | kernel-diff §6 |

Live evidence (n=2, `docs/research/live-smoke-2026-11-26.md` §8b): both
market-order fills landed within ~200 ms of the bar close at **exactly** the
closing print, deviation 0.0 ticks, because BTCUSDT's spread in that window
was zero-to-one tick. n=2 is not a sample; see missing-item (c).

### What a real venue does that the sandbox does not

Enumerated precisely — these are the structural gaps, not parameter errors:

1. **Queue position.** The sandbox fills a marketable order at the quoted
   price instantly. A real limit order joins a queue; fill probability is a
   function of position in it. Unmeasurable in paper — no queue exists.
2. **Partial fills.** Sandbox fills are whole. Measured replay divergence
   was "never partial, never random" (kernel-diff §6) — a property of the
   model, not of any venue.
3. **Latency.** The chain the desk runs (data task → risk → exec queue
   hops, kernel-diff §6) is the honest part; missing is network+venue
   latency and the queue of other people's orders ahead of ours.
4. **Funding rates.** USDT-M perps pay/collect funding every 8 hours. The
   kernel venue is zero-fee zero-funding; the reconstruction models only
   the taker fee and slippage (`kernel.py::_settle`). For positions held
   bars-to-days, funding is a continuous cost (or income) **completely
   absent from every backtest verdict this repository has produced.**
5. **Liquidation and margin discipline.** Sandbox margin is deliberately
   non-binding (leverage 50, decision note 3). Real leverage means real
   liquidation prices; nothing in the harness knows where they are.
6. **API rate limits and order rejection modes.** Weight limits, ban
   ladders, `MIN_NOTIONAL` rejects, reduce-only rejections that are venue
   truth rather than replay artifact — none exist in the sandbox. The desk
   carries **no keys at all** (decision note 1); the authenticated API
   surface is unmeasured by construction.
7. **Price gaps vs protective orders.** Measured realistic in the sandbox
   (gap-through fills at open) — this is the one real-venue cost the model
   does carry, shared by both engines (kernel-diff §1; divergence.py
   docstring: "execution cost both engines share").

### What paper structurally cannot measure

The divergence budget itself declares the boundary (`backend/trading/
divergence.py` module docstring): in the sandbox, per-fill price deviation
from the filling bar's close is **structurally zero** — "any nonzero reading
is evidence the venue model broke, and it becomes the paper → candidate_live
execution evidence **the moment a real venue adapter exists**, where fills
measurably land away from the close." Until that adapter exists the
instrument reads zero regardless of what real execution would cost. The
budget instruments three things — fill price deviation per role, entry
timing lag, missed bars — and explicitly refuses small-n statistics
(`compare_distributions` refuses below 30 trades per side, "fake statistics
over two trades are worse than no statistics"). Today's fill evidence is
n=2 (smoke §8b): exactly the sample size the budget refuses to draw
conclusions from.

## 2. Fee/slippage honesty

Modeled (validation harness, all 16 sweep cells):

| parameter | value | source |
|---|---|---|
| taker fee | 0.045 % per leg | `config.py` `taker_fee_pct` (BTConfig default) |
| slippage | 2.0 bps per leg, flat | `config.py` `slippage_bps` |
| application | both legs: `fees = (entry_px + exit_px) * qty * fee`, slippage adverse on both entry and exit | `kernel.py::_settle` |
| funding | **zero — unmodeled** | absence in `_settle` |

Real Binance USDT-M truth: VIP 0 taker 0.050 % / maker 0.020 % — measured
in the installed adapter's own static tier table
(`adapters/binance/futures/providers.py` lines 130–146, citing
binance.com/en/fee/futureFee). Every order the strategy fires is a market
order: taker-taker, no maker income.

Arithmetic per round trip, both sides taker: modeled cost 0.09 % (fees) +
0.04 % (slippage) = **0.13 % of notional**; real fee cost at VIP 0 is
0.10 %, so the harness's fee leg is 0.01 % *optimistic* — small, and the
wrong direction. The material gaps are elsewhere: real slippage is not a
flat 2 bps (it is zero-to-one tick at BTCUSDT depth in the n=2 sample but
widens exactly when stops matter — fast markets), and funding is entirely
absent. A position held 24h pays funding roughly three times; at a
representative 0.01 %/8h that is ~0.03 %/day of notional — arithmetic, not
a measurement — which at the harness's ~4× notional-to-equity sizing
(`engine.py` BTConfig comment: "risk_per_trade 2% over a 1×ATR stop…
implies ~4× equity notional at leverage 1") compounds to a cost of order
10 %/yr of equity before any trading result. No verdict row in either
sweep carries this cost.

At measured trade frequencies (kernel-sweep-2026-11-26, 365 days): the
rails-active counts (6–44 trades/year per cell) make fee drag small in
absolute terms; the pre-rails counts the strategies wanted (up to 779–790
trades/year for meanrev 1h) at 0.13 % round-trip and 4× leverage-implied
notional would cost ~1–4× equity per year in friction alone — arithmetic
on the sweep's own numbers. Conclusion: the fee model is close to honest
for taker fees, the slippage model is a placeholder that no measurement
yet constrains (n=2), and the funding model does not exist. The last one
is the fixable-before-pilot item; the middle one requires missing-item (c).

## 3. Reconciliation procedures

What exists today (`backend/app/routers/overview.py`):

- The consolidated total is **ledger wealth**; engine equity is displayed
  beside it, never summed (design rule D13 — the broker statement already
  contains the money).
- The reconciliation gap compares the ledger-projected statement (projected
  positions + cash-register projection) against the engine's latest
  `equity_points` row for the mapped institution.
- The time-mixing caveat is documented in the implementation itself: "a gap
  against last month's statement is time plus divergence, never divergence
  alone" — `statement_date` reports how fresh the photograph half is.
- Absence is honest throughout: no mapping, institution deleted, no engine
  equity — each a measured state, not an error page.

What broker-statement reconciliation for a live pilot would additionally
need: (a) per-fill reconciliation — each venue fill against the engine's
projection, the anchor+events discipline applied to the venue's own
fill/statement stream rather than the sandbox's; (b) the venue statement
import path — today the institution's ledger truth is typed in by the owner
(anchor+events), which does not scale to dozens of perp fills a day and
would need a statement/fill ingestion seam that does not exist; (c) funding
and fee line-items as first-class events in the ledger, since they are the
majority of real account movement on a perp account. None of this exists;
all of it is ordinary engineering once venue truth exists to reconcile
against.

## 4. The capital question — decision-points, not amounts

Measured facts: the ledger contains exactly one crypto-exchange institution,
`id=1, name=BitGet` (read-only query of `data.db` `institutions`), and the
`trading_institution_id` mapping setting is **unset** — the reconciliation
machinery reports `no-mapping` today. Note what this implies: the account
the ledger photographs is BitGet, while every data/execution measurement in
this audit is Binance. A live pilot on Binance requires either a new
institution row plus mapping or a BitGet venue adapter; the two planes must
point at the same account or the reconciliation line measures nothing.

Decision-points for the owner, framed as constraints the mandate system is
designed to express (design §6 Layer 2: "an immutable row of hard caps —
max order notional, max exposure, allowed instruments, max trades per day,
consent expiry… **funding bounds**"), never as recommended numbers:

1. **Which account**: a dedicated venue account, separate from any other
   holdings — isolation is what makes the mandate's funding bound
   meaningful and the reconciliation legible. One institution row, one
   mapping, one venue adapter.
2. **How much**: bounded above by the mandate's funding bound — a number
   the owner writes into an immutable mandate row through the confirmation
   flow, deliberately unreachable by any agent or strategy (§6 Layer 2).
   The audit constrains the shape, not the amount: small enough that the
   12 % kill-switch's worst day is a tuition payment, since the pilot's
   product is evidence, not return.
3. **Funded how**: the ledger already models this — a cash movement into
   the institution is an ordinary `cash_moves` event with full provenance;
   the transfer becomes the first anchor the reconciliation measures
   against. Transfer mechanics, custody chain, and whether the venue
   account is fresh or existing are owner decisions outside the codebase.
4. **Venue choice**: the design's non-recommendation stands (§11: "One
   venue, chosen in M5 — IBKR paper is the leading candidate… crypto perps
   are the worse first live venue in every dimension except convenience").
   This audit adds the measured weight to that judgment: all execution
   evidence in this repository is Binance perps, zero is IBKR — a pivot to
   IBKR would discard the soak evidence base and restart it.

## 5. Tax treatment of the trading account

What the repo knows: `backend/app/tax.py` is deliberately a declared
estimate, not an engine — one flat user-overridable percentage over realized
capital gains and dividends, documented with the failure mode in the
module docstring ("precise and wrong… is worse than being openly
approximate"). It knows nothing about derivatives.

What the repo does not know, and must not fake: the owner's jurisdiction's
treatment of crypto-perpetual futures — whether perp pnl is capital gains,
income, or a derivatives regime; whether funding payments are deductible
costs or separate taxable events; lot-matching and reporting obligations;
the interaction with the existing ledger's realized-gain arithmetic. **This
is an open question requiring professional advice in the owner's
jurisdiction before any live order.** The honest engineering contribution
exists already: every fill the desk produces carries provenance
(`risk_events` inputs, the audit projection of positions/fills — design §11
nautilus-opacity mitigation), so whatever the treatment turns out to be,
the records to support it are being written today. What must never happen
is extending `tax.py` to perps with a guessed rule — its own docstring
names that as the line-crossing failure mode.

## 6. What is missing before any pilot — the explicit list, ordered

1. **A validated edge exists.** Precondition for everything; currently
   false for every strategy: 16/16 REJECTED on the kernel sweep with rails
   (`docs/research/kernel-sweep-2026-11-26.md`), previously rejected on the
   ported engine and kernel baseline — the rejection has survived three
   independent measurement configurations. Close: a validation row passing
   permutation p < 0.05, bootstrap CI lower bound > 0, walk-forward
   consistency, ≥30 trades — the gate is enforced in code (`registry.py`:
   transitions impossible without the verdict rows). Nothing else on this
   list matters until this is true.
2. **Soak verdict.** pending — verdict due ~2026-11-27 00:37 UTC, soak doc
   docs/research/soak-2026-11-26.md. The soak adds: 24h of `missed_bars = 0`
   continuity evidence on two tapes (4h production-realistic, 1m density),
   restart/rearm behavior if any, heartbeat reliability, feed-stale
   semantics at production interval, and — critically — the first real
   sample of live fills (the 1m scalp process fired its first entry 90 s
   after boot: `fills 1, open_position true` at 00:33).
3. **Order-path evidence at scale.** Today n=2 live fills, both perfect
   (smoke §8b). `divergence.py` refuses statistics below 30 trades per side
   for the correct reason. Close: the divergence budget's instruments
   reading a month-scale paper sample of a strategy that actually trades —
   fill deviation per role in ticks, entry lag distribution, then the same
   instruments on the real adapter (item 5).
4. **Mandate machinery armed + signoff.** Status: partially built, never
   armed. The halt sentinel rail exists and is enforced in the harness at
   entry and rearm (`rails.py` rail 4, fail-closed, corrupt-file-halts);
   the manual kill-switch row and approval-card flow exist (M4); the
   `candidate_live → live` transition is structurally impossible today —
   `registry.py` raises unconditionally: "requires a mandate (M5), which
   does not exist". Mandate rows themselves, the order-guard chain, and the
   append-only hash-chained audit ledger are not yet implemented. Close:
   the design's M5 acceptance — the machinery demonstrably blocks a
   violating order in tests even with every software layer above bypassed
   (sentinel file test) — plus the owner's signed-off audit, meaning this
   document superseded.
5. **A real-venue execution adapter.** Execution today is the local sandbox
   wearing the BINANCE label; "there is no Binance exec client in this
   process" (`desk/live.py` decision note 1). Nothing about keys,
   authentication, order management against a real API, rate limits, or
   reject handling is written or measured. Design §M5 acceptance: "the
   venue adapter is wired to testnet/paper only" until signoff. Close:
   adapter built behind the same `DeskNode` seam the replay/live-data
   clients already share, exercised against venue testnet first, with the
   divergence budget's structurally-zero fill-deviation reading becoming a
   real measurement for the first time.
6. **Reconciliation against real statements.** §3: per-fill reconciliation
   and a statement ingestion seam do not exist. Close: the ledger importing
   venue truth and the reconciliation gap reading near-zero over a pilot
   month — today it reads `no-mapping` because the institution mapping is
   unset.
7. **Tax/legal resolution.** §5: professional advice in the owner's
   jurisdiction on derivatives treatment before the first live order.
   Close: a written answer the ledger's record-keeping can service.

## 7. What the machinery already guarantees — the positive side

The audit is not only a list of gaps. Measured, in code, today:

- **Layer-0 rails are live in both backtest and paper**, evaluated before
  any entry exists, deterministic arithmetic over realized truth: 12 %
  drawdown kill-switch (one-way latch), 5 % daily loss limit (the day is
  forfeit, not the moment), loss-streak cooldown (3 losses → 4h), manual
  kill-switch row read at entry cadence fail-closed ("a rail that cannot
  see its state is a rail that says no"), halt sentinel file checked at
  entry and rearm, protective exits never blocked. Every firing writes
  `risk_events` with its inputs — "a rail that cannot explain itself is
  removed, not trusted" (`rails.py` module docstring). Measured effect in
  the sweep: cells that pre-rails ground on to 67–100 % drawdowns now stop
  at ~12–14 % — "an account that bleeds to the kill-switch stops bleeding"
  (kernel-sweep-2026-11-26).
- **The lifecycle gate is enforced in code, not discipline** (design D7):
  no evidence row, no transition; the empty paper roster is the honest
  measured end state, and the registration path demonstrably refuses
  promotion of a rejected validation row (kernel-sweep-2026-11-26,
  registration-path demonstration). `candidate_live → live` cannot happen
  at all until a mandate exists.
- **Human-in-the-loop transitions carry staleness fingerprints** — a card
  whose inputs moved returns 409 (design §6 Layer 1, M4 landed).
- **The paper data path is production-honest**: real venue instrument truth
  (tick 0.10, step 0.001 parsed from exchangeInfo), only closed bars
  published, boot-window gaps recovered by REST backfill (measured
  before/after on the same boot geometry: 1 missed → 0 missed, smoke §5),
  WS reconnect recovery automatic and measured (40.1 s for one cycle, smoke
  §8a), shutdown clean in ~10–20 s.
- **The divergence budget instruments exactly the right quantities** and
  refuses to fake statistics at small n (divergence.py).
- **Never-auto is structural**: design §11 — "Do not arm live trading
  outside the M5 audit process, whatever the paper results look like. A
  good paper run is a candidate, not a license." This document is that
  process, and its answer today is: not yet — items 1–7, in order.
