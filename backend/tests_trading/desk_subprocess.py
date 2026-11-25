"""Subprocess runner for restart tests — one desk process per lifetime, the
way production runs.

The kernel's live node is architecturally one-per-process: clock and
component registries are process-global, and two sequential TradingNodes in
one interpreter share leftover state that intermittently blocks the second
node's startup or drops bars mid-run (measured 2026-11-25: in-process phase-2
stalls at emitted=0 in the majority of loaded runs; subprocess phase-2 is
deterministic across repeated iterations). A restart test that runs both
lifetimes in one process therefore measures an off-label configuration —
production restarts are new processes, so the test spawns them.

Protocol: each invocation prints one JSON line to stdout with the run's
facts; the parent test reads rows from the shared SQLite file for the DB-side
truth and the JSON for the in-memory side.
"""

from __future__ import annotations

import json
import sys
import threading
import time

import sqlalchemy as sa

# the runner is exec'd with cwd=backend — tests_trading is importable only
# through the package path
from tests_trading.test_desk import _candles_from_df, _ohlcv, Signal
from trading.backtest.engine import BTConfig
from trading.kernel import build_bars
from trading.models import (
    OpenPosition,
    init_schema,
    make_engine,
    make_session_factory,
)
from trading.desk.node import DeskNode, DeskSpec
from trading.desk.replay import ReplayFeeder


class WideLong:
    """One long at bar 150, protective levels wide enough that the tape never
    hits them — every close comes from the timeout logic."""

    def signal(self, i, df):
        if len(df) - 1 == 150:
            return Signal(side="long", confidence=0.9, stop_atr=50.0, tp_rr=20.0)
        return None


def _make_spec():
    return DeskSpec(
        bot="t1",
        symbol="BTCUSDT",
        timeframe="4h",
        strategy_cls=WideLong,
        bt_config=BTConfig(max_bars_in_trade=60),
    )


def phase1(db_path: str) -> None:
    """Fresh desk, feed bars[:190] — the position opens and stays open past
    the segment end (timeout close lands ~211)."""
    raw = _ohlcv(n=700)
    engine = make_engine(f"sqlite:///{db_path}")
    init_schema(engine)
    session_factory = make_session_factory(engine)
    spec = _make_spec()
    desk = DeskNode(specs=[spec], session_factory=session_factory, seed_history=lambda s, t: [])
    desk.build()
    instrument = desk.instruments["t1"]
    bars = build_bars(raw, instrument, "4h")
    feeder = ReplayFeeder(
        bars=bars[:190],
        instrument=instrument,
        interval_ms=5,
        quiescence=lambda: (desk._strategy_for("t1")._k + 1 >= feeder.emitted and desk.states["t1"].order_chain_drained()),
    )
    t = threading.Thread(target=desk.node.run, daemon=True)
    desk.node.trader.add_actor(feeder)
    t.start()
    row = None
    deadline = time.time() + 30
    while time.time() < deadline:
        s = session_factory()
        try:
            row = s.execute(sa.select(OpenPosition).where(OpenPosition.bot == "t1")).scalar_one_or_none()
        finally:
            s.close()
        if row is not None and feeder.emitted >= 190:
            break
        time.sleep(0.2)
    out = {
        "emitted": feeder.emitted,
        "open_row": None
        if row is None
        else {
            "entry_price": row.entry_price,
            "stop_loss": row.stop_loss,
            "take_profit": row.take_profit,
            "signal_time": row.signal_time.isoformat() if row.signal_time else None,
        },
    }
    print("RESULT " + json.dumps(out), flush=True)
    try:
        desk.node.stop()
    except Exception:
        pass


def phase2(db_path: str, seed_depth: int) -> None:
    """Restarted desk against the same DB. seed_depth controls how much
    history the new process sees: 190 seeds everything the first process saw
    (the recoverable path); shallow seeds can drop the signal bar, which must
    produce the unrecoverable close."""
    raw = _ohlcv(n=700)
    candles = _candles_from_df(raw)
    engine = make_engine(f"sqlite:///{db_path}")
    init_schema(engine)
    session_factory = make_session_factory(engine)
    spec = _make_spec()
    seed = candles[170:190] if seed_depth < 0 else candles[:seed_depth]
    desk = DeskNode(specs=[spec], session_factory=session_factory, seed_history=lambda s, t: seed)
    desk.build()
    desk.rearm_open_positions()
    instrument = desk.instruments["t1"]
    bars = build_bars(raw, instrument, "4h")
    feeder = ReplayFeeder(
        bars=bars[190:400],
        instrument=instrument,
        interval_ms=5,
        quiescence=lambda: (desk._strategy_for("t1")._k + 1 >= feeder.emitted and desk.states["t1"].order_chain_drained()),
    )
    t = threading.Thread(target=desk.node.run, daemon=True)
    desk.node.trader.add_actor(feeder)
    t.start()
    deadline = time.time() + 30
    while time.time() < deadline:
        if feeder.emitted >= 210:
            break
        time.sleep(0.2)
    time.sleep(2)
    strat = desk._strategy_for("t1")
    state = desk.states["t1"]
    open_pos = strat._open_pos
    out = {
        "emitted": feeder.emitted,
        "fills": [(f["role"], f["price"]) for f in state.fills],
        "positions": [
            {
                "closed": bool(p.get("closed")),
                "rearmed": bool(p.get("rearmed")),
                "signal_bar": p.get("signal_bar"),
                "stop_loss": p.get("stop_loss"),
                "take_profit": p.get("take_profit"),
                "entry_price": (p.get("entry_fill") or {}).get("price"),
                "exit_role": (p.get("exit_fill") or {}).get("role"),
            }
            for p in state.positions
        ],
        "open_pos": None
        if open_pos is None
        else {
            "rearmed": bool(open_pos.get("rearmed")),
            "signal_bar": open_pos.get("signal_bar"),
            "stop_loss": open_pos.get("stop_loss"),
            "take_profit": open_pos.get("take_profit"),
            "pending": bool(open_pos.get("pending", True)),
        },
    }
    print("RESULT " + json.dumps(out), flush=True)
    try:
        desk.node.stop()
    except Exception:
        pass


def parity(db_path: str) -> None:
    """Full tape, ScalpTrend, quiescence-paced — the live half of the parity
    contract. Runs in its own process for the same reason the restart phases
    do: a BacktestEngine never registers here, the node boots clean, and the
    measured path is the unmodified kernel."""
    from trading.bots.scalp_bot import ScalpTrend

    raw = _ohlcv(n=700)
    engine = make_engine(f"sqlite:///{db_path}")
    init_schema(engine)
    session_factory = make_session_factory(engine)
    cfg = BTConfig(max_bars_in_trade=30)
    spec = DeskSpec(bot="scalp", symbol="BTCUSDT", timeframe="4h", strategy_cls=ScalpTrend, bt_config=cfg)
    desk = DeskNode(specs=[spec], session_factory=session_factory, seed_history=lambda s, t: [])
    desk.build()
    instrument = desk.instruments["scalp"]
    bars = build_bars(raw, instrument, "4h")
    feeder = ReplayFeeder(
        bars=bars,
        instrument=instrument,
        interval_ms=5,
        quiescence=lambda: (desk._strategy_for("scalp")._k + 1 >= feeder.emitted and desk.states["scalp"].order_chain_drained()),
    )
    t = threading.Thread(target=desk.node.run, daemon=True)
    desk.node.trader.add_actor(feeder)
    t.start()
    deadline = time.time() + 40
    while time.time() < deadline:
        # emission of the last bar proves only the second-to-last bar was
        # processed — the pacing contract emits bar k once bar k-1 completed.
        # The result snapshot is meaningful only when the final bar's own
        # on_bar has run and every command it may have submitted is
        # adjudicated, which is what the drain waits on directly.
        if (
            feeder.emitted >= len(bars)
            and desk._strategy_for("scalp")._k + 1 >= len(bars)
            and desk.states["scalp"].order_chain_drained()
        ):
            break
        time.sleep(0.2)
    state = desk.states["scalp"]
    time.sleep(2)
    out = {
        "emitted": feeder.emitted,
        "positions": [
            {
                "closed": bool(p.get("closed")),
                "side": p.get("side"),
                "entry_price_net": p.get("entry_price_net"),
                "exit_price_net": p.get("exit_price_net"),
                "pnl": p.get("pnl"),
            }
            for p in state.positions
        ],
    }
    print("RESULT " + json.dumps(out), flush=True)
    try:
        desk.node.stop()
    except Exception:
        pass


if __name__ == "__main__":
    mode, db_path = sys.argv[1], sys.argv[2]
    if mode == "phase1":
        phase1(db_path)
    elif mode == "phase2":
        phase2(db_path, int(sys.argv[3]))
    elif mode == "parity":
        parity(db_path)
    else:
        raise SystemExit(f"unknown mode {mode}")
