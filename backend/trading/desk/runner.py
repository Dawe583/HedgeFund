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

BOT_REGISTRY = {
    "scalp": "trading.bots.scalp_bot:ScalpTrend",
    "hft": "trading.bots.hft_bot:HFTMomentum",
    "breakout": "trading.bots.breakout_bot:BreakoutVol",
    "meanrev": "trading.bots.meanrev_bot:MeanRev",
}


def _resolve_bot(name: str):
    import importlib

    path = BOT_REGISTRY[name]
    module_name, cls_name = path.split(":")
    return getattr(importlib.import_module(module_name), cls_name)


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
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--timeframe", default="4h", choices=sorted(TIMEFRAME_NS))
    p.add_argument("--bot", default="scalp", choices=sorted(BOT_REGISTRY))
    p.add_argument(
        "--stale-after",
        type=float,
        default=None,
        help="feed staleness timeout in seconds (default 1.5x the bar interval, floor 120s)",
    )
    return p.parse_args(argv)


def build_desk(args, seed_history):
    from trading.desk.live import build_production_desk
    from trading.desk.node import DeskSpec

    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_schema(engine)
    session_factory = make_session_factory(engine)

    interval_s = TIMEFRAME_NS[args.timeframe] / 1e9
    stale_after = args.stale_after if args.stale_after is not None else max(120.0, 1.5 * interval_s)

    spec = DeskSpec(
        bot=args.bot,
        symbol=args.symbol,
        timeframe=args.timeframe,
        strategy_cls=_resolve_bot(args.bot),
    )
    return build_production_desk(
        specs=[spec],
        session_factory=session_factory,
        seed_history=seed_history,
        feed_stale_after_s=stale_after,
    )


def status_line(desk, started_monotonic: float) -> str:
    """One JSON object with the desk's operational facts — the evidence
    surface for smoke runs and the soak."""
    out = {"uptime_s": round(time.monotonic() - started_monotonic, 1), "bots": {}}
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
    except Exception:
        session.rollback()
        log.exception("heartbeat write failed — engine lamp will read offline")
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
    log.info("node running: %s %s %s on the live binance tape", args.bot, args.symbol, args.timeframe)
    write_heartbeats(desk, running=True)  # light the lamp at boot, not first cadence
    # monitor: STATUS evidence every 60s; the short join tick keeps SIGTERM
    # latency at seconds — a 60s join would make every shutdown wait out the
    # current tick (measured: 52s from signal to stop with join(60))
    last_status = time.monotonic()
    while t.is_alive() and not shutdown.is_set():
        t.join(timeout=10)
        if t.is_alive() and not shutdown.is_set() and time.monotonic() - last_status >= 60:
            last_status = time.monotonic()
            print(status_line(desk, started), flush=True)
            write_heartbeats(desk, running=True)
    # any node-thread death the runner did not request is abnormal: a fatal
    # error inside the kernel, or an internal shutdown nothing ordered —
    # either way the desk is no longer trading and the supervisor must know
    node_died_unexpectedly = not t.is_alive() and not shutdown.is_set()

    if shutdown.is_set():
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
    if node_died_unexpectedly:
        log.error("node thread died without external shutdown — fatal")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
