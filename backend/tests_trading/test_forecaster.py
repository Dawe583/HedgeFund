"""Tests for the per-bot market forecaster (agents/forecaster.py)."""

import pandas as pd
import pytest

from trading.agents.forecaster import Forecaster, _f
from trading.agents.openrouter import OpenRouterClient
from trading.models import AgentPrediction, make_engine, make_session_factory


def _offline_client() -> OpenRouterClient:
    c = OpenRouterClient(api_key=None)
    c.api_key = None  # .env may carry a real key — tests stay hermetic
    return c


@pytest.fixture
def sf():
    return make_session_factory(make_engine("sqlite://"))


@pytest.fixture
def fc(sf):
    return Forecaster(sf, _offline_client())


def _feats(ts=1.8, rsi=62.0):
    idx = pd.date_range("2026-08-01", periods=300, freq="1h")
    return pd.DataFrame(
        {
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 10.0,
            "trend_strength": ts,
            "rsi": rsi,
            "atr_pct": 0.012,
            "rvol": 1.4,
            "regime": 0.03,
        },
        index=idx,
    )


@pytest.mark.asyncio
async def test_heuristic_forecast_up(fc, sf):
    row = await fc.run("scalp", "BTCUSDT", "4h", _feats())
    assert row["direction"] == "up"
    assert row["source"] == "heuristic"
    assert 0 < row["confidence"] <= 0.99
    assert row["expected_move_pct"] > 0
    s = sf()
    try:
        assert s.query(AgentPrediction).count() == 1
        saved = s.query(AgentPrediction).first()
        assert saved.bot == "scalp"
        assert saved.direction == "up"
    finally:
        s.close()


@pytest.mark.asyncio
async def test_heuristic_flat_in_range(fc):
    row = await fc.run("hft", "BTCUSDT", "1m", _feats(ts=0.2, rsi=50.0))
    assert row["direction"] == "flat"


@pytest.mark.asyncio
async def test_extreme_rsi_overrides_weak_trend(fc):
    row = await fc.run("hft", "BTCUSDT", "1m", _feats(ts=0.3, rsi=85.0))
    assert row["direction"] == "down"


@pytest.mark.asyncio
async def test_forecast_never_raises(fc, sf):
    broken = pd.DataFrame({"close": [1.0]})  # missing features
    out = await fc.run("scalp", "BTCUSDT", "4h", broken)
    assert out == {}
    s = sf()
    try:
        assert s.query(AgentPrediction).count() == 0
    finally:
        s.close()


def test_float_coercion():
    assert _f("1.5") == 1.5
    assert _f(None) == 0.0
    assert _f("junk", 2.0) == 2.0
