# Live Binance wiring — smoke evidence

Date: 2026-11-26. Scope: M3 slice 2 — the paper desk booted against the real
Binance USDT-M futures tape, public endpoints only, no keys. 1m klines rather
than the production 4h because the smoke needs bar closes inside minutes, not
hours; the data path is identical at every interval.

**Verdict up front: the production wiring carries the live tape end-to-end —
real adapter instruments, closed bars at exact wall-clock cadence, zero
post-boot gaps across 17 measured minutes, feed health tracking, clean
supervised shutdown. No orders fired because ScalpTrend (a 4h strategy) does
not signal on a 1m frame inside minutes — correct behavior, not noise. One
boot-window bar miss is explained below; it is a seed/backfill gap, not a
feed failure, and it is the top soak risk.**

---

## 1. What ran

```
cd backend
DATABASE_URL="sqlite:////tmp/smoke-desk.db" DATA_DIR=/tmp/smoke-desk-data \
  uv run python -m trading.desk.runner --symbol BTCUSDT --timeframe 1m --bot scalp --stale-after 180
```

- boot: 2026-11-25 23:23:59 UTC (log lines are machine-local CET, +1h)
- seed: 1499 warm-up bars from `GET /fapi/v1/klines` (public REST), the
  still-forming bar dropped; independent re-fetch verified continuity: all
  1498 inter-bar steps exactly 60 s, zero irregular steps
- execution: the local sandbox exchange wearing the BINANCE venue label —
  no real money exists anywhere in this topology
- the process ran 17 minutes (longer than planned because the pre-fix
  runner could not shut itself down — the extra minutes are free evidence)

## 2. Adapter facts the wiring depends on (measured in the installed
nautilus_trader 1.231.0)

| fact | evidence |
|---|---|
| public kline data needs no API key | `BinanceDataClientConfig` docstring: "If None, the client will work for public market data only"; keyless provider falls back to the venue fee-tier table (`futures/providers.py::load_ids_async`) |
| only CLOSED klines are published | `_handle_kline` drops every update with `x=False` — the forming candle never reaches the engine |
| `ts_event` is the kline CLOSE time | `parse_to_binance_bar` stamps `millis_to_nanos(kline.T)`; the harness convention is open-time, so `IncrementalFrame` normalizes keys by interval flooring — exact because Binance T is the interval's last millisecond, strictly inside the interval |
| instruments arrive with real tick/step sizes | `futures/providers.py::_parse_instrument` parses tickSize/stepSize out of exchangeInfo; smoke observed `price_increment 0.10`, `size_increment 0.001`, `min_quantity 0.001` for BTCUSDT-PERP |
| instrument delivery ordering is safe | data `connect()` only schedules the async instrument load while the sandbox exec client's msgbus subscription is synchronous in the same tick (`system/kernel.py::_connect_clients`, `live/data_client.py::connect`); late arrivals still register because `SimulatedExchange.update_instrument` adds the book on first sight |
| the kline stream has no sequence id | integrity detection is wall-clock staleness (FeedHealth) plus bar-open arithmetic (`frame.missed_bars`); the arithmetic detects a gap one bar late by construction — nothing finer exists without consuming the raw stream, which the adapter does not expose |
| `_reconnect` only re-subscribes order-book depth streams | `BinanceCommonDataClient._reconnect` iterates `self._book_depths` — nothing else. Kline subscriptions surviving a WS reconnect are unverified (see risks) |

## 3. Venue alignment decision

Venue label BINANCE end-to-end: instrument ids are `BTCUSDT-PERP.BINANCE`,
and the sandbox exchange's venue IS BINANCE. Nautilus keys cache, order
routing and matching books by the full InstrumentId including venue; there
is no venue translation layer, so the sandbox must wear the data's label.
Relabeling the data client to PAPER was rejected: the tape would carry a
venue label claiming it is the sandbox's own — provenance fraud for one
config flag's convenience. Nothing about the BINANCE label triggers
real-money behavior: execution routing resolves to the registered client
for the venue, which is the sandbox. Replay tests keep their `.PAPER` ids
end-to-end and pass unchanged (7/7 desk, 7/7 kernel).

## 4. Smoke measurements

Primary run (23:23:59–23:40 UTC, ~17 min of tape):

| measure | value | expectation | verdict |
|---|---|---|---|
| closed bars processed | 16 over 16 fully-covered minutes (uptime 64–1020 s) | 1 per minute, ±1 | exact cadence, never late enough to go stale |
| `missed_bars` after boot | 0 from the 2nd bar onward | 0 | pass |
| `missed_bars` at boot | 1 | — | boot-window artifact, explained in §5 |
| feed_stale (180 s timeout) | true only before the first bar | false while running | pass |
| frame growth | 1499 seed → 1515 rows, +1 per bar | — | pass |
| fills / positions | 0 / 0 | any | none — ScalpTrend never signaled on 1m tape; correct, not noise |
| instrument in kernel cache | `BTCUSDT-PERP.BINANCE`, tick 0.10, step 0.001 | binance truth | pass |
| errors beyond the explained gap | none | — | pass |

Shutdown verification runs (post-fix runner, shorter windows):
- run A: SIGTERM at uptime ~130 s → "shutdown requested" logged, final
  STATUS printed, process exited — node thread dead, exit path clean.
  Shutdown latency was 52 s with a 60 s monitor join tick; the tick is now
  10 s (measured stop() itself ≈ 10 s, so SIGTERM-to-exit is bounded ~20 s).
- run B: boot 40 s, SIGTERM, clean exit ~20 s, `missed_bars: 0` (booted far
  enough from the minute boundary that no bar closed during connect).

## 5. The boot-window miss, and why it is not a feed failure

Boot was at 23:23:59.652 — 348 ms before the 23:23 candle closed at
23:24:00. The seed fetch still saw that candle forming and correctly
dropped it; the WS connect + subscribe handshake (~1–2 s) finished after
the close. Bar 23:23 therefore exists nowhere: not in the seed, not on the
wire. The frame arithmetic caught it exactly as designed:
`bar stream gap: 1 closed bar(s) missing before open 23:24:00+00:00`,
`missed_bars` pinned at 1 for the whole run, zero further gaps in 16
minutes of tape.

The fix is implemented and measured (hardening item 1): `IncrementalFrame`
takes a `backfill` callable wired to `fetch_klines_range` in production.
When a key gap opens — at boot, at restart, or after any silence — the
frame fetches the missing window synchronously inside `on_bar_close`,
inserts the recovered bars BEFORE the triggering bar's append (order-safe:
every key in the window is strictly between the last seeded key and the
incoming one), and counts them in `backfilled_bars`; only what REST cannot
recover counts in `missed_bars`. Insertion is strictly-inside filtered:
REST windows are inclusive, and the boundary rows (already seeded /
arriving by wire) must never insert — the general case a restart produces
(multi-bar gaps) is unit-verified for 1-bar, 3-bar, partial-coverage and
naive-timestamp inputs.

Deliberate boundary-boot measurement (2026-11-26 00:08:58.965 UTC boot,
~1 s before the minute close): the 00:08 bar closed during connect, the
first wire bar was 00:09, the gap detector fired, REST recovered the 00:08
bar — log: `backfilled 1 bar(s) the stream missed before open
2026-11-26 00:09:00+00:00`. Result: `missed_bars 0`, `backfilled_bars 1`,
frame rows continuous (1499 seed → 1501 after first wire bar = seed +
backfill + wire). Before/after on the same boot geometry: 1 missed / 0
missed. The boot-time lottery is closed.

## 6. Shutdown path — vendor defect found and worked around

The nautilus kernel installs asyncio loop signal handlers
(`system/kernel.py::_setup_loop`) that consume SIGINT/SIGTERM into a
loop-thread callback `TradingNode._loop_sig_handler` → `self.stop()`.
Measured: minutes after the signal the process still consumes quotes, no
shutdown logs, SIGKILL the only exit. `node.stop()` called from the MAIN
thread completes in ~10 s (probe-measured: node thread dead in seconds).
The runner therefore replaces the kernel's handlers with its own
event-flag handlers; the monitor loop performs the stop. This is now the
only shutdown path the desk uses; systemd SIGTERM lands identically.

## 7. Observed noise, and why it is noise

`OrderMatchingEngine: Skipping stale quote` warnings cluster at minute
boundaries (~120/min of tape on this machine). Cause: Binance bookTicker
messages carry no exchange timestamp, so the adapter stamps receive time;
quotes arriving microseconds before a bar close are processed after the
bar (whose ts_init is the close time) advanced the book clock — the
sub-millisecond inversion makes them "stale". Effect: a bounded fraction
of book updates drops around bar boundaries; fresh quotes keep flowing
within a second, so the executable market is never absent at decision
time. A divergence class to watch in fill inspection, not a data-path
defect.

## 8. Hardening probes (2026-11-26, after the initial smoke)

### 8a. WS reconnect probe — klines DO resubscribe, recovery is automatic

Method: the desk's data client pointed at a killable local CONNECT proxy
(`proxy_url` threads to both ws clients, verified in `binance/data.py`);
killing the proxy is a real network partition — TCP dies, writes fail, the
Rust ws controller's reconnect machinery engages. Restarting the proxy
restores reachability. Partition length 80 s, spanning one bar close.

Measured sequence: 2 bars pre-partition (`missed 0`) → proxy killed →
80 s of silence (feed_stale false throughout — the 180 s timeout correctly
does not trip on sub-timeout partitions) → proxy restarted → bars resumed
**40.1 s later** (the Rust controller's reconnect backoff, capped at 30 s,
plus handshake and resubscription) → the first post-reconnect bar keyed a
gap, the REST backfill recovered the one missed bar.

Result: `missed_bars 0`, `backfilled_bars 1`, bars flowing. The vendor
fear from §2 was unfounded at the layer that matters: `data.py`'s
`_reconnect` indeed only re-snapshots book depth, but kline resubscription
is owned by the *ws client* layer — `BinanceWebSocketClient._handle_reconnect`
calls `_resubscribe_client` with the full stream list. No recovery code was
needed on our side; the backfill closed the data hole the partition opened.
Remaining caveat: reconnects longer than the FeedHealth timeout flip
feed_stale — detection works as designed; recovery time is backoff-bound
(measured 40 s for one cycle).

### 8b. Order-path live evidence — fills at exactly the bar close

Probe: production-wired desk, engineered test strategy (`/tmp/probe_strategies.py`,
explicitly a measurement harness, never in the production roster) — long at
the 4th live bar with wide brackets, flat exit after 3 bars held.

| measure | entry | exit (signal_exit) |
|---|---|---|
| fill price | 60960.0 | 61152.0 |
| filling bar close (exchange REST truth) | 60960.0 (00:15 bar) | 61152.0 (00:18 bar) |
| deviation | 0.0 — zero ticks | 0.0 — zero ticks |
| fill timestamp | 152 ms after bar close | 177 ms after bar close |

Both market orders filled within ~200 ms of the bar close at EXACTLY the
closing print — BTCUSDT's spread inside that window was zero-to-one tick
and the fill did not cross measurably worse than the close. The stale-quote
drop class (§7) cost nothing measurable in this sample of 2 fills; the
soak's larger sample is where to confirm. Margin at leverage 50 accepted
the harness-sized qty (0.009 BTC, risk-based) without rejection. Bracket
lifecycle: protective children submitted after the entry fill, cancelled
cleanly on the signal exit — the full lifecycle closed with correct
economics (net pnl +1.01 after the harness's reconstruction arithmetic).

### 8c. Heartbeat lamp — the desk now reads as a running engine

The kernel desk never wrote BotStatus rows; `/api/trading/status` read
`offline` while the desk traded. The runner now writes per-bot heartbeats
at boot, every monitor cadence, and `running=False` on shutdown. Measured
end-to-end against a live uvicorn on the shared production database:
`engine_state` flipped `offline` → `running` with
`last_tick_at` tracking the runner's cadence; SIGTERM shutdown wrote
`running=0` and the process exited clean.

The verification exposed a real endpoint bug, fixed in passing: the
status filter `BotStatus.name.notlike("__%")` used unescaped underscores —
LIKE wildcards — excluding every bot name longer than one character
('scalp' NOT LIKE '__%' evaluates FALSE in sqlite). The lamp would have
read offline forever regardless of heartbeats. Fixed with proper escaping;
measured correct against live rows before and after.

## 9. Risks toward the 24h soak (updated post-hardening)

1. ~~Boot/restart-window bar miss~~ — closed by the backfill (§5).
2. ~~WS reconnect behavior~~ — verified working, automatic (§8a); residual:
   multi-minute outages flip feed_stale (correct) and recovery is
   backoff-bound, tens of seconds per cycle.
3. **Shutdown takes ~10–20 s.** stop() itself is ~10 s (client
   disconnect timeouts); systemd needs `TimeoutStopSec` ≥ 30 in M6.
4. **Fill quality sample is n=2.** Both fills hit the exact close; the
   soak is the real sample. If entries systematically cross worse than
   close, that cost is unmodeled by backtest parity.
5. **`update_instruments` re-publishes hourly** — benign (sandbox
   `update_instrument` handles it); provider is keyless so fee rates are
   static-tier.
6. **Backfill is synchronous inside `on_bar_close`** — a REST fetch of
   several hundred ms blocks the loop thread once per gap. At bar cadence
   (minutes) this is nothing; at 1s bars it would deserve a queue. The
   desk trades minutes, documented not fixed.
