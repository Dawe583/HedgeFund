"""Hyperliquid market data — public REST info + L2 order-book WebSocket stream.

No keys required. Used by the HFT-BOT order-flow pipeline (shadow mode)
and as the primary klines fallback where Binance is geo-blocked (HTTP 451,
e.g. GitHub Actions US runners).
"""

import asyncio
import datetime as dt
import json
import logging
from collections.abc import AsyncIterator

import httpx
import websockets

from trading.config import get_settings

log = logging.getLogger(__name__)

TF_MS_HL = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


async def _post_with_retry(client: httpx.AsyncClient, url: str, body: dict, attempts: int = 4):
    """POST with exponential backoff — transient timeouts must not kill backfill."""
    delay = 1.0
    for i in range(attempts):
        try:
            return await client.post(url, json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if i == attempts - 1:
                raise
            log.warning("hyperliquid chunk failed (%s), retry %d/%d", exc, i + 1, attempts - 1)
            await asyncio.sleep(delay)
            delay *= 2


async def fetch_candles(
    coin: str = "BTC",
    interval: str = "1h",
    days: int | None = None,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> list[dict]:
    """Candles from Hyperliquid candleSnapshot, paginated. Same row shape as Binance feed."""
    if interval not in TF_MS_HL:
        raise ValueError(f"unsupported interval {interval}")
    end = end or dt.datetime.now(dt.UTC)
    start = start or end - dt.timedelta(days=days or 30)
    step_ms = TF_MS_HL[interval] * 4000  # ≤5000 candles per call
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as client:
        cursor_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        while cursor_ms < end_ms:
            chunk_end = min(cursor_ms + step_ms, end_ms)
            resp = await _post_with_retry(
                client,
                f"{get_settings().hyperliquid_rest}/info",
                {
                    "type": "candleSnapshot",
                    "req": {
                        "coin": coin.upper(),
                        "interval": interval,
                        "startTime": cursor_ms,
                        "endTime": chunk_end,
                    },
                },
            )
            resp.raise_for_status()
            rows = resp.json()
            if not isinstance(rows, list):
                # error payload (e.g. {"error": ...}) instead of candle rows
                log.warning("hl candleSnapshot unexpected payload: %s", str(rows)[:200])
                break
            for r in rows:
                out.append(
                    {
                        "open_time": dt.datetime.fromtimestamp(int(r["t"]) / 1000, dt.UTC),
                        "open": float(r["o"]),
                        "high": float(r["h"]),
                        "low": float(r["l"]),
                        "close": float(r["c"]),
                        "volume": float(r.get("v", 0)),
                    }
                )
            cursor_ms = chunk_end
            await asyncio.sleep(0.2)
    # dedup + sort (overlapping windows possible)
    seen: dict[dt.datetime, dict] = {r["open_time"]: r for r in out}
    merged = [seen[k] for k in sorted(seen)]
    log.info("hl fetched %d klines %s %s", len(merged), coin, interval)
    return merged


async def all_mids() -> dict[str, float]:
    """Spot/perp mid prices keyed by coin symbol."""
    try:
        s = get_settings()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{s.hyperliquid_rest}/info", json={"type": "allMids"})
            resp.raise_for_status()
            return {k: float(v) for k, v in resp.json().items()}
    except Exception:
        log.exception("allMids failed")
        return {}


def parse_l2(msg: dict) -> dict | None:
    """Normalize an l2Book message into {ts, bids, asks} with sorted levels."""
    if msg.get("channel") != "l2Book":
        return None
    data = msg.get("data", {})
    levels = data.get("levels", [])
    if len(levels) < 2:
        return None
    try:
        bids = [(float(l["px"]), float(l["sz"])) for l in levels[0]]
        asks = [(float(l["px"]), float(l["sz"])) for l in levels[1]]
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "coin": data.get("coin"),
        "ts": data.get("time"),
        "bids": sorted(bids, reverse=True),  # best first
        "asks": sorted(asks),
    }


async def stream_book(coin: str = "BTC") -> AsyncIterator[dict]:
    """Yield normalized L2 book snapshots forever, auto-reconnecting."""
    url = "wss://api.hyperliquid.xyz/ws"
    sub = {"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}}
    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                log.info("hl l2 subscribed: %s", coin)
                async for raw in ws:
                    try:
                        book = parse_l2(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
                    if book is not None:
                        yield book
        except (websockets.ConnectionClosed, OSError) as exc:
            log.warning("hl ws dropped (%s), reconnecting in 3s", exc)
            await asyncio.sleep(3)


# ------------------------------------------------------------- order-flow math


def book_features(book: dict, depth_levels: int = 10) -> dict:
    """Microstructure features from one snapshot."""
    bids, asks = book["bids"][:depth_levels], book["asks"][:depth_levels]
    if not bids or not asks:
        return {}
    best_bid, bb_sz = bids[0]
    best_ask, ba_sz = asks[0]
    bid_depth = sum(sz for _, sz in bids)
    ask_depth = sum(sz for _, sz in asks)
    denom = bid_depth + ask_depth
    mid = (best_bid + best_ask) / 2
    # size-weighted microprice: pressure of size at the touch
    micro = (best_bid * ba_sz + best_ask * bb_sz) / max(bb_sz + ba_sz, 1e-9)
    return {
        "mid": mid,
        "spread_bps": (best_ask - best_bid) / mid * 10_000,
        "imbalance": (bid_depth - ask_depth) / denom if denom else 0.0,
        "micro_skew_bps": (micro - mid) / mid * 10_000,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
    }


class OrderFlowTracker:
    """Rolling window over book snapshots -> smoothed tradable state."""

    def __init__(self, window: int = 60):
        self.window = window
        self.imb: list[float] = []
        self.skew: list[float] = []

    def update(self, feats: dict) -> dict | None:
        self.imb.append(feats.get("imbalance", 0.0))
        self.skew.append(feats.get("micro_skew_bps", 0.0))
        if len(self.imb) > self.window:
            self.imb.pop(0)
            self.skew.pop(0)
        if len(self.imb) < self.window // 3:
            return None
        n = len(self.imb)
        imb_mean = sum(self.imb) / n
        skew_mean = sum(self.skew) / n
        return {
            "ofi_mean": round(imb_mean, 4),
            "micro_skew_mean_bps": round(skew_mean, 3),
            "pressure": round((imb_mean * 2 + skew_mean / 5) / 3, 4),
        }
