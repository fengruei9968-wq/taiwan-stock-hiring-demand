#!/bin/bash
# =============================================================================
# Stock monthly revenue raw updater
# - Reads the latest Stock_codes CSV
# - Fetches MOPS monthly revenue from 2021-01 to the previous complete month by default
# - Listed / OTC use MOPS CSV with FinMind fallback for missing months
# - Emerging uses MOPS rotc CSV with rotc HTML fallback
# - Writes stage3_web/investment.db table stock_monthly_revenue and dated CSV/receipt
# =============================================================================

set -euo pipefail

HIRING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="${HIRING_PROJECT_ROOT:-$(cd "$HIRING_DIR/.." && pwd -P)}"
STAGE3_DIR="${HIRING_STAGE3_DIR:-$HIRING_DIR/stage3_web}"
PYTHON="${HIRING_REVENUE_PYTHON:-$HIRING_DIR/venv/bin/python3}"
SCRIPT="$HIRING_DIR/fetch_stock_monthly_revenue_raw.py"
LOG_FILE="$HIRING_DIR/logs/stock_monthly_revenue_raw_run.log"

export HIRING_STAGE3_DIR="$STAGE3_DIR"
export DB_PATH="${DB_PATH:-$STAGE3_DIR/investment.db}"
export STOCK_CODES_DIR="${STOCK_CODES_DIR:-$(cd "$PROJECT_ROOT/.." && pwd -P)/台股上市櫃公司名稱確認與自動定時更新/Stock_codes}"
export RAW_MONTHLY_REVENUE_SKIP_GIT="${RAW_MONTHLY_REVENUE_SKIP_GIT:-1}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

mkdir -p "$HIRING_DIR/logs"
echo "========================================" >> "$LOG_FILE"
echo "執行時間: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "RAW_MONTHLY_REVENUE_SKIP_GIT=$RAW_MONTHLY_REVENUE_SKIP_GIT" >> "$LOG_FILE"

if [ ! -x "$PYTHON" ]; then
    echo "錯誤: Python 不存在：$PYTHON" >> "$LOG_FILE"
    exit 1
fi
if [ ! -f "$SCRIPT" ]; then
    echo "錯誤: 主程式不存在：$SCRIPT" >> "$LOG_FILE"
    exit 1
fi
if [ ! -f "$DB_PATH" ]; then
    echo "錯誤: DB 不存在：$DB_PATH" >> "$LOG_FILE"
    exit 1
fi

ENV_FILE="$STAGE3_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep FINMIND_TOKEN | xargs) 2>/dev/null || true
fi

START_MONTH="${RAW_REVENUE_START_MONTH:-2021-01}"
DEFAULT_END_MONTH="$("$PYTHON" - <<'PY'
from datetime import date

today = date.today()
year = today.year
month = today.month - 1
if month == 0:
    year -= 1
    month = 12
print(f"{year:04d}-{month:02d}")
PY
)"
END_MONTH="${RAW_REVENUE_END_MONTH:-$DEFAULT_END_MONTH}"
MARKET_TYPES="${RAW_REVENUE_MARKET_TYPES:-上市,上櫃,興櫃}"
RAW_REVENUE_MISSING_ONLY="${RAW_REVENUE_MISSING_ONLY:-0}"

EXTRA_ARGS=()
if [ "$RAW_REVENUE_MISSING_ONLY" = "1" ]; then
    EXTRA_ARGS+=("--missing-only")
fi

cd "$HIRING_DIR"
"$PYTHON" "$SCRIPT" \
    --start-month "$START_MONTH" \
    --end-month "$END_MONTH" \
    --market-types "$MARKET_TYPES" \
    "${EXTRA_ARGS[@]}" \
    "$@" >> "$LOG_FILE" 2>&1

echo "完成" >> "$LOG_FILE"
