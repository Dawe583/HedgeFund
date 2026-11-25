"""Resilient klines fetch — Binance first, Hyperliquid fallback (HTTP 451 geo-blocks)."""

import logging

from trading.feeds.binance import fetch_klines as _binance_fetch
from trading.feeds.hyperliquid import fetch_candles as _hl_fetch

log = logging.getLogger(__name__)


async def fetch_candles_any(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    **kwargs,
) -> tuple[list[dict], str]:
    """Returns (rows, venue). Tries Binance, falls back to Hyperliquid perp."""
    try:
        return await _binance_fetch(symbol, interval, **kwargs), "binance"
    except Exception as exc:  # noqa: BLE001 — 451/timeout/blocks all fall back
        log.warning("binance unavailable (%s) → falling back to Hyperliquid", exc)
    hl_coin = symbol.upper().replace("USDT", "").replace("USD", "") or "BTC"
    rows = await _hl_fetch(coin=hl_coin, interval=interval, **kwargs)
    return rows, "hyperliquid"


from trading.feeds.binance import fetch_klines, stream_klines  # noqa: F401
