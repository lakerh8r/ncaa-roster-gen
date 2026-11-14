#!/usr/bin/env bash
# Install ncaa-roster-gen: Python deps + app-menu entry. Run once.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3.11+ is required but 'python3' was not found." >&2
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Python 3.11 or newer is required." >&2
  exit 1
fi

echo "Creating virtual environment..."
if command -v uv >/dev/null 2>&1; then
  uv venv .venv --python "$PY"
  echo "Installing dependencies..."
  uv pip install -e .
else
  "$PY" -m venv .venv
  echo "Installing dependencies..."
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/pip install -e .
fi

chmod +x "$DIR/launch.sh" "$DIR/setup.sh"

# Add an app-menu shortcut on Linux.
if command -v update-desktop-database >/dev/null 2>&1 || [ -d "$HOME/.local/share/applications" ]; then
  APPS="$HOME/.local/share/applications"
  mkdir -p "$APPS"
  cat > "$APPS/ncaa-roster-gen.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=NCAA Football 14 Roster Generator
Comment=Generate NCAA Football 14 roster saves from ESPN data
Exec=$DIR/launch.sh
Path=$DIR
Icon=applications-games
Terminal=false
Categories=Game;Utility;
EOF
  chmod +x "$APPS/ncaa-roster-gen.desktop"
  update-desktop-database "$APPS" >/dev/null 2>&1 || true
  echo "Added 'NCAA Football 14 Roster Generator' to your app menu."
fi

echo
echo "Setup complete."
echo "Launch it with: $DIR/launch.sh"
