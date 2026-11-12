#!/usr/bin/env bash
# One-click launcher for ncaa-roster-gen
cd /home/lakerh8r/ncaa-roster-gen || exit 1
# always restart to pick up latest code
pkill -f "roster-gen serve" 2>/dev/null
sleep 1
nohup .venv/bin/roster-gen serve >/tmp/ncaa-roster-gen.log 2>&1 &
for i in $(seq 1 20); do
  curl -s http://127.0.0.1:8765/ >/dev/null 2>&1 && break
  sleep 0.5
done
xdg-open http://127.0.0.1:8765 >/dev/null 2>&1 &
