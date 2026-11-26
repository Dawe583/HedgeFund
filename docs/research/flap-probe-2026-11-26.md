# Flap probe — repeated hard partitions do NOT reproduce the vendor failure

Date: 2026-11-26. Method: `docs/research/probes/probe_flap.py` — one
production-wired desk (BTCUSDT 1m) behind a killable local CONNECT proxy;
killing the proxy is a real network partition (TCP dies, the Rust
controller's reconnect machinery engages), restarting it on the SAME port
restores reachability. 8 cycles of 70 s partitions, verdicts measured per
cycle: quotes resuming vs the first post-reconnect closed bar.

## Measured

| cycle | verdict | recovery s | quotes resumed s |
|---|---|---|---|
| 0 | RESUMED | 52.1 | 28.1 |
| 1 | RESUMED | 50.1 | 28.1 |
| 2 | RESUMED | 48.1 | 28.1 |
| 3 | RESUMED | 52.1 | 28.1 |
| 4 | RESUMED | 50.1 | 28.1 |
| 5 | RESUMED | 48.2 | 28.1 |
| 6 | RESUMED | 50.2 | 28.1 |
| 7 | RESUMED | 50.1 | 28.0 |

**8/8 RESUMED, zero deaths, recovery tightly clustered at ~50 s** — 28 s of
reconnect backoff plus one bar-close boundary, reproducibly. The
fire-and-forget resubscribe survives hard-kill partitions even when
repeated: the failure shape the soak measured (hours of healthy-looking
reconnects with a dead kline stream) is NOT a probabilistic race in the
resubscribe-after-hard-partition path.

## What this rules in and out

Ruled out: the simple hypothesis that the resubscribe task races the
connection state on ordinary reconnects often enough to explain the soak —
eight consecutive hard partitions produced zero failures, and the recovery
time variance is ~2 s. If the race existed in this path it would have
shown at this sample.

Ruled in (untested, ordered by prior):

1. **Blackhole partitions** — outage shapes where TCP never dies (no RST,
   writes succeed into a void, death detected only by heartbeat timeout).
   The reconnect then starts from a different controller state (ping/pong
   timeout, not write failure), and the resubscribe-after-timeout path is
   a different code path with different races. Probeable with a silent-drop
   proxy mode: cost minutes to build, hours to run.
2. **Sleep/wake** — the host machine sleeping (lid close) freezes the
   process clock while the venue's 24h keys and server-side session state
   age. Resume semantics differ from network failure in everything that
   matters: local sockets may still be "open" against a dead peer, kernel
   buffers hold stale bytes. Not reproducible in a probe — the machine has
   to actually sleep.
3. **The Binance-side periodic connection drop** (24h connection lifetime,
   documented operational reality) — the server-initiated close is neither
   a partition nor a client failure; what the controller does with a
   server FIN after 24h is a third distinct path. Probeable only by
   waiting, or by a proxy that issues FIN on schedule — buildable,
   cheap.

## Standing

The feed watchdog merged today (exit 3 on quotes-alive-plus-bars-silent)
covers every one of these shapes symptomatically — it does not care which
path kills the stream, only that quotes flow while bars do not. What it
does not tell us is whether a restart actually HEALS the blackhole/sleep
shapes: if the failure is in the Rust controller's post-timeout state, a
fresh process re-issues cleanly by construction; if it is in something the
fresh process inherits (server-side session state, machine clock), it does
not. That distinction is the next probe's question, and it matters exactly
once — the first time the watchdog fires in production.

## Process notes

- The probe script is committed now (`probes/probe_flap.py`) — it was
  written and run uncommitted during the session; the evidence above is
  its verbatim output.
- `PYTHONPATH=.` is required when running probes from backend/ against
  repo-root scripts — the venv has no installed trading package, pytest's
  pythonpath setting does not apply to bare python. First launch attempt
  died on exactly this; the relaunch line is in the script's docstring.

## Blackhole probe — measured the same evening (2026-11-26)

The probe gained a blackhole mode: the relay keeps every socket open but
swallows all bytes — the failure shape the production 4h candle silence most
resembles. Four cycles of 70s partitions against a live production twin:

| cycle | partition | verdict | recovery after open |
|---|---|---|---|
| 0 | 70s blackhole | RESUMED | 52.2s |
| 1 | 70s blackhole | RESUMED | 46.2s |
| 2 | 70s blackhole | RESUMED | 52.2s |
| 3 | 70s blackhole | RESUMED | 50.1s |

**4/4 RESUMED, zero deaths** — the controller survives short blackholes
without any reconnect at all: TCP is silent-but-open, no FIN arrives, the
socket is still valid when bytes return, and the stream resumes in place.
The 46-52s "recovery" is the bar-close cadence catching up, not a failure.

What this does NOT answer, and why: 70s is shorter than the server's ping
cadence (minutes), so the heartbeat path never engaged. The production
failure was hours of silence with repeated reconnects and bulk backfills —
a shape closer to long partitions or repeated short ones than to a single
70s hole. A long-blackhole probe (5-10 min, crossing the heartbeat timeout)
is the next measurement; the probe harness now supports it with one flag,
and the watchdog is production coverage for every shape in the meantime.

## Long-blackhole probe — 6-minute partitions, measured the same night

The short-hole run left the key question open: does crossing the server's
ping cadence change anything? Three cycles of 360s blackhole partitions
against the live production twin:

| cycle | partition | verdict | recovery after open |
|---|---|---|---|
| 0 | 360s | RESUMED | 60.1s |
| 1 | 360s | RESUMED | 60.1s |
| 2 | 360s | RESUMED | 58.2s |

**3/3 RESUMED, zero deaths at six-minute holes.** The Rust client's own
liveness machinery either tolerates the gap or reconnects cleanly enough
that the stream resumes within a minute of partition end — in both cases
without operator intervention. The production failure shape (hours of
silence behind healthy-looking reconnects) is therefore NOT reproduced by
clean blackholes of any tested length: whatever killed the soak's 4h tape
is a different shape — partial connectivity (some flows passing, some
dropped), server-side session rot, or machine sleep — and the watchdog
remains the correct symptomatic cover exactly because the reproduction
remains open. The probe harness now supports arbitrary partition lengths
with positional args; the next shape to try is a partial blackhole
(klines-only filter) when the vendor question becomes load-bearing again.
