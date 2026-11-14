#!/usr/bin/env bash
# One-click launcher for ncaa-roster-gen
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

if [ ! -x .venv/bin/roster-gen ]; then
  echo "First run: installing dependencies..."
  "$DIR/setup.sh" || { echo "Setup failed."; exit 1; }
fi

# always restart to pick up latest code
pkill -f "roster-gen serve" 2>/dev/null
sleep 1
LOG="${XDG_CACHE_HOME:-$HOME/.cache}/ncaa-roster-gen/server.log"
mkdir -p "$(dirname "$LOG")"
nohup .venv/bin/roster-gen serve >"$LOG" 2>&1 &
for i in $(seq 1 40); do
  curl -s http://127.0.0.1:8765/ >/dev/null 2>&1 && break
  sleep 0.5
done
xdg-open http://127.0.0.1:8765 >/dev/null 2>&1 &
echo "NCAA Football 14 Roster Generator: http://127.0.0.1:8765"
echo "Server log: $LOG"
