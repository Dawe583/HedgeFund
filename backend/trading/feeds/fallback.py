"""Resilient klines fetch — Binance first, Hyperliquid fallback (HTTP 451 geo-blocks).

The market dimension is explicit (analysis F-3): default 'perp' because the
desk trades USD-M perpetuals and a validation on the spot tape measured an
instrument nobody trades. The returned venue string is the row's identity
in the store — 'binance-usdm' / 'binance' / 'hyperliquid' — never a guess.
"""

import logging

from trading.feeds.binance import fetch_klines as _binance_fetch
from trading.feeds.hyperliquid import fetch_candles as _hl_fetch

log = logging.getLogger(__name__)


async def fetch_candles_any(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    market: str = "perp",
    **kwargs,
) -> tuple[list[dict], str]:
    """Returns (rows, venue). Tries Binance at the requested market, falls
    back to Hyperliquid — which lists perpetuals only, so a spot caller
    gets no fallback: Hyperliquid cannot price what it does not trade, and
    a silent spot/perp substitution is exactly the venue mixing this feed
    exists to end."""
    from trading.feeds.binance import MARKET_META

    try:
        return await _binance_fetch(symbol, interval, market=market, **kwargs), MARKET_META[market]["venue"]
    except Exception as exc:  # noqa: BLE001 — 451/timeout/blocks all fall back
        log.warning("binance %s unavailable (%s)", market, exc)
    if market != "perp":
        raise SystemExit(
            f"binance spot unreachable and no spot fallback exists — "
            f"Hyperliquid lists perps only; refusing a silent instrument substitution"
        )
    log.warning("falling back to Hyperliquid perp")
    hl_coin = symbol.upper().replace("USDT", "").replace("USD", "") or "BTC"
    rows = await _hl_fetch(coin=hl_coin, interval=interval, **kwargs)
    return rows, "hyperliquid"


from trading.feeds.binance import fetch_klines, stream_klines  # noqa: F401
