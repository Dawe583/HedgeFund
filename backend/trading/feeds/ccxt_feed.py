"""ccxt multi-venue crypto feed — the second crypto data plane.

Binance remains the primary tape (deepest history, the desk trades it);
ccxt extends coverage to venues and instruments Binance does not carry —
OKX perpetuals, spot pairs, smaller caps. The fallback chain in
trading.feeds.fallback tries Binance first and ccxt venues after, so a
symbol that exists anywhere is never a silent hole.

Rows match the candle schema exactly: open_time UTC, OHLCV floats.
Rate limiting is the venue's own — ccxt handles throttling internally.
"""

from __future__ import annotations

import datetime as dt


def _ccxt():
    try:
        import ccxt

        return ccxt
    except ImportError as exc:
        raise SystemExit("ccxt is not installed — run `uv add ccxt`") from exc


async def fetch_ccxt_candles(
    symbol: str = "BTC/USDT:USDT",
    interval: str = "1h",
    days: int = 365,
    venue: str = "binanceusdm",
) -> tuple[list[dict], str]:
    """OHLCV from any ccxt venue. Symbol in ccxt's unified format
    (BASE/QUOTE or BASE/QUOTE:SETTLE for perps). Returns (rows, venue)."""
    import asyncio

    ccxt = _ccxt()
    if venue not in ccxt.exchanges:
        raise SystemExit(f"unknown ccxt venue {venue!r} — see ccxt.exchanges")
    ex = getattr(ccxt, venue)({"enableRateLimit": True})
    since_ms = int((dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).timestamp() * 1000)

    def _fetch():
        out = []
        cursor = since_ms
        while True:
            batch = ex.fetch_ohlcv(symbol, timeframe=interval, since=cursor, limit=1000)
            if not batch:
                break
            out.extend(batch)
            cursor = batch[-1][0] + 1
            if len(batch) < 1000:
                break
        return out

    raw = await asyncio.to_thread(_fetch)
    rows = []
    for r in raw:
        rows.append(
            {
                "open_time": dt.datetime.fromtimestamp(r[0] / 1000, tz=dt.UTC),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            }
        )
    return rows, f"ccxt:{venue}"
