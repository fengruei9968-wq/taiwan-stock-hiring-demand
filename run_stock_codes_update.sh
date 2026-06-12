#!/bin/bash
# =============================================================================
# Hiring-demand local Stock_codes updater.
# =============================================================================

set -euo pipefail

SCRIPT_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_DIR="${HIRING_SCRIPT_DIR:-$SCRIPT_SELF_DIR}"
PYTHON="${HIRING_PYTHON:-$SCRIPT_DIR/venv/bin/python3}"
LOG_FILE="$SCRIPT_DIR/launchd_stock_codes.log"
OUTPUT_DIR="${HIRING_STOCK_CODES_DIR:-$SCRIPT_DIR/data/stock_codes}"
RECEIPT_DIR="${HIRING_STOCK_CODES_RECEIPT_DIR:-$SCRIPT_DIR/data/runs/stock_codes_update}"
UPDATER_SCRIPT="$SCRIPT_DIR/stock_codes_updater.py"

mkdir -p "$(dirname "$LOG_FILE")" "$OUTPUT_DIR" "$RECEIPT_DIR"

run_python_script() {
    local script_path="$1"
    shift
    "$PYTHON" -c '
from pathlib import Path
import runpy
import sys
script = Path(sys.argv[1]).resolve()
sys.argv = [str(script)] + sys.argv[2:]
runpy.run_path(str(script), run_name="__main__")
' "$script_path" "$@"
}

{
    echo "============================================================"
    echo "Stock_codes update start: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "SCRIPT_DIR=$SCRIPT_DIR"
    echo "OUTPUT_DIR=$OUTPUT_DIR"
    echo "PYTHON=$PYTHON"
} >> "$LOG_FILE"

if [ ! -x "$PYTHON" ]; then
    echo "錯誤: Python 不存在或不可執行：$PYTHON" >> "$LOG_FILE"
    exit 1
fi

if [ ! -f "$UPDATER_SCRIPT" ]; then
    echo "錯誤: stock_codes_updater.py 不存在：$UPDATER_SCRIPT" >> "$LOG_FILE"
    exit 1
fi

run_python_script "$UPDATER_SCRIPT" \
    --output-dir "$OUTPUT_DIR" \
    --receipt-dir "$RECEIPT_DIR" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "Stock_codes update end: $(date '+%Y-%m-%d %H:%M:%S') exit=$EXIT_CODE" >> "$LOG_FILE"
exit "$EXIT_CODE"
