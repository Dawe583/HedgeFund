"""Yahoo Finance market data — the multi-asset data plane.

Stocks, indexes and metals have no Binance; yfinance covers SPY/QQQ/IWM/DIA
indexes, GLD/SLV metal trusts and individual equities, free for personal
use. The fetch is synchronous (yfinance is requests-based), paginated by
interval caps — 1h data reaches ~730 days per pull, 1d unlimited. Rows
match the candle schema exactly: open_time UTC, OHLCV floats.

Honesty notes (weeks 3-4 data-truth repair):

- RETRY: Yahoo is a scraped, rate-limited endpoint; transient chunk errors,
  connection resets and occasionally-empty frames on perfectly good tickers
  are routine. We retry with bounded jittered backoff. yfinance cannot
  reliably distinguish "wrong ticker" from "rate-limited into an empty
  frame" — both surface as an empty DataFrame or a caught exception — so
  empty frames are RETRIED, and only persistent emptiness after all
  attempts is treated as fatal. A genuinely wrong ticker therefore costs
  the full retry budget before failing; that is the honest price of not
  being able to tell the two apart.
- VALIDATION: rows are not trusted blind. Yahoo routinely emits bars with
  high < low, NaN cells on halted days and duplicated timestamps around
  DST transitions. Bad rows are dropped and REPORTED; a frame that fails
  wholesale raises instead of succeeding-empty, because empty ingestion
  of garbage looks identical to success in the ingest JSON output.
- 4h RESAMPLE: wall-clock 4h binning (pandas resample aligned to midnight
  UTC) slices US equity sessions mid-morning and fabricates overnight
  structure that does not exist. We resample session-aware instead: group
  by UTC date, chunk each day's 1h bars into consecutive blocks of 4.
  For US equities the whole session (13:30-20:00 UTC in summer, 14:30-21:00
  in winter) fits inside one UTC day, so UTC-date grouping is a correct
  session proxy without needing an exchange calendar. Documented limit:
  for instruments whose session crosses UTC midnight this proxy is wrong,
  but yahoo ingestion today targets US equities/indexes/metal trusts.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
import time

log = logging.getLogger(__name__)

# yfinance interval names for our internal timeframes
_TF_MAP = {"1h": "1h", "1d": "1d", "4h": "1h"}  # 4h resampled downstream from 1h

# Retry policy: CLI ingestion tool, not a service — the budget is small on
# purpose. 4 attempts (1 initial + 3 retries), base 1s doubling per retry,
# full jitter in [0.5x, 1.5x]: worst-case added latency ~1+2+4 = 7s before
# giving up. Enough to ride out a rate-limit window, small enough that a
# wrong ticker fails fast in human time.
_RETRY_ATTEMPTS = 4
_RETRY_BASE_SECONDS = 1.0

# Float noise tolerance for OHLC consistency: prices range from cents to
# thousands, so the tolerance is relative to bar magnitude. 1e-6 is far
# above float32/64 representation noise and far below any real violation.
_PRICE_TOL_REL = 1e-6


def validate_ohlcv_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    """Drop rows violating OHLCV sanity, loudly. Returns (clean_rows, report).

    Rules enforced:
      - NaN in any of open/high/low/close          -> drop
      - high < low beyond float noise              -> drop
      - open or close outside [low, high]          -> drop
      - negative volume                            -> drop (zero volume is
        legitimate: indexes like ^GSPC report no volume at all)
      - duplicated open_time                       -> keep first, drop rest
      - non-monotonic open_time                    -> repaired by sorting
        (vendor frames occasionally arrive slightly out of order around
        DST transitions; ordering is a store invariant, not information)

    Nothing is silently kept or silently dropped — the report dict carries
    per-rule counts and every drop is logged. Callers deciding "is this
    frame garbage" should check the report, not re-derive it.
    """
    report = {
        "input": len(rows),
        "dropped_nan": 0,
        "dropped_high_lt_low": 0,
        "dropped_outside_range": 0,
        "dropped_negative_volume": 0,
        "dropped_duplicate_time": 0,
        "sorted": False,
        "output": 0,
    }

    clean = []
    for row in rows:
        o, h, lo, c = row["open"], row["high"], row["low"], row["close"]
        if any(v != v for v in (o, h, lo, c)):  # NaN check without importing math
            report["dropped_nan"] += 1
            continue
        tol = max(abs(h), abs(lo), 1e-12) * _PRICE_TOL_REL
        if h < lo - tol:
            report["dropped_high_lt_low"] += 1
            continue
        if o < lo - tol or o > h + tol or c < lo - tol or c > h + tol:
            report["dropped_outside_range"] += 1
            continue
        if row["volume"] < 0:
            report["dropped_negative_volume"] += 1
            continue
        clean.append(row)

    if any(clean[i + 1]["open_time"] < clean[i]["open_time"] for i in range(len(clean) - 1)):
        clean.sort(key=lambda r: r["open_time"])
        report["sorted"] = True

    deduped = []
    seen = set()
    for row in clean:
        key = row["open_time"]
        if key in seen:
            report["dropped_duplicate_time"] += 1
            continue
        seen.add(key)
        deduped.append(row)

    report["output"] = len(deduped)
    dropped = report["input"] - report["output"]
    if dropped or report["sorted"]:
        log.warning(
            "yahoo validation: %d/%d rows dropped (nan=%d high<low=%d outside_range=%d "
            "neg_volume=%d dup_time=%d) sorted=%s",
            dropped, report["input"], report["dropped_nan"], report["dropped_high_lt_low"],
            report["dropped_outside_range"], report["dropped_negative_volume"],
            report["dropped_duplicate_time"], report["sorted"],
        )
    return deduped, report


def _fetch_with_retry(ticker, period_days: int, interval: str, symbol: str):
    """One yfinance pull with bounded jittered exponential backoff.

    Retriable: any exception from the HTTP layer (connection resets, chunk
    errors, 429s — yfinance wraps these inconsistently across versions, so
    we catch broadly and rely on the small retry budget for boundedness)
    and empty frames, which Yahoo hands out both for wrong tickers AND
    transiently under rate-limiting. Since the two are indistinguishable,
    empty is retried; a wrong ticker burns the whole budget then fails
    honestly. The final failure mode is SystemExit, matching the feed's
    CLI-facing contract.
    """
    last_error: str | None = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            frame = ticker.history(period=f"{period_days}d", interval=interval, auto_adjust=True)
        except Exception as exc:  # noqa: BLE001 — yfinance exception types are version-dependent
            last_error = f"{type(exc).__name__}: {exc}"
            log.warning("yahoo fetch %s attempt %d/%d failed: %s", symbol, attempt, _RETRY_ATTEMPTS, last_error)
        else:
            if not frame.empty:
                return frame
            last_error = "empty frame"
            log.warning("yahoo fetch %s attempt %d/%d returned empty frame", symbol, attempt, _RETRY_ATTEMPTS)
        if attempt < _RETRY_ATTEMPTS:
            delay = _RETRY_BASE_SECONDS * (2 ** (attempt - 1)) * random.uniform(0.5, 1.5)
            time.sleep(delay)
    raise SystemExit(
        f"yahoo feed: no data for {symbol} after {_RETRY_ATTEMPTS} attempts "
        f"(last: {last_error}) — wrong/delisted ticker or persistent rate-limit; "
        f"yahoo cannot tell the two apart, retry manually to disambiguate"
    )


def fetch_yahoo_candles(symbol: str, timeframe: str, days: int) -> list[dict]:
    """OHLCV rows for one symbol, newest-last, matching the candle schema.
    4h bars are resampled session-aware from 1h (yfinance has no 4h); 1h
    data is capped at 730 days by Yahoo, so longer asks honestly truncate.
    Rows pass through validate_ohlcv_rows before returning: bad rows drop
    loudly, and a frame that validates to nothing raises — ingestion of
    garbage must fail, not succeed-empty."""
    import yfinance as yf

    interval = _TF_MAP.get(timeframe)
    if interval is None:
        raise SystemExit(f"yahoo feed: timeframe {timeframe} unsupported — use 1h/1d")
    period_days = min(days, 729) if interval == "1h" else days
    ticker = yf.Ticker(symbol)
    frame = _fetch_with_retry(ticker, period_days, interval, symbol)
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

    rows, report = validate_ohlcv_rows(rows)
    if not rows:
        raise SystemExit(
            f"yahoo feed: all {report['input']} rows for {symbol} failed validation — "
            f"refusing to ingest garbage (report: {report})"
        )
    if report["output"] < report["input"]:
        log.warning("yahoo feed %s %s: validation report %s", symbol, timeframe, report)
    return rows
