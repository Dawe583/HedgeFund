"""Yahoo Finance market data — the multi-asset data plane.

Stocks, indexes and metals have no Binance; yfinance covers SPY/QQQ/IWM/DIA
indexes, GLD/SLV metal trusts and individual equities, free for personal
use. The fetch is synchronous (yfinance is requests-based), paginated by
interval caps — 1h data reaches ~730 days per pull, 1d unlimited. Rows
match the candle schema exactly: open_time UTC, OHLCV floats.
"""

from __future__ import annotations

import datetime as dt
import logging

log = logging.getLogger(__name__)

# yfinance interval names for our internal timeframes
_TF_MAP = {"1h": "1h", "1d": "1d", "4h": "1h"}  # 4h resampled downstream from 1h


def fetch_yahoo_candles(symbol: str, timeframe: str, days: int) -> list[dict]:
    """OHLCV rows for one symbol, newest-last, matching the candle schema.
    4h bars are resampled from 1h (yfinance has no 4h); 1h data is capped
    at 730 days by Yahoo, so longer asks honestly truncate."""
    import yfinance as yf

    interval = _TF_MAP.get(timeframe)
    if interval is None:
        raise SystemExit(f"yahoo feed: timeframe {timeframe} unsupported — use 1h/1d")
    period_days = min(days, 729) if interval == "1h" else days
    ticker = yf.Ticker(symbol)
    frame = ticker.history(period=f"{period_days}d", interval=interval, auto_adjust=True)
    if frame.empty:
        raise SystemExit(f"yahoo feed: no data for {symbol} — delisted or wrong ticker")
    frame = frame.tz_convert("UTC") if frame.index.tz is not None else frame.tz_localize("UTC")

    if timeframe == "4h":
        frame = frame.resample("4h").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
        }).dropna()

    rows = []
    for ts, r in frame.iterrows():
        rows.append({
            "open_time": ts.to_pydatetime().replace(tzinfo=dt.UTC) if ts.tzinfo else ts.to_pydatetime().replace(tzinfo=dt.UTC),
            "open": float(r["Open"]),
            "high": float(r["High"]),
            "low": float(r["Low"]),
            "close": float(r["Close"]),
            "volume": float(r["Volume"]),
        })
    return rows
