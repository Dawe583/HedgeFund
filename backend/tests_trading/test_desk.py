"""M3 slice 1 integration tests — the kernel paper desk against replayed bars.

Nothing here mocks the engine: bars travel the real msgbus path through the
live DataEngine into the same SimulatedExchange the backtest uses, and the
strategies are the same harness-wrapped classes. What the tests control is
only WHERE bars come from — the replay feeder — and when the process dies.

The parity test is the slice's money test: one dataset, one strategy, one
harness — a backtest run and a live-node paper run must produce the same
trades. Divergence classes that legitimately exist (live-clock event
ordering) are documented in docs/design/m3-paper-plan.md; everything else is
a bug.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trading.backtest.engine import BTConfig, Signal
from trading.bots import ScalpTrend
from trading.features import build_features
from trading.kernel import build_bars, run_kernel_backtest
from trading.models import init_schema, make_engine, make_session_factory, OpenPosition, Trade
from trading.desk.frame import IncrementalFrame
from trading.desk.node import DeskNode, DeskSpec
from trading.desk.replay import ReplayFeeder

import sqlalchemy as sa


def _ohlcv(n=700, drift=2.0, seed=11, freq="4h", start=None):
    """Same generator as the kernel tests — OHLC-consistent synthetic series.

    The tape is anchored IN THE FUTURE by default: replay emission compresses
    hours into milliseconds, and the sandbox exchange's inflight/drain logic
    compares command timestamps (wall clock) against bar timestamps — a tape
    ending at 'now' would leave orders stranded behind the final bar. Future-
    anchored bars keep the timeline monotonic and consistent, which is the
    same relationship the backtest has with its data clock. Pass an explicit
    start to reproduce the kernel tests' historical tapes.
    """
    rng = np.random.default_rng(seed)
    steps = np.cumsum(rng.normal(drift, 60, n)) + 40_000
    close = steps
    open_ = np.concatenate([[close[0]], close[:-1]])
    body_hi = np.maximum(open_, close)
    body_lo = np.minimum(open_, close)
    high = body_hi * (1 + np.abs(rng.normal(0, 0.002, n)))
    low = body_lo * (1 - np.abs(rng.normal(0, 0.002, n)))
    vol = np.abs(rng.normal(1000, 100, n))
    if start is None:
        start = pd.Timestamp.now(tz="UTC").floor(freq) + pd.Timedelta(freq)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _candles_from_df(df):
    return [
        {
            "open_time": ts,
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": float(r.volume),
        }
        for ts, r in df.iterrows()
    ]


@pytest.fixture()
def session_factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/desk.db")
    init_schema(engine)
    return make_session_factory(engine)


class AlwaysLong:
    """Deterministic test strategy: long signal at exactly one frame position,
    wide protective levels — entries and timing are test-controlled, never
    market-dependent. Positional indexing, honest by construction."""

    def __init__(self, signal_at=150):
        self._signal_at = signal_at

    def signal(self, i, df):
        if len(df) - 1 == self._signal_at or i == self._signal_at:
            return Signal(side="long", confidence=0.9, stop_atr=8.0, tp_rr=4.0)
        return None


def _wait_for(predicate, timeout=20.0, interval=0.05, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    raise AssertionError(f"timed out waiting for {what}")


def _run_node(node, feeder=None):
    """Start the node's loop on a daemon thread; caller must stop_node it."""
    if feeder is not None:
        node.node.trader.add_actor(feeder)
    t = threading.Thread(target=node.node.run, daemon=True)
    t.start()
    return t


def _stop_node(node):
    try:
        node.node.stop()
    except Exception:
        pass


def test_replay_flows_through_real_engine_into_provenance(session_factory):
    """End-to-end: replayed bars -> harness strategy -> sandbox fills ->
    ledger rows. Asserts the full data path exists, not any particular trade
    outcome — the parity test owns outcome correctness."""
    df = build_features(_ohlcv(n=700))
    spec = DeskSpec(
        bot="scalp",
        symbol="BTCUSDT",
        timeframe="4h",
        strategy_cls=ScalpTrend,
        bt_config=BTConfig(max_bars_in_trade=30),
    )
    desk = DeskNode(specs=[spec], session_factory=session_factory, seed_history=lambda s, t: [])
    desk.build()

    instrument = desk.instruments["scalp"]
    # the replay bars are built from the RAW ohlcv rows, not the feature frame —
    # the feature frame is the strategy's view, bars are the market's truth
    raw = _ohlcv(n=700)
    bars = build_bars(raw, instrument, "4h")
    feeder = ReplayFeeder(bars=bars, instrument=instrument, interval_ms=5, quiescence=lambda: (desk._strategy_for("scalp")._k + 1 >= feeder.emitted and desk.states["scalp"].order_chain_drained()))

    _run_node(desk, feeder)
    try:
        state = desk.states["scalp"]
        _wait_for(lambda: len(state.positions) > 0 or feeder.emitted >= len(bars), timeout=30, what="first closed position")
        # trailing fills settle a beat after the tape ends — give the loop a
        # moment, then judge the path, not the timing
        deadline = time.time() + 5
        while time.time() < deadline and len(state.positions) == 0:
            time.sleep(0.1)
    finally:
        _stop_node(desk)

    assert len(state.fills) > 0, "no fills at all — the data path is broken"
    assert len(state.positions) > 0, "fills happened but no position lifecycle completed"


def test_paper_matches_backtest_on_same_bars(tmp_path):
    """The money test: identical dataset, identical strategy, identical
    harness — the paper node's trade economics must match the backtest's.
    Small-sample exactness is the point: any divergence here is either an
    engine bug or a documented divergence class, never noise.

    The live half runs in its own process: a BacktestEngine and a live
    TradingNode in one interpreter share the kernel's process-global
    registries, an off-label configuration whose interference surfaces as
    dropped bars and mid-run freezes (measured 2026-11-25). The backtest is
    loop-free and never feeds a live node, so it stays in-process."""
    raw = _ohlcv(n=700)
    df = build_features(raw.copy())
    cfg = BTConfig(max_bars_in_trade=30)
    bt = run_kernel_backtest(df.copy(), ScalpTrend(), cfg, "4h")

    db_path = tmp_path / "desk.db"
    live = _run_desk_subprocess("parity", db_path)

    paper_closed = [p for p in live["positions"] if p["closed"]]
    bt_trades = bt.trades

    assert len(paper_closed) == len(bt_trades), (
        f"trade count diverges: paper {len(paper_closed)} vs backtest {len(bt_trades)} — {live['positions']}"
    )
    for i, (pp, bt_t) in enumerate(zip(paper_closed, bt_trades)):
        assert pp["side"] == bt_t["side"], f"trade {i} side diverges"
        assert pp["entry_price_net"] == pytest.approx(bt_t["entry_price"], rel=1e-6), (
            f"trade {i} entry: paper {pp['entry_price_net']} vs backtest {bt_t['entry_price']}"
        )
        assert pp["exit_price_net"] == pytest.approx(bt_t["exit_price"], rel=1e-6), (
            f"trade {i} exit: paper {pp['exit_price_net']} vs backtest {bt_t['exit_price']}"
        )
        # pnl composes two prices that each already passed rel=1e-6, plus
        # fees on both legs — the composed figure's honest floor is the
        # propagation of those tolerances, not a fresh constant: with
        # qty*price ~2000 per leg, 1e-6 per leg admits ~4e-3 absolute drift
        # in the composed pnl, which for a small-pnl trade dominates any
        # relative band. absolute tolerance derived from the leg tolerance,
        # never a number picked to pass.
        assert pp["pnl"] == pytest.approx(
            bt_t["pnl"], abs=pp["qty"] * (pp["entry_price_net"] + pp["exit_price_net"]) * 1e-6
        ), f"trade {i} pnl diverges"


def _run_desk_subprocess(mode: str, db_path, seed_depth: int | None = None, timeout: int = 90) -> dict:
    """Spawn the restart scenario's desk lifetime in its own process.

    The kernel's live node is one-per-process architecture: registries are
    process-global, and two sequential TradingNodes in one interpreter share
    leftover state that intermittently blocks startup or drops bars
    (measured 2026-11-25, in-process phase-2 stall in the majority of loaded
    runs vs 4/4 deterministic subprocess runs). Production restarts are new
    processes — the test therefore measures what production does.
    """
    import json
    import subprocess
    import sys as _sys

    cmd = [_sys.executable, "-m", "tests_trading.desk_subprocess", mode, str(db_path)]
    if seed_depth is not None:
        cmd.append(str(seed_depth))
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    raise AssertionError(
        f"subprocess produced no RESULT (exit {proc.returncode})\nstdout tail: {proc.stdout[-400:]}\nstderr tail: {proc.stderr[-600:]}"
    )


def test_restart_rearms_position_and_preserves_economics(tmp_path):
    """The restart contract: kill the node with a position open, boot a new
    one against the same DB — the position must come back with its ORIGINAL
    entry economics and protective levels, and closing it writes the trade
    the never-restarted run would have written."""
    db_path = tmp_path / "desk.db"
    phase1 = _run_desk_subprocess("phase1", db_path)
    row = phase1["open_row"]
    assert row is not None, "position never opened inside phase 1"
    assert phase1["emitted"] == 190
    original_entry = row["entry_price"]
    original_sl = row["stop_loss"]
    original_tp = row["take_profit"]
    assert row["signal_time"] is not None

    phase2 = _run_desk_subprocess("phase2", db_path, seed_depth=190)
    assert phase2["emitted"] == 210, "second segment never fed completely"

    positions = phase2["positions"]
    closed = [p for p in positions if p["closed"]]
    still_open = phase2["open_pos"]
    assert closed or still_open is not None, "position vanished across the restart"

    if closed:
        trade_pos = closed[0]
        # economics anchor to the ORIGINAL entry, not the rearm print
        assert trade_pos["entry_price"] == pytest.approx(original_entry, rel=1e-9)
        engine = make_engine(f"sqlite:///{db_path}")
        init_schema(engine)
        sf = make_session_factory(engine)
        s = sf()
        try:
            trades = list(s.execute(sa.select(Trade).where(Trade.bot == "t1")).scalars())
        finally:
            s.close()
        assert len(trades) == 1
        # cost curve v1: the entry cost is the filling bar's own range, not
        # the flat rate. WideLong signals at bar 150 so the entry fills at
        # the close of bar 151 — a close-fill, priced by its own bar's range
        # (kernel._bar_slip_bps close-fill rule)
        import trading.kernel as _k
        from trading.costs import bar_slippage_bps
        raw_expected = _ohlcv(n=700)
        expected_row = raw_expected.iloc[151]
        expected_slip = bar_slippage_bps(
            expected_row["high"], expected_row["low"], expected_row["close"],
            BTConfig().slippage_bps,
        ) / 10_000
        assert trades[0].entry_price == pytest.approx(
            original_entry * (1 + expected_slip), rel=1e-6
        )
    else:
        assert still_open["rearmed"] is True
        assert still_open["stop_loss"] == pytest.approx(original_sl, rel=1e-6)
        assert still_open["take_profit"] == pytest.approx(original_tp, rel=1e-6)
        # signal bar re-derived from the frame, not reset to now
        assert still_open["signal_bar"] >= 0


def test_two_symbols_never_share_state(session_factory):
    """Multi-symbol by construction: two bots on different instruments must
    not share frames, positions, or bar counting. NETTING merges per
    instrument — never across instruments."""
    raw_btc = _ohlcv(n=400, seed=11)
    raw_eth = _ohlcv(n=400, seed=77)

    class BarOneFifty:
        def signal(self, i, df):
            if len(df) - 1 == 150:
                return Signal(side="long", confidence=0.9, stop_atr=50.0, tp_rr=20.0)
            return None

    specs = [
        DeskSpec(bot="btc_bot", symbol="BTCUSDT", timeframe="4h", strategy_cls=BarOneFifty, bt_config=BTConfig()),
        DeskSpec(bot="eth_bot", symbol="ETHUSDT", timeframe="4h", strategy_cls=BarOneFifty, bt_config=BTConfig()),
    ]
    desk = DeskNode(specs=specs, session_factory=session_factory, seed_history=lambda s, t: [])
    desk.build()

    feeder_btc = ReplayFeeder(
        bars=build_bars(raw_btc, desk.instruments["btc_bot"], "4h"),
        instrument=desk.instruments["btc_bot"], interval_ms=5, feeder_id="btc-feed",
        quiescence=lambda: (desk._strategy_for("btc_bot")._k + 1 >= feeder_btc.emitted and desk.states["btc_bot"].order_chain_drained()),
    )
    feeder_eth = ReplayFeeder(
        bars=build_bars(raw_eth, desk.instruments["eth_bot"], "4h"),
        instrument=desk.instruments["eth_bot"], interval_ms=5, feeder_id="eth-feed",
        quiescence=lambda: (desk._strategy_for("eth_bot")._k + 1 >= feeder_eth.emitted and desk.states["eth_bot"].order_chain_drained()),
    )
    desk.node.trader.add_actor(feeder_btc)
    desk.node.trader.add_actor(feeder_eth)
    t = threading.Thread(target=desk.node.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: feeder_btc.emitted >= 400 and feeder_eth.emitted >= 400, timeout=40, what="both feeds")
        state_btc = desk.states["btc_bot"]
        state_eth = desk.states["eth_bot"]
        # emission of the last bar only proves the second-to-last bar was
        # processed — the pacing contract emits bar k once bar k-1 completed.
        # The final frame row exists only when the last bar's on_bar has run,
        # which the drain here waits on directly.
        _wait_for(
            lambda: desk._strategy_for("btc_bot")._k + 1 >= 400 and desk._strategy_for("eth_bot")._k + 1 >= 400,
            timeout=20,
            what="final bars processed on both",
        )
        _wait_for(lambda: len(state_btc.fills) > 0 and len(state_eth.fills) > 0, timeout=20, what="fills on both")
    finally:
        _stop_node(desk)

    frame_btc = desk.frames["btc_bot"].frame()
    frame_eth = desk.frames["eth_bot"].frame()
    assert len(frame_btc) == 400 and len(frame_eth) == 400
    # different seeds → different closes; frames must not be the same object nor content
    assert frame_btc is not frame_eth
    assert not frame_btc["close"].equals(frame_eth["close"])


def test_worker_lock_admits_exactly_one_holder(tmp_path):
    """The flock guard is the single-worker contract: the desk must never run
    twice against the same book. Two acquisitions racing for the same lock
    file produce exactly one holder; releasing reopens the race."""
    from trading.desk.worker import acquire_worker_lock

    first = acquire_worker_lock(tmp_path)
    assert first is not None, "first acquisition must succeed on a free lock"
    second = acquire_worker_lock(tmp_path)
    assert second is None, "second acquisition must fail while the first holds"
    first.close()
    third = acquire_worker_lock(tmp_path)
    assert third is not None, "the lock must be acquirable again after release"
    third.close()


def test_feed_health_reports_stale_only_after_silence():
    """The stale-feed predicate measures silence against the wall clock: a
    feed that never beat is stale at birth, a beating feed is fresh, and a
    silent one crosses the threshold when the timeout elapses."""
    from trading.desk.worker import FeedHealth

    now = [1000.0]

    def clock():
        return now[0]

    health = FeedHealth(timeout_s=10.0, clock=clock)
    assert health.stale(), "never-beaten feed is stale by definition"
    health.beat()
    assert not health.stale()
    now[0] += 9.0
    assert not health.stale(), "within the timeout the feed is fresh"
    now[0] += 2.0
    assert health.stale(), "silence past the timeout is a dead venue"
    health.beat()
    assert not health.stale(), "a recovered feed reports fresh again"


def test_restart_with_shallow_history_closes_unrecoverable(tmp_path):
    """The honest fallback: rearm a position whose signal bar the seeded
    history does not reach — the position's age is unknowable, so the kernel
    closes it at market instead of silently resetting its clock. Never a
    phantom position, never a falsified age."""
    db_path = tmp_path / "desk.db"
    phase1 = _run_desk_subprocess("phase1", db_path)
    assert phase1["open_row"] is not None, "position never opened inside phase 1"

    # seed_depth -1 selects the shallow seed (bars 170-190): the signal bar's
    # timestamp cannot be in it, so the position's age is unknowable
    phase2 = _run_desk_subprocess("phase2", db_path, seed_depth=-1)
    positions = phase2["positions"]
    # the rearmed position — and only it — must close as unrecoverable. New
    # entries the dumb positional strategy fires inside phase 2 are its own
    # legitimate behavior, never part of this test's contract.
    rearmed = [p for p in positions if p["rearmed"]]
    assert len(rearmed) == 1, f"expected exactly one rearmed position, got {positions}"
    assert rearmed[0]["closed"] is True
    assert rearmed[0]["exit_role"] == "restart_unrecoverable"

    # the open row is gone — no phantom position survives in the ledger
    engine = make_engine(f"sqlite:///{db_path}")
    init_schema(engine)
    sf = make_session_factory(engine)
    s = sf()
    try:
        remaining = list(s.execute(sa.select(OpenPosition).where(OpenPosition.bot == "t1")).scalars())
    finally:
        s.close()
    assert remaining == []
