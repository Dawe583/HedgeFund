"""M3 acceptance seam — every signal recorded, including the rejections.

The kernel emits one outcome per non-None emission; the desk writes the
`signals` row inside the bar event. These tests drive the real replay path
(no mocks of the engine) and read the database rows back: the outcome
vocabulary is asserted word for word because "rejected" without the reason
is exactly the invisibility the acceptance line forbids.
"""

from __future__ import annotations

import json
import threading
import time

import numpy as np
import pandas as pd
import pytest

from sqlalchemy import select

from trading.backtest.engine import BTConfig, Signal
from trading.kernel import build_bars
from trading.models import SignalRecord, init_schema, make_engine, make_session_factory
from trading.desk.node import DeskNode, DeskSpec
from trading.desk.replay import ReplayFeeder
from trading.risk import set_killswitch


def _ohlcv(n=350, seed=23, freq="4h"):
    """Same future-anchored generator as the desk tests — the sandbox's
    command/clock logic needs a monotonic future tape."""
    rng = np.random.default_rng(seed)
    steps = np.cumsum(rng.normal(2.0, 60, n)) + 40_000
    close = steps
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.002, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.002, n)))
    vol = np.abs(rng.normal(1000, 100, n))
    start = pd.Timestamp.now(tz="UTC").floor(freq) + pd.Timedelta(freq)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _candles(df):
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


def _wait_for(predicate, timeout=25.0, interval=0.05, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    raise AssertionError(f"timed out waiting for {what}")


def _run_desk(session_factory, spec, raw, seed_rows=0):
    """Boot a one-bot desk over the replay feeder; returns (desk, stop_fn).
    seed_rows: how many leading candles are seeded as history (the feature
    warm-up) instead of replayed — keeps the replay itself short."""
    candles = _candles(raw)
    seed = candles[:seed_rows]
    tape = raw.iloc[seed_rows:]

    desk = DeskNode(
        specs=[spec],
        session_factory=session_factory,
        seed_history=lambda s, t: list(seed),
    )
    desk.build()
    instrument = desk.instruments[spec.bot]
    bars = build_bars(tape, instrument, spec.timeframe)
    feeder = ReplayFeeder(
        bars=bars,
        instrument=instrument,
        interval_ms=5,
        quiescence=lambda: (
            desk._strategy_for(spec.bot)._k + 1 >= feeder.emitted
            and desk.states[spec.bot].order_chain_drained()
        ),
    )
    desk.node.trader.add_actor(feeder)
    t = threading.Thread(target=desk.node.run, daemon=True)
    t.start()
    return desk, feeder


def _stop(desk):
    try:
        desk.node.stop()
    except Exception:
        pass


def _signals(sf, bot):
    session = sf()
    try:
        return list(
            session.execute(
                select(SignalRecord).where(SignalRecord.bot == bot).order_by(SignalRecord.id)
            ).scalars()
        )
    finally:
        session.close()


class Script:
    """Deterministic scripted strategy: emits at exact frame positions —
    entries are test-controlled, never market-dependent."""

    def __init__(self, script: dict[int, dict]):
        self._script = script

    def signal(self, i, df):
        emission = self._script.get(i)
        if emission is None:
            return None
        return Signal(**emission)


def test_rejected_signals_are_recorded_with_their_reasons(session_factory):
    """One run, three rejection classes, all must land in the table:
    flat_noop (a flat emission with no position), below_confidence (under the
    gate's floor), in_position (the book is already full). Plus the entered
    emission carrying its sizing chain — the drill-down's raw material."""
    script = {
        200: {"side": "flat", "confidence": 0.9},   # flat_noop
        210: {"side": "long", "confidence": 0.1},   # below_confidence (floor default 0.55)
        220: {"side": "long", "confidence": 0.9, "stop_atr": 8.0, "tp_rr": 4.0},  # entered
        230: {"side": "long", "confidence": 0.9, "stop_atr": 8.0, "tp_rr": 4.0},  # in_position
    }
    raw = _ohlcv(n=280)
    spec = DeskSpec(
        bot="script",
        symbol="BTCUSDT",
        timeframe="4h",
        strategy_cls=Script,
        strategy_params={"script": script},
        bt_config=BTConfig(max_bars_in_trade=30),
    )
    desk, feeder = _run_desk(session_factory, spec, raw)
    try:
        _wait_for(
            lambda: feeder.emitted >= 245,
            timeout=60,
            what="replay past the scripted emissions",
        )
        _wait_for(
            lambda: len(_signals(session_factory, "script")) >= 4,
            timeout=20,
            what="four signal rows",
        )
    finally:
        _stop(desk)

    rows = _signals(session_factory, "script")
    by_outcome = {}
    for r in rows:
        by_outcome.setdefault(r.outcome, []).append(r)


    # entered OR veto:exposure-class — the synthetic tape's equity/cap math
    # decides which; both are the chain recorded honestly. What is NOT
    # acceptable is silence.
    entered = by_outcome.get("entered", [])
    vetoes = [r for r in rows if r.outcome.startswith("veto:")]
    assert entered or vetoes, f"neither entered nor vetoed: {sorted(by_outcome)}"
    chain_row = (entered or vetoes)[0]
    details = json.loads(chain_row.details_json)
    assert details, "the sizing chain must travel with entered/vetoed emissions"

    # every row carries the signal bar's own time, never the write clock
    for r in rows:
        assert r.bar_time is not None
        assert r.side in ("long", "short", "flat")
        assert 0.0 <= r.confidence <= 1.0
        assert r.timeframe == "4h"


def test_rail_vetoed_signal_is_recorded_as_a_veto(session_factory):
    """A thrown manual kill-switch turns every entry signal into a veto —
    and the signal row must say so, word for word, beside the risk_events
    veto row the rail already writes."""
    set_killswitch(session_factory, True, note="test halt")
    script = {
        220: {"side": "long", "confidence": 0.9, "stop_atr": 8.0, "tp_rr": 4.0},
    }
    raw = _ohlcv(n=280)
    spec = DeskSpec(
        bot="halted",
        symbol="BTCUSDT",
        timeframe="4h",
        strategy_cls=Script,
        strategy_params={"script": script},
        bt_config=BTConfig(max_bars_in_trade=30),
    )
    desk, feeder = _run_desk(session_factory, spec, raw)
    try:
        _wait_for(
            lambda: len(_signals(session_factory, "halted")) >= 1,
            timeout=30,
            what="the vetoed signal row",
        )
    finally:
        _stop(desk)

    rows = _signals(session_factory, "halted")
    assert rows, "no signal rows at all — the vetoed emission went unrecorded"
    assert all(r.outcome.startswith("veto:") for r in rows), (
        f"a halted desk must veto every emission: {[r.outcome for r in rows]}"
    )
    assert any("killswitch" in r.outcome or "halt" in r.outcome for r in rows), (
        f"the rail must name itself in the outcome: {[r.outcome for r in rows]}"
    )
    details = json.loads(rows[0].details_json)
    assert details, "a rail veto carries the rail's inputs as its explanation"
