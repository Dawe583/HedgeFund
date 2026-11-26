"""Unit tests for trading.desk.binance_history — no real network.

The transport seam is the module's ``_http_get`` (one single attempt); tests
monkeypatch it with scripted fakes. Retry backoff is zeroed so the suite
never sleeps.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

import trading.desk.binance_history as bh
from trading.desk.binance_history import fetch_klines, fetch_klines_range


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(bh, "_RETRY_BACKOFF_S", 0.0)


def make_row(open_ms: int, price: float = 100.0) -> list:
    """A realistic 12-field binance kline row."""
    return [
        open_ms,
        str(price),  # open
        str(price + 1),  # high
        str(price - 1),  # low
        str(price + 0.5),  # close
        "1234.5",  # volume
        open_ms + 59_999,  # close_time
        "99999.9",  # quote volume — everything below must be ignored
        42,  # trades
        "1.0",
        "2.0",
        "0",
    ]


def response(rows: list, status: int = 200) -> httpx.Response:
    if status == 200:
        return httpx.Response(200, json=rows)
    return httpx.Response(status, text=f"binance error body {status}")


def patch_transport(monkeypatch, fn):
    """fn(url, params) -> httpx.Response | raises — installed as the transport."""
    monkeypatch.setattr(bh, "_http_get", fn)


# ---------------------------------------------------------------- parsing


def test_row_parsing_first_six_fields_only(monkeypatch):
    rows = [make_row(1_700_000_000_000, price=100.0)]
    patch_transport(monkeypatch, lambda url, params: response(rows))

    (bar,) = fetch_klines("BTCUSDT", "4h")

    assert bar["open"] == 100.0
    assert bar["high"] == 101.0
    assert bar["low"] == 99.0
    assert bar["close"] == 100.5
    assert bar["volume"] == 1234.5
    assert all(isinstance(bar[k], float) for k in ("open", "high", "low", "close", "volume"))
    # nothing of the trailing row fields leaks into the contract dict
    assert set(bar) == {"open_time", "open", "high", "low", "close", "volume"}


def test_oldest_to_newest_ordering_even_if_upstream_unordered(monkeypatch):
    rows = [
        make_row(1_700_000_200_000),
        make_row(1_700_000_000_000),
        make_row(1_700_000_100_000),
    ]
    patch_transport(monkeypatch, lambda url, params: response(rows))

    bars = fetch_klines("BTCUSDT", "1m", limit=3)

    times = [b["open_time"] for b in bars]
    assert times == sorted(times)
    assert times[0] < times[1] < times[2]


def test_open_time_exact_ms_and_tz_aware(monkeypatch):
    # a ms value with non-zero sub-second part — must survive exactly
    ms = 1_700_000_000_123
    patch_transport(monkeypatch, lambda url, params: response([make_row(ms)]))

    (bar,) = fetch_klines("BTCUSDT", "1m", limit=1)

    assert bar["open_time"].tzinfo is not None
    assert bar["open_time"].utcoffset() == timedelta(0)
    assert bar["open_time"] == datetime(2023, 11, 14, 22, 13, 20, 123000, tzinfo=timezone.utc)


def test_forming_bar_is_not_dropped(monkeypatch):
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    rows = [make_row(now_ms - 3_600_000), make_row(now_ms)]  # last bar still forming
    patch_transport(monkeypatch, lambda url, params: response(rows))

    bars = fetch_klines("BTCUSDT", "1h", limit=2)

    assert len(bars) == 2  # both rows kept, caller decides


def test_symbol_is_uppercased(monkeypatch):
    seen = {}

    def fake(url, params):
        seen.update(params)
        return response([make_row(1_700_000_000_000)])

    patch_transport(monkeypatch, fake)
    fetch_klines("btcusdt", "1h", limit=1)

    assert seen["symbol"] == "BTCUSDT"
    assert seen["interval"] == "1h"


# ------------------------------------------------------------- validation


def test_unknown_timeframe_raises_listing_supported():
    with pytest.raises(ValueError) as excinfo:
        fetch_klines("BTCUSDT", "3h")
    msg = str(excinfo.value)
    assert "3h" in msg
    for tf in ("1m", "5m", "15m", "1h", "4h", "1d"):
        assert tf in msg  # the error lists the supported set


def test_limit_above_1500_raises():
    with pytest.raises(ValueError):
        fetch_klines("BTCUSDT", "1h", limit=1501)


def test_limit_below_one_raises():
    with pytest.raises(ValueError):
        fetch_klines("BTCUSDT", "1h", limit=0)


def test_limit_1500_accepted(monkeypatch):
    patch_transport(monkeypatch, lambda url, params: response([make_row(1_700_000_000_000)]))
    assert len(fetch_klines("BTCUSDT", "1h", limit=1500)) == 1


# ---------------------------------------------------------------- retries


def test_network_error_retried_once_then_success(monkeypatch):
    calls = []

    def flaky(url, params):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("connection reset")
        return response([make_row(1_700_000_000_000)])

    patch_transport(monkeypatch, flaky)
    bars = fetch_klines("BTCUSDT", "1h", limit=1)

    assert len(bars) == 1
    assert len(calls) == 2


def test_network_error_twice_raises_runtime_error(monkeypatch):
    calls = []

    def dead(url, params):
        calls.append(1)
        raise httpx.ConnectTimeout("no route")

    patch_transport(monkeypatch, dead)

    with pytest.raises(RuntimeError, match="after retry"):
        fetch_klines("BTCUSDT", "1h", limit=1)
    assert len(calls) == 2  # exactly one retry, no loop


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retryable_status_then_success(monkeypatch, status):
    calls = []

    def flaky(url, params):
        calls.append(1)
        if len(calls) == 1:
            return response([], status=status)
        return response([make_row(1_700_000_000_000)])

    patch_transport(monkeypatch, flaky)
    assert len(fetch_klines("BTCUSDT", "1h", limit=1)) == 1
    assert len(calls) == 2


def test_retryable_status_twice_raises_with_status_in_message(monkeypatch):
    patch_transport(monkeypatch, lambda url, params: response([], status=500))

    with pytest.raises(RuntimeError) as excinfo:
        fetch_klines("BTCUSDT", "1h", limit=1)
    assert "500" in str(excinfo.value)


def test_client_error_400_not_retried(monkeypatch):
    calls = []

    def bad(url, params):
        calls.append(1)
        return response([], status=400)

    patch_transport(monkeypatch, bad)

    with pytest.raises(RuntimeError) as excinfo:
        fetch_klines("BTCUSDT", "1h", limit=1)
    assert "400" in str(excinfo.value)
    assert len(calls) == 1  # 4xx input errors are not retryable


# ------------------------------------------------------------- pagination


HOUR_MS = 3_600_000
T0_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z, aligned to the hour


def binance_server(rows_by_ms: dict, *, duplicate_first_row: bool = False):
    """Fake matching observed binance semantics: an endTime-only request gets
    the most recent `limit` rows with open_time <= endTime. Asserts the module
    never passes startTime (which would flip binance to forward paging)."""

    def fake(url, params):
        assert "startTime" not in params, "backwards walk must not pass startTime"
        end_ms = params["endTime"]
        limit = params["limit"]
        eligible = sorted(ms for ms in rows_by_ms if ms <= end_ms)
        page_ms = eligible[-limit:]
        rows = [rows_by_ms[ms] for ms in page_ms]
        if rows and duplicate_first_row:
            rows = [rows[0]] + rows  # overlap/glitch the dedupe must absorb
        return response(rows)

    return fake


def make_grid(n_hours: int, price0: float = 100.0) -> dict:
    """Hourly bars for hours 0..n_hours-1 from T0, keyed by open_time ms."""
    return {T0_MS + h * HOUR_MS: make_row(T0_MS + h * HOUR_MS, price0 + h) for h in range(n_hours)}


def hour(h: int) -> datetime:
    return datetime.fromtimestamp((T0_MS + h * HOUR_MS) / 1000, tz=timezone.utc)


def test_range_paginates_backwards_and_reassembles(monkeypatch):
    grid = make_grid(5000)
    patch_transport(monkeypatch, binance_server(grid))
    calls = []

    orig = bh._http_get
    def counting(url, params):
        calls.append(params["endTime"])
        return orig(url, params)
    monkeypatch.setattr(bh, "_http_get", counting)

    bars = fetch_klines_range("BTCUSDT", "1h", start=hour(10), end=hour(3500))

    # hours 10..3500 inclusive = 3491 bars, three 1500-cap pages
    assert len(bars) == 3491
    assert len(calls) == 3
    assert calls == sorted(calls, reverse=True)  # endTime strictly walks backwards
    times = [b["open_time"] for b in bars]
    assert times == sorted(times)
    assert bars[0]["open_time"] == hour(10)  # clipped exactly to [start, end]
    assert bars[-1]["open_time"] == hour(3500)
    assert bars[0]["open"] == pytest.approx(110.0)  # price0 + hour 10


def test_range_dedupes_overlapping_rows(monkeypatch):
    grid = make_grid(4000)
    patch_transport(monkeypatch, binance_server(grid, duplicate_first_row=True))

    bars = fetch_klines_range("BTCUSDT", "1h", start=hour(5), end=hour(3999))

    times = [b["open_time"] for b in bars]
    assert len(times) == len(set(times))  # zero duplicates despite glued pages
    assert len(bars) == 3999 - 5 + 1


def test_range_empty_when_no_data(monkeypatch):
    patch_transport(monkeypatch, binance_server({}))
    assert fetch_klines_range("BTCUSDT", "1h", start=hour(10), end=hour(20)) == []


def test_range_inverted_raises():
    with pytest.raises(ValueError):
        fetch_klines_range("BTCUSDT", "1h", start=hour(20), end=hour(10))


def test_range_unknown_timeframe_raises():
    with pytest.raises(ValueError):
        fetch_klines_range("BTCUSDT", "2h", start=hour(10), end=hour(20))


def test_range_naive_datetimes_treated_as_utc(monkeypatch):
    grid = make_grid(100)
    patch_transport(monkeypatch, binance_server(grid))

    naive_start = datetime(2024, 1, 1, 0, 0) + timedelta(hours=10)  # no tzinfo
    naive_end = datetime(2024, 1, 1, 0, 0) + timedelta(hours=20)
    bars = fetch_klines_range("BTCUSDT", "1h", start=naive_start, end=naive_end)

    assert len(bars) == 11
    assert bars[0]["open_time"] == hour(10)
