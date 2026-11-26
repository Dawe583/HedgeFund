"""Slice-5 divergence budget tests — the measurement machinery, the budget
declaration flow, and the API surface.

Measured against the same replay harness the desk tests use: the money test
here is that a parity-clean replay produces zero-or-sub-tick drift evidence
on every fill, because the sandbox IS the backtest matching engine — nonzero
readings on this tape would be the measurement lying, not divergence.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import time

import pytest
import sqlalchemy as sa

from tests_trading.test_desk import (
    AlwaysLong,
    _candles_from_df,
    _ohlcv,
    _run_node,
    _stop_node,
    _wait_for,
)
from trading.backtest.engine import BTConfig
from trading.desk.node import DeskNode, DeskSpec
from trading.desk.replay import ReplayFeeder
from trading.divergence import (
    DivergenceBudget,
    budget_breaches,
    compare_distributions,
    dev_ticks,
    reference_price,
)
from trading.kernel import build_bars
from trading.models import (
    OpenPosition,
    RiskEvent,
    Trade,
    init_schema,
    make_engine,
    make_session_factory,
)


@pytest.fixture()
def session_factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/desk.db")
    init_schema(engine)
    return make_session_factory(engine)


# ---------------------------------------------------------------- pure logic

def test_reference_price_is_role_dependent():
    # market roles reference the filling bar's close — fill-at-close parity
    assert reference_price("entry", 100.0, 90.0, 110.0) == 100.0
    assert reference_price("timeout", 100.0, 90.0, 110.0) == 100.0
    assert reference_price("signal_exit", 100.0, 90.0, 110.0) == 100.0
    # protective roles reference their own level, or the protective distance
    # would dominate the measurement and every stop would read as "drift"
    assert reference_price("stop", 100.0, 90.0, 110.0) == 90.0
    assert reference_price("take_profit", 100.0, 90.0, 110.0) == 110.0


def test_dev_ticks_signed_and_tick_scaled():
    assert dev_ticks(101.0, 100.0, 0.5) == pytest.approx(2.0)
    assert dev_ticks(99.0, 100.0, 0.5) == pytest.approx(-2.0)
    # degenerate inputs are no measurement, never a crash or an infinity
    assert dev_ticks(101.0, 100.0, 0.0) == 0.0
    assert dev_ticks(101.0, 0.0, 0.5) == 0.0


def test_budget_breaches_per_dimension():
    budget = DivergenceBudget(dev_ticks=2.0, entry_lag_bars=0, missed_bars=0)
    assert budget_breaches(budget, dev=1.9, lag_bars=0) == []
    assert budget_breaches(budget, dev=2.1, lag_bars=0) == ["dev_ticks"]
    assert budget_breaches(budget, dev=-2.1, lag_bars=0) == ["dev_ticks"]
    assert budget_breaches(budget, dev=0.0, lag_bars=1) == ["entry_lag_bars"]
    assert budget_breaches(budget, dev=2.1, lag_bars=1) == ["dev_ticks", "entry_lag_bars"]
    # None means unmeasured, and unmeasured is never a breach
    assert budget_breaches(budget, dev=None, lag_bars=None) == []


def test_distribution_comparison_gates_on_volume():
    rng = [float(i) for i in range(40)]
    # both sides at 30+ → a descriptive comparison exists
    out = compare_distributions(rng, rng)
    assert out is not None
    assert out["bt_trades"] == 40
    assert out["paper_mean_within_bt_p5_p95"] is True
    # either side short → None, the honest insufficient-data answer
    assert compare_distributions(rng[:29], rng) is None
    assert compare_distributions(rng, rng[:29]) is None
    assert compare_distributions([], []) is None


def test_distribution_flags_outlier_paper_mean():
    bt = [float(i % 7) - 3.0 for i in range(35)]
    paper_in = list(bt)
    paper_out = [100.0] * 35
    assert compare_distributions(bt, paper_in)["paper_mean_within_bt_p5_p95"] is True
    assert compare_distributions(bt, paper_out)["paper_mean_within_bt_p5_p95"] is False


# ------------------------------------------------------- declaration plumbing

def test_register_version_declares_budget(session_factory):
    """The budget rides the version row — columns, not constructor params —
    and the roster resolves it into what the desk boots."""
    from tests_trading.test_desk import AlwaysLong as AL
    from trading.registry import register_version, roster, validate_and_promote

    sf = session_factory
    with sf() as s:
        budget = DivergenceBudget(dev_ticks=3.0, entry_lag_bars=1, missed_bars=2)
        v = register_version(
            s, "scalp", "Scalp Trend", AL,
            timeframe="4h", universe=["BTCUSDT"], params={"signal_at": 150},
            budget=budget,
        )
        assert v.budget_dev_ticks == 3.0
        assert v.budget_entry_lag_bars == 1
        assert v.budget_missed_bars == 2
        # undeclared budgets stay null — never retroactively invented
        v2 = register_version(
            s, "scalp", "Scalp Trend", AL,
            timeframe="4h", universe=["BTCUSDT"], params={"signal_at": 151},
        )
        assert v2.budget_dev_ticks is None
        s.commit()


def test_roster_resolves_defaults_for_undeclared(session_factory):
    """A version that never declared a budget measures against the paper
    engine's zero-drift defaults — honestly reported as defaults."""
    from tests_trading.test_desk import AlwaysLong as AL
    from trading.divergence import DISTRIBUTION_MIN_TRADES  # noqa: F401  (the bar's name belongs beside the test)
    from trading.registry import register_version, roster
    from trading.models import StrategyState

    sf = session_factory
    with sf() as s:
        v = register_version(
            s, "scalp", "Scalp Trend", AL,
            timeframe="4h", universe=["BTCUSDT"], params={"signal_at": 150},
        )
        s.commit()
        # force the lifecycle to paper without the validation ceremony —
        # the roster read is what's under test, not the gate
        s.add(StrategyState(version_id=v.id, state="validated", note="test"))
        s.add(StrategyState(version_id=v.id, state="paper", note="test"))
        s.commit()
        entries = roster(s)
    assert len(entries) == 1
    budget = entries[0]["budget"]
    assert budget.dev_ticks == DivergenceBudget().dev_ticks
    assert budget.entry_lag_bars == 0
    assert budget.missed_bars == 0


# ------------------------------------------------------------ measurement

def test_replay_fills_carry_zero_drift_evidence(session_factory):
    """The measurement money test: a paced replay IS the backtest tape, so
    every fill must measure inside the quantization noise — entry deviation
    sub-tick, entry lag exactly zero. Nonzero readings on this tape are the
    measurement lying, and this test is the lie detector."""
    raw = _ohlcv(n=700)
    spec = DeskSpec(
        bot="scalp",
        symbol="BTCUSDT",
        timeframe="4h",
        strategy_cls=AlwaysLong,
        bt_config=BTConfig(max_bars_in_trade=30),
    )
    desk = DeskNode(specs=[spec], session_factory=session_factory, seed_history=lambda s, t: [])
    desk.build()

    instrument = desk.instruments["scalp"]
    bars = build_bars(raw, instrument, "4h")
    feeder = ReplayFeeder(
        bars=bars,
        instrument=instrument,
        interval_ms=5,
        quiescence=lambda: (
            desk._strategy_for("scalp")._k + 1 >= feeder.emitted
            and desk.states["scalp"].order_chain_drained()
        ),
    )

    _run_node(desk, feeder)
    try:
        _wait_for(lambda: len(desk.states["scalp"].positions) > 0 or feeder.emitted >= len(bars), timeout=30, what="first closed position")
        deadline = time.time() + 5
        while time.time() < deadline:
            s = session_factory()
            try:
                done = s.execute(sa.select(Trade)).scalars().all()
            finally:
                s.close()
            if done:
                break
            time.sleep(0.1)
    finally:
        _stop_node(desk)

    s = session_factory()
    try:
        closed = s.execute(sa.select(Trade)).scalars().all()
        open_rows = s.execute(sa.select(OpenPosition)).scalars().all()
    finally:
        s.close()

    assert closed or open_rows, "no provenance rows at all — the desk never traded"
    for t in closed:
        assert t.entry_dev_ticks is not None, "entry fill went unmeasured on a tape where the bar exists"
        assert abs(t.entry_dev_ticks) <= 1.0, (
            f"entry deviation {t.entry_dev_ticks} ticks on the parity tape — the measurement or the engine is lying"
        )
        assert t.entry_lag_bars == 0, f"entry lag {t.entry_lag_bars} on a paced replay — the divergence class is back"
        assert t.exit_dev_ticks is not None
    for row in open_rows:
        assert row.entry_dev_ticks is not None
        assert row.entry_lag_bars == 0
        assert row.entry_ref_price is not None and row.entry_ref_price > 0


def test_breach_writes_risk_event(session_factory):
    """A fill whose measured drift exceeds the declared budget surfaces as a
    risk_events row — visible, never silent. Exercised through _measure_fill
    directly with a synthetic fill: a late fill cannot be synthesized on the
    paced replay (the pacing exists precisely to prevent it), so the unit
    seam is the measurement function itself."""
    raw = _ohlcv(n=700)
    spec = DeskSpec(
        bot="scalp",
        symbol="BTCUSDT",
        timeframe="4h",
        strategy_cls=AlwaysLong,
        bt_config=BTConfig(max_bars_in_trade=30),
        budget=DivergenceBudget(dev_ticks=0.1, entry_lag_bars=0, missed_bars=0),
    )
    desk = DeskNode(specs=[spec], session_factory=session_factory, seed_history=lambda s, t: _candles_from_df(raw))
    desk.build()

    # a frame row exists for every raw bar; synthesize a fill priced 5 ticks
    # off the close of bar 200 — the budget is 0.1, so this must breach
    frame = desk.frames["scalp"].frame()
    bar_ts = frame.index[200]
    interval_ns = 14_400_000_000_000
    close_ns = int(bar_ts.value) + interval_ns
    bar_close = float(frame.iloc[200]["close"])
    fill = {
        "role": "entry",
        "price": bar_close + 5 * 0.1,  # 5 ticks at the sim instrument's 0.1
        "ts_event": close_ns,
        "qty": 0.01,
    }
    pos = {"side": "long", "qty": 0.01, "stop_loss": bar_close * 0.9, "take_profit": bar_close * 1.1, "signal_bar": 199, "confidence": 0.9}

    # the measurement needs the instrument in the node cache — present from
    # build(). node itself is never run: the cache read is synchronous.
    out = desk._measure_fill(spec, pos, fill, "entry")
    assert out["entry_dev_ticks"] == pytest.approx(5.0, abs=0.5)
    assert out["entry_lag_bars"] == 0  # filled in the bar right after the signal

    s = session_factory()
    try:
        events = s.execute(
            sa.select(RiskEvent).where(RiskEvent.rail == "divergence_budget")
        ).scalars().all()
    finally:
        s.close()
    assert len(events) == 1
    inputs = json.loads(events[0].inputs_json)
    assert "dev_ticks" in inputs["dimensions"]
    assert events[0].decision == "breached"
    assert events[0].bot == "scalp"

    # a late fill — one bar past the contract — breaches the lag budget too
    late_fill = dict(fill, price=bar_close, ts_event=close_ns + interval_ns)
    out = desk._measure_fill(spec, pos, late_fill, "entry")
    assert out["entry_lag_bars"] == 1
    s = session_factory()
    try:
        events = s.execute(
            sa.select(RiskEvent).where(RiskEvent.rail == "divergence_budget")
        ).scalars().all()
    finally:
        s.close()
    assert len(events) == 2
    lag_inputs = json.loads(events[1].inputs_json)
    assert "entry_lag_bars" in lag_inputs["dimensions"]


def test_protective_fill_references_order_level(session_factory):
    """A stop fill AT the stop price measures zero deviation even though the
    bar close is far away — the protective distance is design, not drift.
    A gap-through fill measures the slippage, honestly signed adverse."""
    raw = _ohlcv(n=700)
    spec = DeskSpec(
        bot="scalp",
        symbol="BTCUSDT",
        timeframe="4h",
        strategy_cls=AlwaysLong,
        bt_config=BTConfig(max_bars_in_trade=30),
    )
    desk = DeskNode(specs=[spec], session_factory=session_factory, seed_history=lambda s, t: _candles_from_df(raw))
    desk.build()

    frame = desk.frames["scalp"].frame()
    bar_ts = frame.index[300]
    interval_ns = 14_400_000_000_000
    close_ns = int(bar_ts.value) + interval_ns
    bar_close = float(frame.iloc[300]["close"])
    stop = bar_close * 0.97
    pos = {"side": "long", "qty": 0.01, "stop_loss": stop, "take_profit": bar_close * 1.1, "signal_bar": 199, "confidence": 0.9}

    # exact stop fill: zero deviation even though close is 3% away
    fill = {"role": "stop", "price": stop, "ts_event": close_ns, "qty": 0.01}
    out = desk._measure_fill(spec, pos, fill, "exit")
    assert out["exit_dev_ticks"] == pytest.approx(0.0, abs=0.5)
    assert out["exit_ref_price"] == stop

    # gapped-through fill below the stop: adverse, negative for a long exit
    fill = {"role": "stop", "price": stop - 1.0, "ts_event": close_ns, "qty": 0.01}
    out = desk._measure_fill(spec, pos, fill, "exit")
    assert out["exit_dev_ticks"] == pytest.approx(-10.0, abs=0.5)


# ------------------------------------------------------------------ API surface

def test_divergence_endpoint_honest_empty(tmp_path):
    """No engine ever ran: empty bots, empty breach events — the first-class
    answer, never a 500."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers.trading import get_trading_db, router

    engine = make_engine(f"sqlite:///{tmp_path}/t.db")
    init_schema(engine)
    sf = make_session_factory(engine)

    def override():
        db = sf()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_trading_db] = override
    c = TestClient(app)
    res = c.get("/api/trading/divergence")
    assert res.status_code == 200
    body = res.json()
    assert body == {"bots": [], "breach_events": []}

    # rails endpoint carries today's vetoes, empty on a virgin database
    res = c.get("/api/trading/rails")
    assert res.status_code == 200
    assert res.json()["vetoes_today"] == []
    app.dependency_overrides.clear()
    engine.dispose()


def test_divergence_endpoint_aggregates_and_reports_insufficient_distribution(tmp_path):
    """Trades with measured drift aggregate per bot; the distributional
    comparison reports its insufficiency with the reason, never fake stats."""
    import datetime as dt

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers.trading import get_trading_db, router

    engine = make_engine(f"sqlite:///{tmp_path}/t.db")
    init_schema(engine)
    sf = make_session_factory(engine)

    with sf() as s:
        now = dt.datetime.now(dt.UTC)
        for i in range(3):
            s.add(
                Trade(
                    bot="scalp", symbol="BTCUSDT", side="long", qty=0.1,
                    entry_price=100.0, exit_price=101.0,
                    entry_time=now, exit_time=now,
                    pnl=5.0 + i, fees=0.5, confidence=0.5, mode="paper",
                    gate_source="kernel",
                    entry_dev_ticks=0.2 * i, exit_dev_ticks=-0.1, entry_lag_bars=0,
                )
            )
        s.commit()

    def override():
        db = sf()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_trading_db] = override
    c = TestClient(app)
    res = c.get("/api/trading/divergence")
    assert res.status_code == 200
    body = res.json()
    assert len(body["bots"]) == 1
    bot = body["bots"][0]
    assert bot["bot"] == "scalp"
    assert bot["fills"]["measured_fills"] == 6  # entry+exit per trade
    assert bot["fills"]["max_abs_dev_ticks"] == pytest.approx(0.4)
    assert bot["distribution"] is None
    assert "not registry-booted" in bot["distribution_note"]
    # no snapshots exist — budget keys are null, never invented defaults
    assert bot["budget_dev_ticks"] is None
    assert bot["missed_bars"] is None
    app.dependency_overrides.clear()
    engine.dispose()


def test_vetoes_today_reads_risk_events(tmp_path):
    """Today's veto rows land in the rails payload; yesterday's do not."""
    import datetime as dt

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers.trading import get_trading_db, router

    engine = make_engine(f"sqlite:///{tmp_path}/t.db")
    init_schema(engine)
    sf = make_session_factory(engine)

    now = dt.datetime.now(dt.UTC)
    yesterday = now - dt.timedelta(days=1)
    with sf() as s:
        s.add(RiskEvent(bot="scalp", symbol="BTCUSDT", rail="symbol_exposure_cap", decision="veto",
                        inputs_json='{"notional": 1200}', tape_ts=1.0, created_at=now))
        s.add(RiskEvent(bot="scalp", symbol="BTCUSDT", rail="symbol_exposure_cap", decision="veto",
                        inputs_json='{"notional": 900}', tape_ts=1.0, created_at=yesterday))
        s.add(RiskEvent(bot="scalp", symbol="BTCUSDT", rail="killswitch_drawdown", decision="tripped",
                        inputs_json="{}", tape_ts=1.0, created_at=now))
        s.commit()

    def override():
        db = sf()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_trading_db] = override
    c = TestClient(app)
    res = c.get("/api/trading/rails")
    assert res.status_code == 200
    vetoes = res.json()["vetoes_today"]
    assert len(vetoes) == 1, "only today's veto, never yesterday's, never non-veto decisions"
    assert vetoes[0]["rail"] == "symbol_exposure_cap"
    assert vetoes[0]["inputs"]["notional"] == 1200
    app.dependency_overrides.clear()
    engine.dispose()
