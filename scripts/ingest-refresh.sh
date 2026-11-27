#!/bin/bash
# hourly freshness refresh — the validation plane measures the present,
# never a tape that froze when somebody remembered to run ingest by hand.
cd /Users/dawe/Developer/HedgeFund/backend || exit 1
for sym in BTCUSDT ETHUSDT SOLUSDT; do
  for tf in 1h 4h; do
    timeout 240 uv run python -m trading.research ingest --symbol $sym --timeframe $tf --days 7 >> /tmp/ingest-refresh.log 2>&1
  done
done
for sym in GLD SLV SPY TLT; do
  timeout 200 uv run python -m trading.research ingest-yahoo --symbol $sym --timeframe 1h --days 10 >> /tmp/ingest-refresh.log 2>&1
  timeout 200 uv run python -m trading.research ingest-yahoo --symbol $sym --timeframe 1d --days 10 >> /tmp/ingest-refresh.log 2>&1
done
echo "[$(date -u +%H:%M)] refresh pass done" >> /tmp/ingest-refresh.log
