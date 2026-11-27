"""Binance public market data feed — REST backfill + WebSocket live stream.

No API keys required for market data.
"""

import asyncio
import datetime as dt
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from trading.config import get_settings

log = logging.getLogger(__name__)

TF_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

# Public REST mirrors — the Pi's route to api.binance.com drops packets for
# minutes at a time, so every backfill tries hosts in order and sticks with
# the first that answers.
_REST_HOSTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://data-api.binance.vision",
]
_working_host: str | None = None
_FAPI_HOSTS = [
    "https://fapi.binance.com",
]
_working_fapi_host: str | None = None

# The two Binance markets are different instruments: /api/v3/klines prices
# the spot pair, /fapi/v1/klines prices the USD-M perpetual the desk trades.
# `market` selects the tape; the venue labels the rows so the store keeps
# them apart — they must never share one key again (analysis F-3).
MARKET_META = {
    "spot": {"venue": "binance", "instrument_type": "spot"},
    "perp": {"venue": "binance-usdm", "instrument_type": "perp"},
}


def _parse_kline(k: list) -> dict | None:
    o, h, l, c, v = float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])
    # OHLC sanity: high must dominate, low must sit below, close inside.
    # Corrupt frames (we have seen low = 6.6e9 on flaky WiFi) would poison
    # every downstream indicator — drop instead of persisting garbage.
    if not (h >= o and h >= c and l <= o and l <= c and h >= l and c > 0):
        log.warning("dropping corrupt kline o=%s h=%s l=%s c=%s", o, h, l, c)
        return None
    return {
        "open_time": dt.datetime.fromtimestamp(k[0] / 1000, dt.UTC),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "close_time": dt.datetime.fromtimestamp(k[6] / 1000, dt.UTC),
    }


def _kline_from_ws(k: dict) -> dict | None:
    """Parse one WS kline payload into a candle dict.

    Spot WS sends lowercase h/l keys, futures sends H/L — accept both.
    Returns None for payloads without usable high/low (caller skips them).
    """
    if not isinstance(k, dict):
        return None
    high = k.get("H", k.get("h"))
    low = k.get("L", k.get("l"))
    if high is None or low is None:
        return None
    return _parse_kline([k["t"], k["o"], high, low, k["c"], k["v"], k["T"]])


async def _get_with_retry(client: httpx.AsyncClient, url: str, params: dict, attempts: int = 4):
    """GET with exponential backoff — transient timeouts must not kill backfill."""
    delay = 1.0
    for i in range(attempts):
        try:
            return await client.get(url, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if i == attempts - 1:
                raise
            log.warning("binance chunk failed (%s), retry %d/%d", exc, i + 1, attempts - 1)
            await asyncio.sleep(delay)
            delay *= 2


async def fetch_klines(
    symbol: str,
    interval: str,
    days: int | None = None,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
    market: str = "spot",
) -> list[dict]:
    """Backfill candles via public REST, paginating 1000 at a time.

    Tries every public mirror until one answers — the primary host can be
    unreachable for minutes on flaky home networks.

    `market` picks the instrument: 'spot' hits /api/v3/klines, 'perp' hits
    the USD-M futures endpoint /fapi/v1/klines — the trading truth, because
    the desk trades perps. The wire shape is identical; the tape is not.
    """
    global _working_host, _working_fapi_host
    if market not in MARKET_META:
        raise ValueError(f"unknown market {market!r} — use one of {sorted(MARKET_META)}")
    if interval not in TF_MS:
        raise ValueError(f"unsupported interval {interval}")
    end = end or dt.datetime.now(dt.UTC)
    start = start or end - dt.timedelta(days=days or 30)
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
    }

    fapi = market == "perp"
    hosts = list(_FAPI_HOSTS) if fapi else list(_REST_HOSTS)
    working = _working_fapi_host if fapi else _working_host
    if working and working in hosts:
        hosts.remove(working)
        hosts.insert(0, working)

    path = "/fapi/v1/klines" if fapi else "/api/v3/klines"
    last_exc: Exception | None = None
    for host in hosts:
        cursor_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        out: list[dict] = []
        try:
            async with httpx.AsyncClient(base_url=host, timeout=12) as client:
                while cursor_ms < end_ms:
                    resp = await _get_with_retry(
                        client,
                        path,
                        params={**params, "startTime": cursor_ms, "endTime": end_ms, "limit": 1000},
                    )
                    resp.raise_for_status()
                    rows = resp.json()
                    if not rows:
                        break
                    out.extend(c for r in rows if (c := _parse_kline(r)) is not None)
                    last_close_ms = rows[-1][6]
                    cursor_ms = last_close_ms + 1
                    if len(rows) < 1000:
                        break
                    await asyncio.sleep(0.15)  # be polite to the public API
        except Exception as exc:  # noqa: BLE001 — try the next mirror
            last_exc = exc
            log.warning("binance host %s failed (%s) — trying next mirror", host, exc)
            continue
        if fapi:
            _working_fapi_host = host
        else:
            _working_host = host
        log.info("fetched %d %s klines %s %s via %s", len(out), market, symbol, interval, host)
        return out
    raise last_exc or RuntimeError("all binance mirrors failed")


async def stream_klines(symbol: str, interval: str, market: str = "spot") -> AsyncIterator[dict]:
    """Yield *closed* klines forever, auto-reconnecting. `market` selects the
    instrument exactly as in fetch_klines — the futures stream lives on a
    different host (fstream) because it is a different instrument, not a
    mirror."""
    import json

    import websockets

    settings = get_settings()
    stream = f"{symbol.lower()}@kline_{interval}"
    base = "wss://fstream.binance.com/ws" if market == "perp" else settings.binance_ws
    url = f"{base}/{stream}"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                log.info("ws connected: %s (%s)", stream, market)
                async for raw in ws:
                    try:
                        msg: dict[str, Any] = json.loads(raw)
                    except json.JSONDecodeError:
                        continue  # corrupt frame — skip instead of killing the stream
                    k = msg.get("k")
                    if not isinstance(k, dict) or not k.get("x"):  # candle closed
                        continue
                    candle = _kline_from_ws(k)
                    if candle is None:
                        continue
                    yield candle
        except (websockets.ConnectionClosed, OSError) as exc:
            log.warning("ws dropped (%s), reconnecting in 3s", exc)
            await asyncio.sleep(3)
