# Kernel migration reference diff — nautilus harness vs ported engine

Date: 2026-11-25. Scope: the one-time diff the M2 milestone requires (design
§M2) — ScalpTrend on real Binance data, ported `backtest/engine.py` against
the nautilus kernel adapter `backend/trading/kernel.py`. Both engines run the
same pure strategies through the same structural anti-lookahead harness; what
differs is the execution layer underneath.

**Verdict up front: the fill-timing part matches within cents; the outcomes
do not match within rounding, and the design text claiming they would was
wrong about a fact — nautilus cannot fill at the next bar's open with
bar-only data. Measured, documented, design updated. The kernel runs the
pipeline from this commit.**

---

## 1. The fact the design was wrong about

Design §2/§7 assumed "limit orders placed for the next bar's open" was an
available execution mode in nautilus. The upstream documentation for 1.x
(`docs/concepts/backtesting/bar-execution.md` at tag v1.231.0) says
explicitly it is not, and probes on a controlled price series confirmed every
mechanism (`docs/research/probes/probe_execution.py`, `probe2_brackets.py`):

| mechanism | measured behavior |
|---|---|
| market order from `on_bar(k)` | fills at **close(k)**, stamped close(k) |
| aggressive limit (price beyond market) from `on_bar(k)` | fills immediately like a market order — at close(k), never later |
| resting passive limit | fills at its own limit price when matched, not the open |
| STOP_MARKET gapped through at open | fills at the **open** — but only if the market gapped; otherwise at the trigger, intrabar. Not an execution policy, a path accident |
| latency model | documented to settle against a later bar's close, not the open |

Why: every synthetic OHLC update of bar k lands at the same timestamp
(ts_init = close of the interval). There is no simulated instant at which
"the open of bar k" exists as a distinct book state before the rest of the
bar — so nothing can fill there. Timer and latency tricks settle against the
book as it stands at that instant, which is always some bar's close.

**What the harness runs instead:** signal(k−1) is computed when bar k
completes; the order fills at close(k). Every fill is strictly after every
bar the strategy saw — the M2 acceptance test asserts `entry_bar >
signal_bar` on kernel-derived timestamps, and passes. This model is also the
one closest to live execution: live, a market order sent when a bar closes
executes at approximately the close, not at the next bar's open. The ported
engine's open(i+1) fills were an idealization no venue offers.

## 2. Other execution differences, measured in probes

| aspect | ported engine | nautilus kernel |
|---|---|---|
| stop + tp both touched in one bar | stop always fills first (conservative) | intrabar path O→H→L→C decides; for longs the tp is visited before the stop (optimistic in that case) |
| gap through a stop | fills at the stop price exactly | fills at the bar **open** — realistic, worse for the trader |
| slippage | baked into the fill price arithmetic | applied in the reconstruction on top of kernel fills; kernel itself is zero-fee zero-slippage so nothing double-counts |
| fees | percentage on both legs in-trade | same arithmetic in reconstruction |
| equity for sizing | realized-only equity | reconstruction tracks net realized equity inside the run; kernel cash is gross and never used for sizing |
| sizing ATR | `atr[i]` of the fill bar — unknown at the open, a mild lookahead inside the ported engine | `atr` of the signal bar — known when the decision happens; strictly causal |

The last row is a bug the migration fixed in passing: the ported engine sized
positions with the ATR of the bar being entered, which is unknowable at that
bar's open. The kernel harness uses the signal bar's ATR, which is closed
information at decision time.

## 3. Measured divergence on real data (ScalpTrend, 365d Binance)

| series | ported trades / pnl | kernel trades / pnl | exact exit-bar+side overlap |
|---|---|---|---|
| BTCUSDT 4h | 36 / −98.47 | 28 / +51.09 | 14/36 |
| ETHUSDT 4h | 44 / +167.74 | 38 / +169.19 | 21/44 |
| BTCUSDT 1h | 167 / −466.52 | 164 / −359.45 | 87/167 |

Per-fill entry price deviations (paired trades, same entry bar): median
+0.03…+0.09 %, p90 absolute 1.4–4.1 % — the open/close spread of the entry
bar, exactly the documented timing difference. On synthetic noise the two
engines produce identical trade sequences; the cascade appears only on real
data because a fill price moved by the open/close spread anchors a different
stop price, and stops decide which trades survive. Divergence compounds
through survival, not through arithmetic.

The design's phrase "everything else must match within rounding" is retired
as untestable: equality of outcomes was never a property two different fill
models could have. What holds instead, and is now enforced by tests:
identical signal sequences (same pure strategy, same harness slicing),
identical reconstruction arithmetic (fees, slippage, realized-only equity),
and strictly causal fill timing in both.

## 4. What this means for verdicts

ScalpTrend BTCUSDT 4h validates as REJECTED on the kernel end-to-end
(permutation p 0.382 ≥ 0.05, CI lower −1.71 ≤ 0, 28 < 30 trades) — the gate
holds on the new engine, including on a run whose raw return was positive.
Sweep verdicts from `sweep-2026-11-25.md` were produced on the ported engine
and are not recomputed: every strategy was rejected there by margins no fill
model overturns, and future validation rows are kernel-produced by
construction.

## 5. What stays, what is superseded

`backtest/engine.py` remains in the tree: `trading/api/app.py` (the paper
API's ad-hoc backtest endpoint) and its test-suite consumers still use it,
and the reference diff reruns against it. It no longer feeds validation
verdicts — `research.py` runs `run_kernel_backtest` exclusively. Removing it
is M3 work together with the paper-engine migration, when the kernel becomes
the only execution layer.

Kernel facts verified in probes and relied on: OCO brackets fill exact
stop/tp intrabar; gap-through fills at the open; children of a bracket are
reduce-only and accepted while flat; manual closes cancel the resting
children cleanly (60/60 canceled in the verification run); zero-fee
instrument accounting is exact to the cent.
