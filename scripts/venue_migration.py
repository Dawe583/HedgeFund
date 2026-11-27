"""Venue row-labelling migration for the research candle store (analysis F-3).

Rows written before the venue schema carry venue=''. This script assigns
their instrument identity by EVIDENCE, never by assumption:

- Crypto series (…USDT) are verified against Binance's own tapes: three
  full sampled days (first/middle/last of the series) are re-fetched from
  the spot API and compared exactly — rows that came from Binance match to
  the last decimal because they ARE Binance numbers. A series matching
  >=95% of sampled bars is labelled binance/spot. Failing that, the same
  comparison runs against the USD-M perp API (binance-usdm/perp). Failing
  both, the series is labelled unknown — the honest answer when the tape's
  origin cannot be proven (the Hyperliquid fallback leaves no signature we
  can verify without a Hyperliquid reference fetch, so a double mismatch
  means 'not Binance', not 'proven Hyperliquid').
- Yahoo series (equities/ETFs) need no verification: Yahoo is the only
  ingestion path that ever wrote them.

Sampling caveat, declared: verification covers the sampled days exactly;
rows inside unsampled windows inherit the series label. The alternative —
re-fetching three years per series — costs the same as re-ingestion, and
the unlabelled rows are legacy evidence either way: new measurements run
on venue-explicit series, these rows are the past.

Usage:
    python3 scripts/venue_migration.py [--db backend/data/research.db] [--apply]

Without --apply the script only reports what it would label. NEVER run
against data.db — the guard refuses.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import shutil
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

TF_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def _day_window(center_epoch_ms: int, tf_ms: int) -> tuple[int, int]:
    """One full day of grid slots around a center timestamp."""
    day_ms = 86_400_000
    start = center_epoch_ms - day_ms // 2
    return start, start + day_ms + tf_ms  # inclusive-ish end: a full day's worth of bars


async def _verify_series(symbol: str, timeframe: str, first_ms: int, last_ms: int, stored: dict[int, float]) -> dict:
    """Compare stored closes with Binance spot (then perp) over three sampled days."""
    from trading.feeds.binance import fetch_klines

    tf_ms = TF_MS[timeframe]
    samples = [first_ms, (first_ms + last_ms) // 2, last_ms - tf_ms]
    result = {}
    for market in ("spot", "perp"):
        matched = total = 0
        for center in samples:
            start_ms, end_ms = _day_window(center, tf_ms)
            try:
                rows = await fetch_klines(
                    symbol, timeframe,
                    start=dt.datetime.fromtimestamp(start_ms / 1000, dt.UTC),
                    end=dt.datetime.fromtimestamp(end_ms / 1000, dt.UTC),
                    market=market,
                )
            except Exception as exc:  # noqa: BLE001 — a failed fetch is no evidence either way
                print(json.dumps({"event": "verify_fetch_failed", "symbol": symbol, "timeframe": timeframe,
                                  "market": market, "error": str(exc)[:120]}))
                continue
            for r in rows:
                key = int(r["open_time"].timestamp() * 1000)
                if key in stored:
                    total += 1
                    if abs(stored[key] - r["close"]) <= abs(r["close"]) * 1e-9:
                        matched += 1
        result[market] = {"matched": matched, "total": total, "rate": matched / total if total else 0.0}
        if total and matched / total >= 0.95:
            break  # strong match — no need to test the other tape
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "backend" / "data" / "research.db"))
    ap.add_argument("--apply", action="store_true", help="write the labels — without it, report only")
    args = ap.parse_args()

    db_path = Path(args.db)
    if db_path.name == "data.db":
        raise SystemExit("refusing: data.db is the owner's financial data, never a migration target")
    if not db_path.exists():
        raise SystemExit(f"no database at {db_path}")

    # schema first: columns + index rebuild through the same guard every writer uses
    from trading.models import init_schema, make_engine
    engine = make_engine(f"sqlite:///{db_path}")
    init_schema(engine)
    engine.dispose()

    conn = sqlite3.connect(str(db_path))
    series = conn.execute(
        "SELECT symbol, timeframe, COUNT(*), MIN(open_time), MAX(open_time) FROM candles"
        " WHERE venue = '' OR venue IS NULL GROUP BY symbol, timeframe ORDER BY symbol, timeframe"
    ).fetchall()
    print(json.dumps({"event": "unlabelled_series", "count": len(series)}))

    report = []
    for symbol, timeframe, n, first, last in series:
        is_crypto = symbol.upper().endswith("USDT")
        label = {"symbol": symbol, "timeframe": timeframe, "rows": n}
        if not is_crypto:
            label.update(venue="yahoo", instrument_type="equity", evidence="yahoo is the only ingestion path for this symbol")
        else:
            # stored closes keyed by epoch-ms for exact comparison; open_time
            # is stored as a sqlite datetime string — julianday math converts
            rows = conn.execute(
                "SELECT CAST((julianday(open_time) - 2440587.5) * 86400000 AS INTEGER), close"
                " FROM candles WHERE symbol = ? AND timeframe = ? AND (venue = '' OR venue IS NULL)",
                (symbol, timeframe),
            ).fetchall()
            stored = {int(r[0]): float(r[1]) for r in rows}
            tf_ms = TF_MS.get(timeframe)
            if tf_ms is None:
                label.update(venue="unknown", instrument_type="", evidence=f"timeframe {timeframe} has no grid mapping")
                report.append(label)
                continue
            first_ms = int((dt.datetime.fromisoformat(str(first).replace(" ", "T")).replace(tzinfo=dt.UTC)).timestamp() * 1000) if first else 0
            last_ms = int((dt.datetime.fromisoformat(str(last).replace(" ", "T")).replace(tzinfo=dt.UTC)).timestamp() * 1000) if last else 0
            verification = asyncio.run(_verify_series(symbol, timeframe, first_ms, last_ms, stored))
            label["verification"] = verification
            spot_rate = verification.get("spot", {}).get("rate", 0.0)
            perp_rate = verification.get("perp", {}).get("rate", 0.0)
            if spot_rate >= 0.95:
                label.update(venue="binance", instrument_type="spot",
                             evidence=f"{spot_rate:.2%} exact close matches over sampled days vs spot API")
            elif perp_rate >= 0.95:
                label.update(venue="binance-usdm", instrument_type="perp",
                             evidence=f"{perp_rate:.2%} exact close matches over sampled days vs perp API")
            else:
                label.update(venue="unknown", instrument_type="",
                             evidence=f"no Binance tape matches (spot {spot_rate:.1%}, perp {perp_rate:.1%}) — origin unproven")
        report.append(label)
        print(json.dumps({"event": "labelled", **{k: v for k, v in label.items() if k != "verification"},
                          "spot_rate": label.get("verification", {}).get("spot", {}).get("rate"),
                          "perp_rate": label.get("verification", {}).get("perp", {}).get("rate")}))

    if args.apply:
        backup = db_path.with_suffix(f".bak-{dt.datetime.now(dt.UTC).strftime('%Y%m%d-%H%M%S')}-venue-migration")
        shutil.copy2(db_path, backup)
        print(json.dumps({"event": "backup", "path": str(backup)}))
        for label in report:
            conn.execute(
                "UPDATE candles SET venue = ?, instrument_type = ? WHERE symbol = ? AND timeframe = ? AND (venue = '' OR venue IS NULL)",
                (label["venue"], label["instrument_type"], label["symbol"], label["timeframe"]),
            )
        conn.commit()
        print(json.dumps({"event": "applied", "series": len(report)}))
    else:
        print(json.dumps({"event": "dry_run", "note": "re-run with --apply to write labels"}))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
