"""Binance USD-M futures public intel — funding, open interest, long/short ratio.

All endpoints are public (no key). Powers the Coinglass-style panel.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

FAPI = "https://fapi.binance.com"


async def funding_rate(symbol: str = "BTCUSDT") -> dict | None:
    """Current predicted funding + next event."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{FAPI}/fapi/v1/premiumIndex", params={"symbol": symbol.upper()}
            )
            r.raise_for_status()
            d = r.json()
            return {
                "mark_price": float(d["markPrice"]),
                "index_price": float(d["indexPrice"]),
                "funding_rate_pct": round(float(d["lastFundingRate"]) * 100, 4),
                "next_funding_ts": int(d["nextFundingTime"]),
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("funding failed: %s", exc)
        return None


async def funding_history(symbol: str = "BTCUSDT", limit: int = 21) -> list[float]:
    """Last N realized 8h funding rates (percent)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{FAPI}/fapi/v1/fundingRate",
                params={"symbol": symbol.upper(), "limit": limit},
            )
            r.raise_for_status()
            return [round(float(x["fundingRate"]) * 100, 4) for x in r.json()]
    except Exception as exc:  # noqa: BLE001
        log.warning("funding history failed: %s", exc)
        return []


async def open_interest(symbol: str = "BTCUSDT") -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{FAPI}/fapi/v1/openInterest", params={"symbol": symbol.upper()})
            r.raise_for_status()
            d = r.json()
            return {"open_interest": float(d["openInterest"]), "ts": int(d["time"])}
        # OI in USD approximation done client-side with mark price
    except Exception as exc:  # noqa: BLE001
        log.warning("oi failed: %s", exc)
        return None


async def oi_history(symbol: str = "BTCUSDT", period: str = "1h", limit: int = 24) -> list[dict]:
    """Aggregate OI history — shows position build-up/drain."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{FAPI}/futures/data/openInterestHist",
                params={"symbol": symbol.upper(), "period": period, "limit": limit},
            )
            r.raise_for_status()
            return [
                {
                    "ts": int(x.get("timestamp", 0)),
                    "oi_usd": float(x.get("sumOpenInterestValue", 0) or 0),
                    "change_pct": float(x.get("sumOpenInterestChangeRate", 0) or 0) * 100,
                }
                for x in r.json()
            ]
    except Exception as exc:  # noqa: BLE001
        log.warning("oi hist failed: %s", exc)
        return []


async def long_short_ratio(symbol: str = "BTCUSDT", period: str = "1h", limit: int = 24) -> list[dict]:
    """Top-trader position ratio — crowd positioning gauge."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{FAPI}/futures/data/topLongShortPositionRatio",
                params={"symbol": symbol.upper(), "period": period, "limit": limit},
            )
            r.raise_for_status()
            return [
                {
                    "ts": int(x["timestamp"]),
                    "long_short_ratio": float(x["longShortRatio"]),
                    "long_pct": float(x["longAccount"]) * 100,
                    "short_pct": float(x["shortAccount"]) * 100,
                }
                for x in r.json()
            ]
    except Exception as exc:  # noqa: BLE001
        log.warning("lsr failed: %s", exc)
        return []


async def taker_flow(symbol: str = "BTCUSDT", period: str = "1h", limit: int = 24) -> list[dict]:
    """Taker buy/sell volume ratio — aggressive flow direction."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{FAPI}/futures/data/takerlongshortRatio",
                params={"symbol": symbol.upper(), "period": period, "limit": limit},
            )
            r.raise_for_status()
            return [
                {
                    "ts": int(x["timestamp"]),
                    "buy_sell_ratio": float(x["buySellRatio"]),
                    "buy_vol": float(x["buyVol"]),
                    "sell_vol": float(x["sellVol"]),
                }
                for x in r.json()
            ]
    except Exception as exc:  # noqa: BLE001
        log.warning("taker flow failed: %s", exc)
        return []


async def full_intel(symbol: str = "BTCUSDT") -> dict:
    """Everything the Coinglass-style panel needs, one call."""
    fr, fh, oi, oih, lsr, flow = await __import__("asyncio").gather(
        funding_rate(symbol),
        funding_history(symbol),
        open_interest(symbol),
        oi_history(symbol),
        long_short_ratio(symbol),
        taker_flow(symbol),
    )
    mark = fr["mark_price"] if fr else None
    if oi and mark:
        oi["notional_usd"] = oi["open_interest"] * mark
    return {
        "symbol": symbol.upper(),
        "funding": fr,
        "funding_history": fh,
        "open_interest": oi,
        "oi_history": oih,
        "long_short": lsr,
        "taker_flow": flow,
    }


async def funding_history_full(symbol: str, days: int) -> list[dict]:
    """The complete funding-rate history for a symbol, paginated backwards
    from now — the F2 family's raw ingestion. 1000 rows per request, three
    settlements a day, so a 3-year pull is a handful of round trips. Each
    row: funding_time (UTC), rate as a signed decimal fraction, mark_price.
    Rows are venue truth, unparsed beyond types — provenance beats comfort."""
    import datetime as dt

    end_ms = int(dt.datetime.now(dt.UTC).timestamp() * 1000)
    start_ms = end_ms - days * 86_400_000
    out: list[dict] = []
    cursor = start_ms
    async with httpx.AsyncClient(timeout=15) as client:
        while cursor < end_ms:
            r = await client.get(
                f"{FAPI}/fapi/v1/fundingRate",
                params={"symbol": symbol.upper(), "startTime": cursor, "limit": 1000},
            )
            r.raise_for_status()
            rows = r.json()
            if not rows:
                break
            for row in rows:
                out.append({
                    "funding_time": dt.datetime.fromtimestamp(int(row["fundingTime"]) / 1000, dt.UTC),
                    "rate": float(row["fundingRate"]),
                    "mark_price": float(row.get("markPrice") or 0.0),
                })
            cursor = int(rows[-1]["fundingTime"]) + 1
            if len(rows) < 1000:
                break
    return out
