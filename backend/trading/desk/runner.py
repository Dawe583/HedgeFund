"""Production desk runner — `python -m trading.desk.runner`.

Boots the live-wired paper desk against the real Binance tape:

1. flock single-worker guard first — a second desk process trading the same
   book is double sizing, not redundancy
2. seed history from the binance REST fetcher (the SEED CONTRACT seam —
   `seed_history(symbol, timeframe) -> list[dict]`, newest-last; the
   forming bar is dropped, see live.seed_drop_forming_bar)
3. re-arm open positions from the DB before bars flow
4. run the node; supervise from the main thread

Supervision is deliberately thin: the runner exits non-zero when the node
thread dies or a fatal boot step fails; restart policy (systemd) is M6's.
The monitor loop's STATUS lines are the operational evidence surface —
bars processed, stream gaps, feed health, fills — and the final STATUS
line is what smoke runs harvest.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time

from trading.config import get_settings
from trading.kernel import TIMEFRAME_NS
from trading.models import init_schema, make_engine, make_session_factory

log = logging.getLogger("trading.desk.runner")

def control_strategies() -> dict:
    """The instrumentation-control catalog — deliberately OUTSIDE
    research.STRATEGIES, because the catalog is alpha-candidate code and
    controls are not candidates: they are measurement instruments the desk
    runs so its operational plane (veto tape, divergence, reconciliation)
    works against expectations known by construction. Same entry shape as
    STRATEGIES so resolution treats them uniformly — registration, never
    resolution, is where the honesty differs."""
    from trading.bots.random_control_bot import RandomControl

    return {
        "randomctl": {
            "key": "randomctl",
            "cls": RandomControl,
            "name": "RandomControl",
            "timeframe": "1h",
            "symbols": ["BTCUSDT"],
            "description": (
                "Instrumentation control — random entries, expectations known by "
                "construction, never alpha. Registered through registry.register_control."
            ),
        }
    }


def resolve_roster_specs(session_factory) -> list:
    """The desk's roster IS the lifecycle registry: every strategy version in
    state `paper` becomes one DeskSpec per universe symbol, parameters and
    timeframe as registered. Nothing else trades — the static STRATEGIES
    catalog is available code, never capital. An empty roster is the honest
    end state of a registry with zero validated strategies: the desk boots
    empty and that emptiness is the gate working, not a bug."""
    from trading.desk.node import DeskSpec
    from trading.registry import roster
    from trading.research import STRATEGIES

    specs = []
    session = session_factory()
    try:
        entries = roster(session)
    finally:
        session.close()
    for entry in entries:
        catalog = STRATEGIES.get(entry["key"])
        if catalog is None:
            # not an alpha candidate — the control catalog is the only other
            # thing the lifecycle may lawfully hold in paper
            catalog = control_strategies().get(entry["key"])
        if catalog is None:
            log.error(
                "registered version %s v%d references catalog key %r which no longer exists — skipped, never silently traded",
                entry["key"], entry["version"], entry["key"],
            )
            continue
        for symbol in entry["universe"]:
            specs.append(
                DeskSpec(
                    bot=f"{entry['bot']}-{symbol.lower()}" if len(entry["universe"]) > 1 else entry["bot"],
                    symbol=symbol,
                    timeframe=entry["timeframe"],
                    strategy_cls=catalog["cls"],
                    strategy_params=entry["params"],
                    # the registered version's declared divergence budget —
                    # the roster carries it resolved (defaults when the
                    # version never declared one)
                    budget=entry["budget"],
                )
            )
    return specs


def load_seed_history():
    """The seed seam. trading.desk.binance_history is a sibling workstream's
    deliverable; when it has not landed the boot cannot seed, and a cold
    node trading on noise is worse than no node — fail clearly."""
    try:
        from trading.desk.live import seed_drop_forming_bar
    except ImportError as exc:
        raise SystemExit(
            "trading.desk.binance_history is required for seeding but not importable "
            f"({exc}). The seed fetcher is a parallel deliverable — without it the "
            "desk would boot cold and trade on un-warmed features."
        )
    return seed_drop_forming_bar


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="trading.desk.runner")
    p.add_argument(
        "--stale-after",
        type=float,
        default=None,
        help="feed staleness timeout in seconds (default 1.5x the bar interval, floor 120s)",
    )
    return p.parse_args(argv)


def build_desk(args, seed_history):
    """Boot the desk the registry owns. Returns None when the roster is
    empty — with zero validated strategies the lifecycle permits nothing,
    and a desk trading a static fallback list would be the gate NOT working."""
    from trading.desk.live import build_production_desk

    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_schema(engine)
    session_factory = make_session_factory(engine)

    specs = resolve_roster_specs(session_factory)
    if not specs:
        log.warning(
            "roster empty: no strategy version in state paper — the desk boots nothing. "
            "Validate a strategy (trading.research validate) and register it "
            "(trading.research register) to make the roster non-empty."
        )
        return None
    # mixed-timeframe rosters use the tightest interval for the staleness
    # floor — a loose timeout on the fastest bot hides its death
    interval_s = min(TIMEFRAME_NS[s.timeframe] for s in specs) / 1e9
    stale_after = args.stale_after if args.stale_after is not None else max(120.0, 1.5 * interval_s)

    return build_production_desk(
        specs=specs,
        session_factory=session_factory,
        seed_history=seed_history,
        feed_stale_after_s=stale_after,
    )


def status_line(desk, started_monotonic: float) -> str:
    """One JSON object with the desk's operational facts — the evidence
    surface for smoke runs and the soak."""
    out = {"uptime_s": round(time.monotonic() - started_monotonic, 1), "bots": {},
           "heartbeat_failures": getattr(desk, "heartbeat_failures", 0)}
    for spec in desk.specs:
        bot = spec.bot
        strat = desk._strategy_for(bot)
        state = desk.states[bot]
        frame = desk.frames[bot]
        instrument = desk.node.cache.instrument(strat.instrument_id)
        out["bots"][bot] = {
            "bars_processed": strat._k + 1,
            "frame_rows": len(frame),
            "missed_bars": frame.missed_bars,
            "backfilled_bars": frame.backfilled_bars,
            "feed_stale": desk.feed_health[bot].stale(),
            "fills": len(state.fills),
            "positions": len(state.positions),
            "open_position": strat._open_pos is not None,
            "instrument": None
            if instrument is None
            else {
                "id": str(instrument.id),
                "price_increment": str(instrument.price_increment),
                "size_increment": str(instrument.size_increment),
                "min_quantity": str(instrument.min_quantity),
            },
        }
    return "STATUS " + json.dumps(out)

# The watchdog distinguishes the two dead-feed shapes the soak measured
# apart. Quotes silent for this long means the wire itself is dead — a
# partition or a venue outage — and restarting the desk changes nothing,
# so the watchdog stays its hand. Quotes alive while bars never close is
# the vendor failure shape: the websocket client reconnects, the
# fire-and-forget resubscribe silently fails, and the kline stream never
# comes back. Only a fresh process re-issues the subscription cleanly.
QUOTE_ALIVE_S = 120.0


def feed_watchdog_verdict(desk, started_monotonic: float) -> dict | None:
    """Decide whether the feed failure shape justifies a process restart.

    Returns a dict describing the first offending bot, or None. The rule:

    - bars silent longer than 2x the staleness timeout (the timeout is
      already 1.5x the bar interval, so 2x is three bar-intervals of
      continuous silence — measured against the BOOT for a feed that never
      delivered, not against infinity),
    - while this bot's instrument kept delivering quotes within
      QUOTE_ALIVE_S (the wire is fine — the subscription is what died),
    - and the desk is past its boot grace of one staleness timeout (a fresh
      feed is legitimately stale until the first close; on slow tapes that
      is most of an interval, so the first verdict can only form after the
      timeout, and the 2x duration requirement does the rest).

    A feed silent because the NETWORK is silent never trips this: quotes
    die with everything else in a partition, and restarting into a
    partition just re-seeds into the same dead wire.
    """
    quote_beats = getattr(desk, "quote_beats", None) or {}
    if not quote_beats:
        return None  # replay/test wiring or pre-tick boot — nothing to judge by
    now = time.monotonic()
    if now - started_monotonic < desk.feed_stale_after_s:
        return None
    for spec in desk.specs:
        health = desk.feed_health[spec.bot]
        silent = health.stale_for()
        if silent == float("inf"):
            silent = now - started_monotonic
        if silent <= 2 * desk.feed_stale_after_s:
            continue
        instrument_id = desk.instrument_ids.get(spec.bot)
        beat = quote_beats.get(instrument_id)
        if beat is not None and now - beat <= QUOTE_ALIVE_S:
            return {
                "bot": spec.bot,
                "bars_silent_s": round(silent, 1),
                "last_quote_s": round(now - beat, 1),
                "stale_after_s": desk.feed_stale_after_s,
            }
    return None

def write_heartbeats(desk, running: bool) -> None:
    """One BotStatus row per bot — the /api/trading/status engine lamp reads
    heartbeat recency (HEARTBEAT_ALIVE_S=120, the 60s monitor cadence fits
    with slack). A failed write must never kill the monitor loop: the lamp
    going dark is a symptom to log, not a failure to propagate."""
    import datetime as dt

    from trading.models import BotStatus

    session = desk.session_factory()
    try:
        for spec in desk.specs:
            row = session.get(BotStatus, spec.bot)
            if row is None:
                row = BotStatus(name=spec.bot, mode="paper")
                session.add(row)
            row.running = running
            row.last_heartbeat = dt.datetime.now(dt.UTC)
            row.note = f"desk kernel | {len(desk.states[spec.bot].positions)} positions"
        session.commit()
        desk.heartbeat_failures = 0
    except Exception:
        session.rollback()
        desk.heartbeat_failures = getattr(desk, "heartbeat_failures", 0) + 1
        log.exception("heartbeat write failed — engine lamp will read offline")
    finally:
        session.close()



def write_rail_snapshots(desk) -> None:
    """Per-bot rail state into the kv store — the /api/trading/rails endpoint
    reads these rows. Written at the monitor cadence beside the heartbeats:
    the rails themselves live in kernel memory (correctly — they measure the
    tape, not the wall), and this snapshot is the honest rendering of what
    they last computed, never a second source of truth. Same failure
    discipline as the heartbeats: a failed write is a symptom to log."""
    import time as _time

    from trading.models import set_state

    session = desk.session_factory()
    try:
        now_s = _time.time()
        for spec in desk.specs:
            state = desk.states[spec.bot]
            rails = state.rails
            if rails is None:
                continue
            book = state.exposure_book
            # per-bot instrument notional: key the book by the instrument
            # prefix this bot trades — the book is desk-wide by design, and
            # the per-bot slice of it is what belongs in the bot's row
            prefix = spec.symbol.upper()
            bot_notional = sum(
                book.instrument_notional(iid) for iid in list(book._by_instrument) if iid.startswith(prefix)
            )
            snap = rails.snapshot(now_s)
            snap["exposure"] = {
                "instrument_notional": round(bot_notional, 6),
                "gross_notional": round(book.gross_notional(), 6),
                "symbol_cap": spec.bt_config.max_symbol_exposure,
                "gross_cap": spec.bt_config.max_gross_exposure,
            }
            snap["vetoes_total"] = len(state.vetoes)
            # slice 5: the divergence budget as declared and the feed counters
            # the budget is measured against — per-fill evidence lives on the
            # trade/position rows themselves; the snapshot carries what only
            # the live process knows (the frame's counters die with it)
            snap["divergence"] = {
                "budget_dev_ticks": spec.budget.dev_ticks,
                "budget_entry_lag_bars": spec.budget.entry_lag_bars,
                "budget_missed_bars": spec.budget.missed_bars,
                "missed_bars": desk.frames[spec.bot].missed_bars,
                "backfilled_bars": desk.frames[spec.bot].backfilled_bars,
            }
            import datetime as _dt

            snap["written_at"] = _dt.datetime.now(_dt.UTC).isoformat()
            set_state(session, f"rails/{spec.bot}", snap)
    except Exception:
        session.rollback()
        log.exception("rail snapshot write failed — /api/trading/rails goes stale")
    finally:
        session.close()



def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = parse_args(argv)
    from trading.desk.worker import acquire_worker_lock

    lock = acquire_worker_lock()
    if lock is None:
        log.error("another desk worker holds the flock — refusing to run a second book")
        return 2

    seed_history = load_seed_history()

    try:
        desk = build_desk(args, seed_history)
    except Exception:
        log.exception("desk build failed")
        return 1
    if desk is None:
        # the gate working: zero validated strategies means an empty roster
        # means nothing trades. Clean exit, not a crash — there is no book
        # to supervise, and a restart loop against this exit code costs the
        # operator nothing but a log line.
        print("STATUS " + json.dumps({"roster": "empty", "detail": "no strategy version in state paper — the engine is ready and empty"}), flush=True)
        return 0

    for spec in desk.specs:
        rows = len(desk.frames[spec.bot])
        log.info(
            "seeded %s %s %s: %d bars of warm-up history",
            spec.bot, spec.symbol, spec.timeframe, rows,
        )

    desk.rearm_open_positions()

    # Shutdown ownership: the nautilus kernel installs asyncio loop signal
    # handlers that swallow SIGINT/SIGTERM into a loop-thread callback whose
    # stop() never progresses (measured 2026-11-25/26: process keeps
    # consuming quotes minutes after the signal, no shutdown log, SIGKILL
    # the only exit). `node.stop()` from the MAIN thread completes cleanly
    # (same probe: node thread dead in seconds). The runner therefore
    # replaces the kernel's handlers — Python allows exactly one per
    # signal — with its own: set an event, let the monitor loop initiate
    # the stop. This is the only shutdown path the desk supervises; systemd
    # SIGTERM lands the same way.
    shutdown = threading.Event()

    def _request_shutdown(signum, frame):
        shutdown.set()

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    started = time.monotonic()
    t = threading.Thread(target=desk.node.run, daemon=True, name="desk-node")
    t.start()
    log.info(
        "node running: %s on the live binance tape",
        ", ".join(f"{s.bot} {s.symbol} {s.timeframe}" for s in desk.specs),
    )
    write_heartbeats(desk, running=True)  # light the lamp at boot, not first cadence
    write_rail_snapshots(desk)
    # monitor: STATUS evidence every 60s; the short join tick keeps SIGTERM
    # latency at seconds — a 60s join would make every shutdown wait out the
    # current tick (measured: 52s from signal to stop with join(60))
    last_status = time.monotonic()
    watchdog_restart = False
    while t.is_alive() and not shutdown.is_set():
        t.join(timeout=10)
        if not t.is_alive() or shutdown.is_set():
            break
        verdict = feed_watchdog_verdict(desk, started)
        if verdict is not None:
            # the subscription-death shape: quotes flowing, bars silent past
            # every honest excuse. The remediation is a fresh process — the
            # vendor client offers no resubscribe API that survives its own
            # failure shape, and kernel surgery on live connection state is
            # how desks die twice. Exit 3 tells the supervisor why.
            log.error(
                "feed watchdog: %s bars silent %.0fs while quotes flowed %.0fs ago "
                "— subscription death shape, restarting the process",
                verdict["bot"], verdict["bars_silent_s"], verdict["last_quote_s"],
            )
            watchdog_restart = True
            shutdown.set()
            break
        if time.monotonic() - last_status >= 60:
            last_status = time.monotonic()
            print(status_line(desk, started), flush=True)
            write_heartbeats(desk, running=True)
            write_rail_snapshots(desk)
    # any node-thread death the runner did not request is abnormal: a fatal
    # error inside the kernel, or an internal shutdown nothing ordered —
    # either way the desk is no longer trading and the supervisor must know
    node_died_unexpectedly = not t.is_alive() and not shutdown.is_set()

    if watchdog_restart:
        log.error("watchdog-ordered shutdown — stopping the node for a supervised restart")
    elif shutdown.is_set():
        log.info("shutdown requested — stopping the node")
    else:
        log.error("node thread ended without a shutdown request")

    try:
        desk.node.stop()
    except Exception:
        log.exception("node stop raised")
    t.join(timeout=60)
    print(status_line(desk, started), flush=True)
    write_heartbeats(desk, running=False)
    if t.is_alive():
        log.error("node thread survived stop() by 60s — exiting anyway, kernel threads are daemons")
    if watchdog_restart:
        # distinct from 0 (clean) and 1 (fatal): the desk was not broken,
        # its feed was — a supervisor keyed on non-zero exits restarts it,
        # and the exit code itself is the incident tape
        return 3
    if node_died_unexpectedly:
        log.error("node thread died without external shutdown — fatal")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
