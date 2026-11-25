from trading.config import Settings
from trading.risk import RiskManager


def test_kill_switch_trips_at_dd():
    rm = RiskManager(Settings(paper_equity_start=1000, risk_killswitch_dd_pct=0.06))
    assert not rm.kill_switch(1000, 950)
    assert rm.kill_switch(1000, 930)  # -7%


def test_daily_loss_breach():
    rm = RiskManager(Settings(risk_max_daily_loss_pct=0.02))
    assert not rm.daily_loss_breached(1000, 985)
    assert rm.daily_loss_breached(1000, 978)


def test_sizing_caps_exposure():
    s = Settings(paper_equity_start=10_000, risk_per_trade_risk_pct=0.01, risk_max_exposure_pct=0.3)
    rm = RiskManager(s)
    # tiny stop distance would explode notional -> must be capped
    qty = rm.size_position(equity=10_000, confidence=0.9, stop_dist_pct=0.0001)
    assert qty <= 10_000 * s.risk_max_exposure_pct


def test_news_blackout_shape():
    import datetime as dt

    inside = dt.datetime(2026, 1, 1, 12, 30, 30, tzinfo=dt.UTC)
    outside = dt.datetime(2026, 1, 1, 15, 0, 0, tzinfo=dt.UTC)
    assert RiskManager.is_news_blackout(inside)
    assert not RiskManager.is_news_blackout(outside)
