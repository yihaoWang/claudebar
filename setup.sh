#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.claudebar.usage"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
LOG_DIR="$HOME/Library/Logs/claudebar"

# 1. Setup virtual environment and install dependencies
echo "==> Setting up virtual environment..."
cd "$SCRIPT_DIR"
if command -v uv &> /dev/null; then
    if [ ! -d ".venv" ]; then
        uv venv
    fi
    uv pip install --python .venv -r requirements.txt
else
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

# 2. Determine paths
PYTHON_PATH="$SCRIPT_DIR/.venv/bin/python"
SCRIPT_PATH="$SCRIPT_DIR/claude_usage.py"

echo "==> Python: $PYTHON_PATH"
echo "==> Script: $SCRIPT_PATH"

# 3. Create log directory
mkdir -p "$LOG_DIR"

# 4. Generate plist with actual paths
sed \
    -e "s|__PYTHON_PATH__|$PYTHON_PATH|g" \
    -e "s|__SCRIPT_PATH__|$SCRIPT_PATH|g" \
    -e "s|__LOG_DIR__|$LOG_DIR|g" \
    "$PLIST_SRC" > "$PLIST_DST"

# 5. Unload old agent if exists, then load new one
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "==> Done! claudebar is now installed and will start on login."
echo "    Logs: $LOG_DIR/"
echo "    To uninstall: launchctl unload $PLIST_DST && rm $PLIST_DST"
