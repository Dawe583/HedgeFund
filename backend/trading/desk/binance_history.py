"""Historical klines (OHLCV) from the Binance USDT-M futures public REST API.

Thin synchronous fetcher used to seed desk warm-up frames. No API key, no
signing — ``GET /fapi/v1/klines`` is public market data.

Transport is httpx (the project's one HTTP convention) in sync mode; the
retry discipline is exactly one retry with a short backoff on transient
network errors and HTTP 429/5xx, then a RuntimeError. Tests substitute the
transport by monkeypatching ``_http_get`` — no real network in unit tests.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

FAPI_KLINES = "https://fapi.binance.com/fapi/v1/klines"

# Connect 5s, read 10s — slow public endpoints must not hang the desk boot.
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

MAX_LIMIT = 1500  # binance hard cap per klines call

# One retry only, after this pause. Module-level so tests can zero it.
_RETRY_BACKOFF_S = 0.5

# Desk timeframe vocabulary (kernel.TIMEFRAME_NS keys) → binance interval.
# The two vocabularies happen to spell the same; the module owns the mapping
# so the desk never depends on that coincidence.
_TIMEFRAME_TO_INTERVAL = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    """Process-wide sync client, built lazily so importing this module (and
    running tests against it) never touches the network."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=_TIMEOUT)
    return _client


def _http_get(url: str, params: dict) -> httpx.Response:
    """One single network attempt — the seam tests patch."""
    return _get_client().get(url, params=params)


def _ms_to_dt(ms: int) -> datetime:
    """Exact integer ms → tz-aware UTC datetime (no float round-trip)."""
    return _EPOCH + timedelta(milliseconds=ms)


def _dt_to_ms(dt: datetime) -> int:
    """Exact tz-aware datetime → unix ms. Naive input is assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - _EPOCH) // timedelta(milliseconds=1)


def _interval(timeframe: str) -> str:
    try:
        return _TIMEFRAME_TO_INTERVAL[timeframe]
    except KeyError:
        supported = ", ".join(sorted(_TIMEFRAME_TO_INTERVAL))
        raise ValueError(
            f"unsupported timeframe {timeframe!r}; supported: {supported}"
        ) from None


def _get_rows(params: dict) -> list[list]:
    """GET klines with the module's retry discipline.

    Retries exactly once after a short backoff on transient network errors
    and HTTP 429/5xx. Other 4xx are caller/input errors — no retry. A second
    failure raises RuntimeError carrying the status/code.
    """
    last_error: str | None = None
    for attempt in range(2):
        if attempt:
            time.sleep(_RETRY_BACKOFF_S)
        try:
            resp = _http_get(FAPI_KLINES, params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = f"network error: {exc}"
            continue
        status = resp.status_code
        if status == 200:
            return resp.json()
        detail = resp.text[:200]
        if status == 429 or status >= 500:
            last_error = f"HTTP {status}: {detail}"
            continue
        raise RuntimeError(
            f"binance klines GET failed: HTTP {status}: {detail} "
            f"(params {params}) — not retryable"
        )
    raise RuntimeError(
        f"binance klines GET failed after retry: {last_error} (params {params})"
    )


def _parse_rows(rows: list[list]) -> list[dict]:
    """Raw binance rows → contract dicts, ordered oldest → newest.

    Only the first six fields of each row are meaningful here:
    [open_time_ms, open, high, low, close, volume, ...ignored].
    """
    bars = [
        {
            "open_time": _ms_to_dt(int(row[0])),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in rows
    ]
    bars.sort(key=lambda bar: bar["open_time"])
    return bars


def fetch_klines(symbol: str, timeframe: str, *, limit: int = 1500) -> list[dict]:
    """Binance USDT-M perpetual klines, public REST, no keys.

    Returns dicts ordered oldest → newest (newest last), each:
      open_time: tz-aware datetime UTC (the bar's OPEN time)
      open, high, low, close, volume: float
    `timeframe` is the desk's vocabulary: "1m", "4h", "1d" etc. — the module
    owns the mapping to binance interval strings.
    `limit` caps rows (binance returns at most 1500 per call); raise ValueError
    above that. The LAST row may be the still-forming bar — that is correct
    for warm-up seeding because IncrementalFrame treats bars as truth only
    once closed; the caller decides. It is deliberately NOT dropped here.

    One page per call — for deeper history use fetch_klines_range.
    """
    interval = _interval(timeframe)
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be within 1..{MAX_LIMIT}, got {limit}")
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    rows = _get_rows(params)
    log.debug(
        "binance klines %s %s limit=%d -> %d rows", params["symbol"], interval, limit, len(rows)
    )
    return _parse_rows(rows)


def fetch_klines_range(
    symbol: str, timeframe: str, start: datetime, end: datetime
) -> list[dict]:
    """All klines with open_time in [start, end] (inclusive), oldest → newest.

    Paginates backwards from `end`: binance answers an endTime-only request
    with the most recent `limit` rows at or before it (while a startTime in
    the request would flip it to oldest-forward paging), so each page steps
    endTime to just before the earliest bar seen and the client clips to
    [start, end]. Rows are deduplicated by open_time — page boundaries and
    repeated walks can overlap by a bar. Same one-retry discipline as
    fetch_klines. The row covering `end` may be the still-forming bar; it is
    kept, as in fetch_klines.
    """
    interval = _interval(timeframe)
    if end <= start:
        raise ValueError(f"end must be after start, got start={start} end={end}")
    start_ms = _dt_to_ms(start)
    cursor_ms = _dt_to_ms(end)
    symbol = symbol.upper()

    pages: dict[int, list] = {}  # open_time ms → raw row, dedupes overlaps
    while True:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": MAX_LIMIT,
            "endTime": cursor_ms,
        }
        rows = _get_rows(params)
        log.debug(
            "binance klines %s %s endTime=%d -> %d rows", symbol, interval, cursor_ms, len(rows)
        )
        if not rows:
            break
        for row in rows:
            pages[int(row[0])] = row
        earliest_ms = min(int(row[0]) for row in rows)
        # Done when the page reached past `start`, or when a short page says
        # fewer than MAX_LIMIT bars exist in all history before the cursor.
        if earliest_ms <= start_ms or len(rows) < MAX_LIMIT:
            break
        cursor_ms = earliest_ms - 1  # endTime is inclusive; step just past it

    rows = sorted(
        (row for ms, row in pages.items() if start_ms <= ms <= _dt_to_ms(end)),
        key=lambda row: int(row[0]),
    )
    return _parse_rows(rows)
