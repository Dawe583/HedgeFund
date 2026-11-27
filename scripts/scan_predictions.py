#!/usr/bin/env python3
"""Scan + score the ML prediction track record — one pass, then exit.

The F-7 instrument's writer: reads every precomputed ML artifact on disk
(frozen F9 pickles, rolling F12 series), scores each one's latest state,
commits new rows into the platform database's predictions table, then
backfills outcomes for predictions whose horizon has elapsed against the
research candle store. Both passes are idempotent — run it as often as
you like; a re-scan of the same bar is the same measurement, not a new
row, and a scored prediction is never rescored.

This process TRAINS NOTHING. Artifacts are files the offline research
pipeline wrote; if an artifact is absent the series is skipped and the
report says so. Serving-path retraining is the exact failure the artifact
discipline exists to prevent — the scanner inherits it absolutely.

Usage (from backend/):

    uv run python ../scripts/scan_predictions.py
    uv run python ../scripts/scan_predictions.py --verbose

Databases follow the repo's own defaults: candles are read from
backend/data/research.db (replaceable market data), predictions are
written to backend/data.db (the platform database the API serves).
Override either with --research-db / --app-db for a throwaway run.

Wiring for the owner — the instrument only works if it runs on a cadence:

- cron (any POSIX box, hourly is the natural grid for 1h artifacts):

      15 * * * * cd /path/to/HedgeFund/backend && uv run python ../scripts/scan_predictions.py >> data/predictions_scan.log 2>&1

  The 15-minute offset puts the scan after the hour's bar close plus
  ingestion slack; ingest must run first, because a scan on a stale tape
  measures the same bar twice and inserts nothing — harmless, but silent.

- launchd (macOS): a ~/Library/LaunchAgents plist with
  StartCalendarInterval Minute 15, ProgramArguments pointing at the same
  `uv run` line, StandardOutPath/StandardErrorPath at the log above. Write
  it once, `launchctl bootstrap gui/$(id -u) <plist>`, forget it. (This
  script deliberately does not write that file — system wiring is the
  owner's act, not a script's.)

The scan's own report goes to stdout as JSON: what was found, what was
inserted, what was skipped and why — the scanner's provenance rides with
the track record it writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

DEFAULT_RESEARCH_DB = f"sqlite:///{_BACKEND_DIR / 'data' / 'research.db'}"
DEFAULT_APP_DB = f"sqlite:///{_BACKEND_DIR / 'data.db'}"


def main() -> int:
    parser = argparse.ArgumentParser(description="scan + score the ML prediction track record")
    parser.add_argument("--research-db", default=DEFAULT_RESEARCH_DB, help="candle store (read-only use)")
    parser.add_argument("--app-db", default=DEFAULT_APP_DB, help="platform database the predictions table lives in")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    import logging

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    from trading.models import init_schema, make_engine
    from trading.predictions import scan_predictions, score_predictions

    # The scanner is a writer, so it owns schema creation here — same
    # discipline as the ingest CLI and the paper engine. On the platform
    # database Alembic's lineage creates the same table first and
    # create_all is a no-op; on a throwaway database this is what makes a
    # verification run possible at all.
    app_engine = make_engine(args.app_db)
    init_schema(app_engine)
    try:
        scan_report = scan_predictions(args.research_db, app_engine)
        score_report = score_predictions(args.research_db, app_engine)
    finally:
        app_engine.dispose()

    print(json.dumps({"scan": scan_report, "score": score_report}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
