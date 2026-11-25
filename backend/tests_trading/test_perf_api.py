"""Tests for the read-only perf analytics router (pure helpers + HTTP)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading.api.perf import (
    build_summary,
    format_trade,
    router,
    summarize_trades,
)


def test_summarize_trades_per_bot():
    rows = [
        {"bot": "hft", "pnl": 10.0, "confidence": 0.8},
        {"bot": "hft", "pnl": -4.0, "confidence": 0.6},
        {"bot": "scalp", "pnl": 5.0, "confidence": 0.9},
    ]
    out = summarize_trades(rows)
    assert out["hft"]["trades"] == 2
    assert out["hft"]["wins"] == 1
    assert out["hft"]["winrate"] == 0.5
    assert out["hft"]["total_pnl"] == 6.0
    assert out["hft"]["avg_conf"] == 0.7
    assert out["scalp"]["wins"] == 1
    assert out["scalp"]["winrate"] == 1.0


def test_summarize_trades_empty():
    assert summarize_trades([]) == {}


def test_build_summary_equity_math():
    rows = [{"bot": "hft", "pnl": 20.0, "confidence": 0.5}]
    out = build_summary(rows, 1000.0)
    assert out["equity_start"] == 1000.0
    assert out["equity_now"] == 1020.0
    assert out["per_bot"]["hft"]["trades"] == 1


def test_format_trade_pnl_pct():
    row = {
        "id": 1, "bot": "hft", "symbol": "BTCUSDT", "side": "long",
        "qty": 1.0, "entry_price": 100.0, "exit_price": 110.0,
        "entry_time": "2026-01-01", "exit_time": "2026-01-02",
        "pnl": 10.0, "confidence": 0.75,
    }
    out = format_trade(row)
    assert out["pnl"] == 10.0
    assert out["pnl_pct"] == 10.0
    assert out["bot"] == "hft"


def test_format_trade_zero_notional_no_crash():
    out = format_trade({"bot": "hft", "pnl": 0.0, "qty": 0.0, "entry_price": 0.0})
    assert out["pnl_pct"] == 0.0


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_http_summary_shape():
    # Read-only endpoint: must return {} or a well-shaped summary, never raise.
    r = _client().get("/api/perf/summary")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    if body:
        assert {"per_bot", "equity_start", "equity_now"} <= set(body)


def test_http_journal_shape():
    r = _client().get("/api/journal" if False else "/api/perf/journal", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


def test_http_journal_bot_filter():
    r = _client().get("/api/perf/journal", params={"bot": "hft", "limit": 5})
    assert r.status_code == 200
    assert isinstance(r.json(), list)
