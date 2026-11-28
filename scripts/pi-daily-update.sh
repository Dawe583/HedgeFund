#!/bin/bash
# Pi4 daily update: pull main, refresh python deps, rebuild the frontend,
# restart the app, then refresh the data plane's freshness — in that order,
# because the ingest code itself is what the pull updates.
# Runs from cron at 04:10 local; idempotent; every failure is loud in the log.
set -x
export PATH="/home/dawe/.local/bin:/usr/local/bin:/usr/bin:/bin"
LOG=/tmp/pi-daily-update.log
exec >> "$LOG" 2>&1
echo "=== $(date -u '+%Y-%m-%d %H:%M UTC') update pass ==="

cd /home/dawe/HedgeFund || exit 1
git fetch origin main -q || exit 1
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
  git merge --ff-only origin/main -q && CHANGED=1 || { echo "ff merge failed"; exit 1; }
else
  CHANGED=0
fi
echo "code: $LOCAL -> $REMOTE (changed=$CHANGED)"

cd /home/dawe/HedgeFund/backend
uv sync -q

if [ "$CHANGED" = 1 ]; then
  cd /home/dawe/HedgeFund/frontend
  npm install --no-audit --no-fund -s
  npm run build
  pkill -f "uvicorn app.main:app" || true   # watchdog restarts it within a minute
  echo "app restarted for new build"
fi

# data freshness: the Pi's own tape, refreshed daily — hourly is the Mac's job,
# the Pi serves the dashboard and keeps its tape no older than a day.
cd /home/dawe/HedgeFund/backend
for sym in BTCUSDT ETHUSDT SOLUSDT; do
  for tf in 1h 4h; do
    timeout 240 uv run python -m trading.research ingest --symbol $sym --timeframe $tf --days 7
  done
done
for sym in GLD SLV SPY TLT; do
  timeout 200 uv run python -m trading.research ingest-yahoo --symbol $sym --timeframe 1h --days 10
  timeout 200 uv run python -m trading.research ingest-yahoo --symbol $sym --timeframe 1d --days 10
done
echo "=== pass done ==="
