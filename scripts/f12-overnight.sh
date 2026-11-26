#!/bin/bash
# F12 overnight measurement — everything sequential, no CPU contention.
# Launch: nohup scripts/f12-overnight.sh > /tmp/f12-overnight.log 2>&1 &
# Stages: phase A sweep -> persistence -> phase B on leaders -> verdict row.
# Every artifact file-caches, so a restart resumes instead of recomputing.

cd /Users/dawe/Developer/HedgeFund/backend || exit 1
LOG() { echo "[$(date -u +%H:%M:%S)] $1"; }

LOG "stage 1/4: F12 phase A sweep (8 cells, caches warm up here)"
uv run python -m trading.sweep --family F12 --phase A --jobs 2 >> /tmp/f12-sweep.log 2>&1
LOG "phase A done"

LOG "stage 2/4: persistence measurement (uses the warm caches)"
PYTHONPATH=. uv run python ../scripts/rolling_persistence_one.py 2000 24 >> /tmp/rolling-persistence.log 2>&1
PYTHONPATH=. uv run python ../scripts/rolling_persistence_one.py 2000 48 >> /tmp/rolling-persistence.log 2>&1
PYTHONPATH=. uv run python ../scripts/rolling_persistence_one.py 4000 24 >> /tmp/rolling-persistence.log 2>&1
PYTHONPATH=. uv run python ../scripts/rolling_persistence_one.py 4000 48 >> /tmp/rolling-persistence.log 2>&1
LOG "persistence done"

LOG "stage 3/4: phase B on the grid (the regime-boundary test)"
uv run python -m trading.sweep --family F12 --phase B --jobs 2 >> /tmp/f12-sweep-b.log 2>&1
LOG "phase B done"

LOG "stage 4/4: equity persistence"
PYTHONPATH=. uv run python ../scripts/rolling_persistence_equity.py >> /tmp/rolling-persistence-equity.log 2>&1
LOG "F12-OVERNIGHT-DONE"
