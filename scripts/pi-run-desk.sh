#!/bin/bash
# Pi4 paper-desk process. The flock inside the runner is the single-book
# guarantee; this wrapper only owns environment and logging.
export PATH="/home/dawe/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd /home/dawe/HedgeFund/backend || exit 1
exec uv run python -m trading.desk.runner >> /tmp/aurelio-desk.log 2>&1
