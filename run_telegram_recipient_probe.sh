#!/bin/bash
# =============================================================================
# Telegram recipient probe - hourly wrapper
# 功能：讀取 Telegram /start updates，更新本機 ignored telegram_recipients.json
# 邊界：不發 PNG、不送 Telegram 訊息、不跑徵人需求度爬蟲、不部署
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="${HIRING_PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd -P)}"
PYTHON="${HIRING_PYTHON:-$SCRIPT_DIR/venv/bin/python3}"
PROBE_SCRIPT="$SCRIPT_DIR/telegram_recipient_probe.py"
RECIPIENTS_PATH="$SCRIPT_DIR/telegram_recipients.json"
LOG_FILE="$SCRIPT_DIR/launchd_telegram_probe.log"

echo "========================================" >> "$LOG_FILE"
echo "執行時間: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "模式: hourly recipient probe only" >> "$LOG_FILE"

if [ ! -d "$SCRIPT_DIR" ]; then
    echo "錯誤: 程式目錄不存在：$SCRIPT_DIR" >> "$LOG_FILE"
    exit 1
fi

if [ ! -f "$PYTHON" ]; then
    echo "錯誤: Python venv 不存在：$PYTHON" >> "$LOG_FILE"
    exit 1
fi

if [ ! -f "$PROBE_SCRIPT" ]; then
    echo "錯誤: probe script 不存在：$PROBE_SCRIPT" >> "$LOG_FILE"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "錯誤: .env 不存在，無法讀取 TELEGRAM_BOT_TOKEN" >> "$LOG_FILE"
    exit 1
fi

OUT_DIR="$SCRIPT_DIR/data/runs/telegram_recipient_probe_hourly_$(date '+%Y%m%d_%H%M%S')"
RECEIPT_PATH="$OUT_DIR/telegram_recipient_probe_receipt_$(date '+%Y%m%d_%H%M%S').json"
mkdir -p "$OUT_DIR"

cd "$SCRIPT_DIR"
"$PYTHON" "$PROBE_SCRIPT" \
    --env-path "$SCRIPT_DIR/.env" \
    --recipients-path "$RECIPIENTS_PATH" \
    --output-receipt "$RECEIPT_PATH" \
    --timeout-seconds "${HIRING_TELEGRAM_PROBE_TIMEOUT_SECONDS:-30}" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "telegram recipient probe 失敗，exit code: $EXIT_CODE" >> "$LOG_FILE"
    exit $EXIT_CODE
fi

echo "telegram recipient probe PASS: $OUT_DIR" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
exit 0
