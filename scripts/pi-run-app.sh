#!/bin/bash
# Pi4 service entry: the dashboard process. Runs under cron @reboot, restarts
# on failure via cron watchdog — systemd needs sudo, cron does not, and a Pi
# reboots rarely enough that @reboot + watchdog is the same guarantee.
# Port 5830: the user's choice, nothing else on the Pi competes for it.
export PATH="/home/dawe/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd /home/dawe/HedgeFund/backend || exit 1
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 5830 --no-access-log \
  >> /tmp/aurelio-pi.log 2>&1
