"""Alert egress runner — one scan-and-send pass, cron-shaped.

Usage: TRADING_ALERT_WEBHOOK_URL=https://... uv run python ../scripts/alert_egress.py
(from backend/, like every script here). Exits 0 in every configuration
including a missing URL — egress being off is a fact, not a failure.

Wiring the owner chooses (documented, not installed): the same 15-minute
launchd/GitHub-cron cadence as the paper cycle, or the deploy watcher's
sibling. One pass per tick is enough — the cursor is durable, so missed
ticks catch up rather than drop.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from trading.alerting import scan_once

if __name__ == "__main__":
    print(json.dumps(scan_once()))
