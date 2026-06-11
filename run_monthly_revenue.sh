#!/bin/bash
# =============================================================================
# 月營收 MoM%/YoY% 更新 - 包裝腳本
# 功能：從 FinMind 抓全市場月營收，計算近六月 MoM%/YoY%，存入 DB 後 push 至 Railway
# 排程：每週一 11:30 由 launchd 呼叫
# =============================================================================

HIRING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="${HIRING_PROJECT_ROOT:-$(cd "$HIRING_DIR/.." && pwd -P)}"
STAGE3_DIR="${HIRING_STAGE3_DIR:-$HIRING_DIR/stage3_web}"
PYTHON="${HIRING_REVENUE_PYTHON:-$HIRING_DIR/venv/bin/python3}"
MAIN_SCRIPT="$HIRING_DIR/fetch_monthly_revenue.py"
LOG_FILE="$HIRING_DIR/logs/launchd_revenue_run.log"
export HIRING_STAGE3_DIR="$STAGE3_DIR"
export DB_PATH="${DB_PATH:-$STAGE3_DIR/investment.db}"

# 通知（macOS + ntfy）
TOOLS_DIR="$PROJECT_ROOT"
NOTIFY_PYTHON="$TOOLS_DIR/stage0_download/venv/bin/python3"

notify() {
    local title="$1"
    local message="$2"
    osascript -e "display notification \"$message\" with title \"$title\" sound name \"default\"" 2>/dev/null || true
    if [ -f "$NOTIFY_PYTHON" ]; then
        cd "$TOOLS_DIR"
        "$NOTIFY_PYTHON" -c "
import sys; sys.path.insert(0, '.')
from tools.notify import send_notification
send_notification('$title', '$message', channels=['ntfy'])
" 2>/dev/null || true
    fi
}

mkdir -p "$HIRING_DIR/logs"
echo "========================================" >> "$LOG_FILE"
echo "執行時間: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"

# 環境檢查
if [ ! -d "$PROJECT_ROOT" ]; then
    echo "錯誤: 正式專案根目錄不存在：$PROJECT_ROOT" >> "$LOG_FILE"
    notify "月營收更新失敗" "正式專案根目錄不存在"; exit 1
fi
if [ ! -f "$PYTHON" ]; then
    echo "錯誤: venv 不存在：$PYTHON" >> "$LOG_FILE"
    notify "月營收更新失敗" "venv 不存在"; exit 1
fi
if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "錯誤: 主程式不存在：$MAIN_SCRIPT" >> "$LOG_FILE"
    notify "月營收更新失敗" "主程式不存在"; exit 1
fi
if [ ! -f "$DB_PATH" ]; then
    echo "錯誤: DB 不存在：$DB_PATH" >> "$LOG_FILE"
    notify "月營收更新失敗" "investment.db 不存在"; exit 1
fi

# 讀取 FINMIND_TOKEN
ENV_FILE="$STAGE3_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep FINMIND_TOKEN | xargs) 2>/dev/null || true
fi
if [ -z "$FINMIND_TOKEN" ]; then
    echo "錯誤: 找不到 FINMIND_TOKEN" >> "$LOG_FILE"
    notify "月營收更新失敗" "找不到 FINMIND_TOKEN"; exit 1
fi

echo "環境檢查通過，開始執行..." >> "$LOG_FILE"
cd "$HIRING_DIR"

# Step 1: 上市/上櫃月營收（FinMind）
echo "--- Step 1: FinMind 上市/上櫃 ---" >> "$LOG_FILE"
"$PYTHON" "$MAIN_SCRIPT" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "FinMind 執行失敗，exit code: $EXIT_CODE" >> "$LOG_FILE"
    notify "月營收更新失敗" "fetch_monthly_revenue.py 異常終止 (exit code: $EXIT_CODE)"
    exit $EXIT_CODE
fi

# Step 2: 興櫃月營收（MoneyDJ）
EMERGING_SCRIPT="$HIRING_DIR/fetch_emerging_revenue.py"
if [ -f "$EMERGING_SCRIPT" ]; then
    echo "--- Step 2: MoneyDJ 興櫃 ---" >> "$LOG_FILE"
    "$PYTHON" "$EMERGING_SCRIPT" >> "$LOG_FILE" 2>&1
    EXIT_CODE2=$?
    if [ $EXIT_CODE2 -ne 0 ]; then
        echo "MoneyDJ 興櫃執行失敗，exit code: $EXIT_CODE2（不中斷流程）" >> "$LOG_FILE"
    fi
fi

echo "完成" >> "$LOG_FILE"
notify "月營收更新完成" "上市/上櫃+興櫃 MoM%/YoY% 已更新並部署至外網"
echo "" >> "$LOG_FILE"
exit 0
