"""M3 slice 4 — Layer-0 hard rails in the kernel harness.

Two levels, honestly separated:

1. RailBook unit tests — the state machine's exact arithmetic (risk_guard
   semantics, UTC-day latching, drawdown from peak), fast and deterministic.
2. Kernel integration tests — the wiring: settles feed the rails, tripped
   rails veto entries BEFORE sizing, every firing lands in the evidence
   tapes, and the external halts (manual kill-switch, halt sentinel) are
   fail-closed.

The losing machine: a falling tape plus a long-every-bar strategy with a
tight stop. Sizing makes every stop-out cost exactly leverage ×
risk_per_trade × equity by construction — leverage 5 is 10% of equity per
loss — so three stop-outs draw down ~27%, far past the 12% kill-switch, and
the losses are losses regardless of noise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading.backtest.engine import BTConfig, Signal
from trading.features import build_features
from trading.kernel import run_kernel_backtest
from trading.rails import RailBook


def _falling(n=600, seed=7, freq="min", start="2025-03-10"):
    """A tape that only falls — every long with a tight stop is a guaranteed
    stop-out. OHLC-consistent, anchored mid-week so UTC-day tests control
    their windows."""
    rng = np.random.default_rng(seed)
    close = 40_000 - np.arange(n) * 25.0 + rng.normal(0, 3, n)
    open_ = np.concatenate([[close[0] + 25.0], close[:-1] + 25.0])
    high = np.maximum(open_, close) * 1.0005
    low = np.minimum(open_, close) * 0.9995
    vol = np.abs(rng.normal(1000, 100, n))
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


class LongEveryBar:
    """Long signal on every bar from warmup on, tight stop, far target — the
    harness enters whenever flat, so on a falling tape this is a loss
    machine whose loss size the sizing arithmetic pins exactly."""

    def __init__(self, start=120, stop_atr=0.5):
        self._start = start
        self._stop = stop_atr

    def signal(self, i, df):
        if i >= self._start:
            return Signal(side="long", confidence=0.9, stop_atr=self._stop, tp_rr=10.0)
        return None


def _losing_run(cfg_overrides=None, n=600):
    df = build_features(_falling(n=n))
    kw = dict(
        fee_pct=0.0,
        slippage_bps=0.0,
        confidence_min=0.5,
        leverage=5.0,
        # caps far above the tape's entry notional — tight stops size large,
        # and the rails under test must be the ONLY thing that can veto
        max_symbol_exposure=500.0,
        max_gross_exposure=500.0,
        max_bars_in_trade=300,
    )
    kw.update(cfg_overrides or {})
    cfg = BTConfig(**kw)
    return run_kernel_backtest(df, LongEveryBar(), cfg, "1m")


# ------------------------------------------------------------------ RailBook


def test_cooldown_follows_risk_guard_semantics_exactly():
    """3 consecutive losses → 4h cooldown from the third close; wins reset;
    breakeven counts as a loss — risk_guard.py's arithmetic, in-run state."""
    rb = RailBook(1000.0, killswitch_dd_pct=0.12, daily_loss_pct=0.05)
    t0 = 1_700_000_000.0
    assert rb.entry_verdict(t0, 1000.0) is None
    rb.settle(-1.0, t0, 999.0)
    rb.settle(0.0, t0, 999.0)  # breakeven is a loss
    events = rb.settle(-1.0, t0, 998.0)
    assert len(events) == 1 and events[0]["decision"] == "cooldown_started"
    assert rb.cooldown_until == t0 + 4 * 3600
    assert rb.loss_streak == 0  # the streak zeroes when the cooldown arms
    v = rb.entry_verdict(t0 + 60, 998.0)
    assert v is not None and v["rail"] == "loss_streak_cooldown"
    assert rb.entry_verdict(t0 + 4 * 3600 + 1, 998.0) is None


def test_win_resets_the_streak():
    rb = RailBook(1000.0, killswitch_dd_pct=0.12, daily_loss_pct=0.05)
    t0 = 1_700_000_000.0
    rb.settle(-1.0, t0, 999.0)
    rb.settle(-1.0, t0, 998.0)
    rb.settle(+5.0, t0, 1003.0)
    assert rb.loss_streak == 0
    rb.settle(-1.0, t0, 1002.0)
    assert rb.loss_streak == 1  # one, not three


def test_kill_switch_trips_at_drawdown_from_peak_and_latches():
    rb = RailBook(1000.0, killswitch_dd_pct=0.12, daily_loss_pct=0.05)
    t0 = 1_700_000_000.0
    rb.settle(+200.0, t0, 1200.0)  # peak moves to 1200
    assert rb.peak_equity == 1200.0
    # 12% below the 1200 peak is 1056 — a drop to 1057 must NOT trip
    events = rb.settle(-143.0, t0, 1057.0)
    assert not any(e["rail"] == "kill_switch_drawdown" for e in events)
    events = rb.settle(-2.0, t0, 1055.0)
    trips = [e for e in events if e["rail"] == "kill_switch_drawdown"]
    assert len(trips) == 1 and trips[0]["decision"] == "tripped"
    assert trips[0]["inputs"]["peak_equity"] == pytest.approx(1200.0)
    v = rb.entry_verdict(t0 + 10, 1055.0)
    assert v["rail"] == "kill_switch_drawdown"
    # the latch is one-way: recovery does not reopen entries
    rb.settle(+500.0, t0, 1555.0)
    assert rb.entry_verdict(t0 + 20, 1555.0)["rail"] == "kill_switch_drawdown"


def test_daily_loss_latches_for_the_utc_day_and_rolls():
    rb = RailBook(1000.0, killswitch_dd_pct=0.99, daily_loss_pct=0.05)
    day1 = 1_700_006_400.0  # 2023-11-14T13:20:00Z
    rb.settle(-60.0, day1, 940.0)  # 6% loss in the day
    assert rb.daily_breached is True
    assert rb.entry_verdict(day1 + 60, 940.0)["rail"] == "daily_loss_limit"
    # later wins do not un-forfeit the day
    rb.settle(+100.0, day1 + 120, 1040.0)
    assert rb.entry_verdict(day1 + 130, 1040.0)["rail"] == "daily_loss_limit"
    # the next UTC day rolls the window — entries flow again
    day2 = day1 + 86400
    assert rb.entry_verdict(day2, 1040.0) is None
    assert rb.daily_breached is False
    assert rb.day_start_equity == 1040.0


def test_snapshot_reports_consumed_fractions():
    rb = RailBook(1000.0, killswitch_dd_pct=0.12, daily_loss_pct=0.05)
    t0 = 1_700_000_000.0
    rb.settle(-25.0, t0, 975.0)
    snap = rb.snapshot(t0, 975.0)
    assert snap["daily_loss"] == pytest.approx(25.0)
    assert snap["daily_loss_limit"] == pytest.approx(50.0)
    assert snap["daily_loss_consumed"] == pytest.approx(0.5)
    assert snap["drawdown_pct"] == pytest.approx(0.025)
    assert snap["loss_streak"] == 1


# -------------------------------------------------------- kernel integration


def test_kill_switch_trips_in_kernel_and_vetoes_with_rail_events():
    """The wiring end to end: stop-outs feed realized_net, the drawdown
    trips the kill-switch, later signals are vetoed BEFORE sizing, the trip
    is a rail event with its inputs, and the vetoes carry the rail's name."""
    # daily loss off: the first stop-out already costs 10% of equity, which
    # breaches the 5% daily limit before the kill-switch can trip — correct
    # behavior, and exactly why this test isolates the kill-switch
    res = _losing_run({"daily_loss_pct": 0.99})
    assert len(res.trades) >= 1, "the losing machine must trade before it trips"
    assert all(t["pnl"] < 0 for t in res.trades), "a falling tape with tight stops only loses"

    events = res.metrics["rail_events"]
    trips = [e for e in events if e["rail"] == "kill_switch_drawdown" and e["decision"] == "tripped"]
    assert len(trips) == 1, f"exactly one trip, got {events}"
    inputs = trips[0]["inputs"]
    assert inputs["peak_equity"] > inputs["realized_net"]
    assert inputs["drawdown_pct"] >= inputs["killswitch_dd_pct"]

    vetoes = res.metrics["vetoes"]
    ks_vetoes = [v for v in vetoes if v.get("rail") == "kill_switch_drawdown"]
    assert len(ks_vetoes) >= 1, "entries after the trip must be vetoed, not silently skipped"
    for v in ks_vetoes:
        assert v["reason"] == "kill_switch_drawdown"
        assert "drawdown_pct" in v["inputs"]
    # the rail vetoed BEFORE sizing — no notional was ever computed for it
    assert "notional" not in ks_vetoes[0]


def test_daily_loss_limit_vetoes_entries_in_kernel():
    res = _losing_run({"killswitch_dd_pct": 0.99, "daily_loss_pct": 0.05})
    events = res.metrics["rail_events"]
    breaches = [e for e in events if e["rail"] == "daily_loss_limit" and e["decision"] == "breached"]
    assert len(breaches) >= 1
    inputs = breaches[0]["inputs"]
    assert inputs["loss"] >= inputs["limit"]
    vetoes = [v for v in res.metrics["vetoes"] if v.get("rail") == "daily_loss_limit"]
    assert len(vetoes) >= 1


def test_loss_streak_cooldown_blocks_and_expires_in_kernel():
    """1m bars, 4h cooldown = 240 bars: three quick losses arm the cooldown,
    entries stop, and after expiry the machine trades again — the timing is
    the rail's contract, measured on the tape's clock."""
    # leverage 0.5: 1% per stop-out — below the daily 5% for several losses,
    # and the kill-switch effectively off, so the cooldown is the only rail
    # that can fire
    res = _losing_run(
        {"killswitch_dd_pct": 0.99, "daily_loss_pct": 0.99, "leverage": 0.5},
        n=600,
    )
    events = res.metrics["rail_events"]
    starts = [e for e in events if e["rail"] == "loss_streak_cooldown" and e["decision"] == "cooldown_started"]
    assert len(starts) >= 1, f"cooldown never armed: trades={len(res.trades)} events={events[:4]}"
    first = starts[0]
    assert first["inputs"]["streak"] == 3
    assert first["inputs"]["cooldown_hours"] == 4.0

    cd_vetoes = [v for v in res.metrics["vetoes"] if v.get("rail") == "loss_streak_cooldown"]
    assert len(cd_vetoes) >= 1
    # cooldown timing on the tape clock: every veto sits inside one of the
    # armed windows, and entries flow again after expiry — proof the timing
    # is the contract, not a perpetual block. The machine re-arms cycles:
    # trade 3 losses, cool down 240 minutes, repeat.
    windows = [(s["ts"], s["ts"] + 4 * 3600) for s in starts]
    for v in cd_vetoes:
        assert any(a <= v["tape_ts"] < b for a, b in windows), (
            f"veto at {v['tape_ts']} is outside every cooldown window {windows[:3]}"
        )
    armed_ts = first["ts"]
    late_trades = [t for t in res.trades if pd.Timestamp(t["entry_time"]).timestamp() > armed_ts + 4 * 3600]
    assert late_trades, "the machine must trade again after the cooldown expires"


def test_manual_killswitch_fail_closed():
    """Tripped manual kill-switch: zero trades, every entry vetoed. And a
    check that ERRORS reads as tripped — a rail that cannot see its state
    says no."""
    df = build_features(_falling(n=200))
    cfg = BTConfig(fee_pct=0.0, slippage_bps=0.0, confidence_min=0.5, leverage=5.0,
                   max_symbol_exposure=500.0, max_gross_exposure=500.0)

    tripped = run_kernel_backtest(df.copy(), LongEveryBar(), cfg, "1m", manual_halt_check=lambda: True)
    assert tripped.trades == []
    vetoes = [v for v in tripped.metrics["vetoes"] if v.get("rail") == "manual_killswitch"]
    assert len(vetoes) >= 1

    def broken():
        raise RuntimeError("database unreachable")

    failed = run_kernel_backtest(df.copy(), LongEveryBar(), cfg, "1m", manual_halt_check=broken)
    assert failed.trades == [], "a kill-switch check that errors must fail CLOSED"
    fvetoes = [v for v in failed.metrics["vetoes"] if v.get("rail") == "manual_killswitch"]
    assert len(fvetoes) >= 1
    assert "check_error" in fvetoes[0]["inputs"]


def test_halt_sentinel_blocks_entries(tmp_path):
    sentinel = tmp_path / "HALT"
    df = build_features(_falling(n=200))
    cfg = BTConfig(fee_pct=0.0, slippage_bps=0.0, confidence_min=0.5, leverage=5.0,
                   max_symbol_exposure=500.0, max_gross_exposure=500.0)

    clear = run_kernel_backtest(df.copy(), LongEveryBar(), cfg, "1m", halt_sentinel_path=str(sentinel))
    assert len(clear.trades) >= 1, "no sentinel file — entries flow"

    sentinel.write_text("anything, even corrupt: \x00\x01")
    halted = run_kernel_backtest(df.copy(), LongEveryBar(), cfg, "1m", halt_sentinel_path=str(sentinel))
    assert halted.trades == []
    vetoes = [v for v in halted.metrics["vetoes"] if v.get("rail") == "halt_sentinel"]
    assert len(vetoes) >= 1


# ------------------------------------------------------- desk persistence


@pytest.fixture()
def session_factory(tmp_path):
    from trading.models import init_schema, make_engine, make_session_factory

    engine = make_engine(f"sqlite:///{tmp_path}/rails.db")
    init_schema(engine)
    return make_session_factory(engine)


def test_desk_veto_hook_writes_risk_events_row(session_factory):
    """The DB seam: a veto leaving the harness becomes a risk_events row with
    the rail name and every input — the row IS the explanation."""
    import json

    import sqlalchemy as sa

    from trading.desk.node import DeskNode, DeskSpec
    from trading.models import RiskEvent

    desk = DeskNode(specs=[], session_factory=session_factory, seed_history=lambda s, t: [])
    spec = DeskSpec(bot="scalp-v1", symbol="BTCUSDT", timeframe="4h", strategy_cls=object)
    hook = desk._make_veto_hook(spec)
    hook(
        {
            "rail": "kill_switch_drawdown",
            "reason": "kill_switch_drawdown",
            "instrument": "BTCUSDT-PERP.BINANCE",
            "side": "long",
            "signal_bar": 150,
            "tape_ts": 1_700_000_000.0,
            "inputs": {"peak_equity": 1000.0, "realized_net": 870.0, "drawdown_pct": 0.13},
        }
    )
    session = session_factory()
    try:
        rows = list(session.execute(sa.select(RiskEvent)).scalars())
    finally:
        session.close()
    assert len(rows) == 1
    row = rows[0]
    assert row.bot == "scalp-v1"
    assert row.rail == "kill_switch_drawdown"
    assert row.decision == "veto"
    inputs = json.loads(row.inputs_json)
    assert inputs["peak_equity"] == 1000.0
    assert inputs["signal_bar"] == 150
    assert row.tape_ts == 1_700_000_000.0


def test_desk_rail_hook_writes_non_veto_events(session_factory):
    import json

    import sqlalchemy as sa

    from trading.desk.node import DeskNode, DeskSpec
    from trading.models import RiskEvent

    desk = DeskNode(specs=[], session_factory=session_factory, seed_history=lambda s, t: [])
    spec = DeskSpec(bot="scalp-v1", symbol="BTCUSDT", timeframe="4h", strategy_cls=object)
    hook = desk._make_rail_hook(spec)
    hook({"rail": "loss_streak_cooldown", "decision": "cooldown_started",
          "inputs": {"streak": 3}, "ts": 1_700_000_000.0})
    session = session_factory()
    try:
        rows = list(session.execute(sa.select(RiskEvent)).scalars())
    finally:
        session.close()
    assert len(rows) == 1
    assert rows[0].decision == "cooldown_started"
    assert json.loads(rows[0].inputs_json)["streak"] == 3


def test_desk_boots_empty_roster(session_factory):
    """The honest M3 end state: an empty roster is a first-class boot, not a
    crash — zero strategies, a ledger that exists, nothing traded, nothing
    rearmed."""
    from trading.desk.node import DeskNode

    desk = DeskNode(specs=[], session_factory=session_factory, seed_history=lambda s, t: [])
    desk.build()
    assert desk.states == {}
    assert desk._realized_total() == desk.initial_equity
    desk.rearm_open_positions()  # no-op, must not raise
    try:
        desk.node.stop()
    except Exception:
        pass


# ------------------------------------------------------------ api endpoint


def test_rails_endpoint_empty_is_honest(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers.trading import get_trading_db, router
    from trading.models import init_schema, make_engine, make_session_factory

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
    res = c.get("/api/trading/status")
    assert res.status_code == 200
    assert res.json()["strategies_registered"] == 0

    res = c.get("/api/trading/rails")
    assert res.status_code == 200
    body = res.json()
    assert body["bots"] == []
    assert body["recent_events"] == []
    assert body["manual_killswitch"] is False
    assert body["halt_sentinel"] is False
    app.dependency_overrides.clear()
    engine.dispose()


def test_rails_endpoint_reads_snapshots_and_events(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers.trading import get_trading_db, router
    from trading.models import RiskEvent, init_schema, make_engine, make_session_factory, set_state

    engine = make_engine(f"sqlite:///{tmp_path}/t.db")
    init_schema(engine)
    sf = make_session_factory(engine)
    with sf() as session:
        set_state(session, "rails/scalp-v1", {
            "written_at": "2026-11-26T10:00:00+00:00",
            "equity": 950.0, "peak_equity": 1000.0, "drawdown_pct": 0.05,
            "killswitch_dd_pct": 0.12, "kill_tripped": False,
            "daily_loss": 20.0, "daily_loss_limit": 50.0, "daily_loss_consumed": 0.4,
            "daily_breached": False, "loss_streak": 2, "max_losses": 3,
            "cooldown_remaining_s": 0.0, "vetoes_total": 1,
            "exposure": {"instrument_notional": 100.0, "gross_notional": 100.0,
                         "symbol_cap": 5.0, "gross_cap": 8.0},
        })
        session.add(RiskEvent(bot="scalp-v1", symbol="BTCUSDT", rail="daily_loss_limit",
                              decision="veto", inputs_json='{"loss": 20.0}', tape_ts=1.0))
        session.commit()

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
    body = res.json()
    assert len(body["bots"]) == 1
    bot = body["bots"][0]
    assert bot["bot"] == "scalp-v1"
    assert bot["drawdown_pct"] == 0.05
    assert bot["daily_loss_consumed"] == 0.4
    assert bot["loss_streak"] == 2
    assert bot["exposure"]["gross_cap"] == 8.0
    assert len(body["recent_events"]) == 1
    assert body["recent_events"][0]["rail"] == "daily_loss_limit"
    assert body["recent_events"][0]["inputs"]["loss"] == 20.0
    app.dependency_overrides.clear()
    engine.dispose()
