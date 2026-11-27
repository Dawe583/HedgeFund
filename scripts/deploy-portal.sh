#!/bin/bash
# Evidence-room continuous deployment, local path.
# Watches origin/main: on any new commit touching the evidence inputs,
# rebuilds the portal and ships it to Vercel. Runs under launchd every
# 10 minutes — the GitHub Action is the primary path once billing or
# repo visibility is fixed; this is the machine-local guarantee.
set -e
cd /Users/dawe/Developer/HedgeFund
git fetch origin main -q 2>/dev/null || exit 0
LOCAL=$(git rev-parse main)
REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] || git merge --ff-only origin/main -q 2>/dev/null || exit 0
STATE=/tmp/portal-deployed-sha
DEPLOYED=$(cat "$STATE" 2>/dev/null || echo none)
CURRENT=$(git rev-parse origin/main)
if [ "$DEPLOYED" != "$CURRENT" ]; then
  if git diff --name-only "$DEPLOYED" "$CURRENT" 2>/dev/null | grep -qE "^(portal/|docs/research/|backend/data/ledger_snapshot.json)" || [ "$DEPLOYED" = none ]; then
    python3 portal/build.py >/dev/null 2>&1
    VERCEL_TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/Library/Application Support/com.vercel.cli/auth.json')).get('token',''))") \
      python3 portal/deploy.py >> /tmp/portal-deploy.log 2>&1 && echo "$CURRENT" > "$STATE"
    echo "$(date -u +%H:%M) deployed $CURRENT" >> /tmp/portal-deploy.log
  else
    echo "$CURRENT" > "$STATE"
  fi
fi
