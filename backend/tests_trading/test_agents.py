import pytest

from trading.agents.analyst import MarketAnalyst
from trading.agents.base import Insight
from trading.agents.openrouter import OpenRouterClient
from trading.agents.reviewer import SignalReviewer
from trading.backtest.engine import Signal


@pytest.fixture
def client_no_key():
    # force offline even when .env carries a real key — tests must be hermetic
    c = OpenRouterClient(api_key=None)
    c.api_key = None
    return c


@pytest.mark.asyncio
async def test_client_without_key_returns_none(client_no_key):
    assert not client_no_key.available
    out = await client_no_key.chat(system="s", user="u")
    assert out is None


@pytest.mark.asyncio
async def test_analyst_fallback_produces_insight(client_no_key):
    agent = MarketAnalyst(client_no_key)
    insight = await agent.run(
        {
            "symbol": "BTCUSDT",
            "price": 77_000,
            "trend_strength": 2.1,
            "rsi": 61,
            "atr_pct": 1.4,
            "rvol": 3.1,
            "regime": 0.02,
        }
    )
    assert isinstance(insight, Insight)
    assert "UP-trend" in insight.title or "DOWN-trend" in insight.title
    assert insight.body.startswith("[heuristic]")


def _ctx(side="long", conf=0.7, ts=1.5, atr=1.2, blackout=False):
    return {
        "bot": "scalp",
        "signal": Signal(side=side, confidence=conf),
        "symbol": "BTCUSDT",
        "price": 77_000,
        "trend_strength": ts,
        "rsi": 55,
        "atr_pct": atr,
        "news_blackout": blackout,
    }


@pytest.mark.asyncio
async def test_reviewer_approves_aligned_setup(client_no_key):
    reviewer = SignalReviewer(client_no_key)
    approved, conf, insight = await reviewer.review(_ctx())
    assert approved
    assert conf >= 0.55
    assert insight.meta["source"] == "fallback"


@pytest.mark.asyncio
async def test_reviewer_vetoes_counter_trend(client_no_key):
    reviewer = SignalReviewer(client_no_key)
    approved, _, _ = await reviewer.review(_ctx(side="short", ts=2.5))
    assert not approved


@pytest.mark.asyncio
async def test_reviewer_vetoes_blackout(client_no_key):
    reviewer = SignalReviewer(client_no_key)
    approved, _, _ = await reviewer.review(_ctx(blackout=True))
    assert not approved


@pytest.mark.asyncio
async def test_reviewer_vetoes_chaos_vol(client_no_key):
    reviewer = SignalReviewer(client_no_key)
    approved, _, _ = await reviewer.review(_ctx(atr=7.0))
    assert not approved
