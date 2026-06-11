#!/bin/bash
# =============================================================================
# 歷史參考檔案（2026-06-11 移入 docs/history）
# 狀態：非 active truth，不可直接用於正式執行、排程、deploy 或 Git 操作。
# 原因：此舊版 wrapper 含本機 D 槽絕對路徑，且含舊式 DB commit/push 流程。
# 現行 wrapper 以 repo root 的 run_hiring_demand.sh 為準；Git / Railway
# 發布邊界以 manifests/first_commit_scope_20260611.yaml 與
# check_release_readiness.py / check_hiring_deploy_boundary.py 為準。
# =============================================================================
# =============================================================================
# 徵人需求度更新 - 包裝腳本
# 功能：檢查執行環境是否就緒，若無法執行則跳出 macOS + ntfy 雙通道通知
# 排程：每天 11:30 由 launchd 呼叫
# =============================================================================

SCRIPT_DIR="/Users/chiufengjui/D槽/Python/台股子公司投資資訊擷取與展示/上市櫃公司徵人需求度"
PYTHON="$SCRIPT_DIR/venv/bin/python3"
MAIN_SCRIPT="$SCRIPT_DIR/fetch_hiring_demand.py"
LOG_FILE="$SCRIPT_DIR/launchd_run.log"

# 雙通道通知（macOS + ntfy）
TOOLS_DIR="/Users/chiufengjui/D槽/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案"
NOTIFY_PYTHON="$TOOLS_DIR/stage0_download/venv/bin/python3"

notify() {
    local title="$1"
    local message="$2"
    # macOS 本機通知
    osascript -e "display notification \"$message\" with title \"$title\" sound name \"default\"" 2>/dev/null || true
    # ntfy 手機通知
    if [ -f "$NOTIFY_PYTHON" ]; then
        cd "$TOOLS_DIR"
        "$NOTIFY_PYTHON" -c "
import sys; sys.path.insert(0, '.')
from tools.notify import send_notification
send_notification('$title', '$message', channels=['ntfy'])
" 2>/dev/null || true
    fi
}

# 記錄時間
echo "========================================" >> "$LOG_FILE"
echo "執行時間: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"

# 檢查 1：程式根目錄是否存在
if [ ! -d "/Users/chiufengjui/D槽/Python" ]; then
    MSG="Python 根目錄不存在：/Users/chiufengjui/D槽/Python"
    echo "錯誤: $MSG" >> "$LOG_FILE"
    notify "徵人需求度更新失敗" "$MSG"
    exit 1
fi

# 檢查 2：程式目錄是否存在
if [ ! -d "$SCRIPT_DIR" ]; then
    MSG="程式目錄不存在：$SCRIPT_DIR"
    echo "錯誤: $MSG" >> "$LOG_FILE"
    notify "徵人需求度更新失敗" "$MSG"
    exit 1
fi

# 檢查 3：Python venv 是否存在
if [ ! -f "$PYTHON" ]; then
    MSG="Python 虛擬環境不存在：$PYTHON"
    echo "錯誤: $MSG" >> "$LOG_FILE"
    notify "徵人需求度更新失敗" "$MSG"
    exit 1
fi

# 檢查 4：主程式是否存在
if [ ! -f "$MAIN_SCRIPT" ]; then
    MSG="主程式不存在：$MAIN_SCRIPT"
    echo "錯誤: $MSG" >> "$LOG_FILE"
    notify "徵人需求度更新失敗" "$MSG"
    exit 1
fi

# 檢查 5：是否有網路連線（ping 104.com.tw）
if ! ping -c 1 -W 5 www.104.com.tw > /dev/null 2>&1; then
    MSG="無法連線到 104 人力銀行，請檢查網路"
    echo "錯誤: $MSG" >> "$LOG_FILE"
    notify "徵人需求度更新失敗" "$MSG"
    exit 1
fi

# 一切就緒，執行主程式
echo "環境檢查通過，開始執行..." >> "$LOG_FILE"
cd "$SCRIPT_DIR"
"$PYTHON" "$MAIN_SCRIPT" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "主程式執行失敗，exit code: $EXIT_CODE" >> "$LOG_FILE"
    # 主程式內已有 send_notification，這裡不重複通知
    # 但如果 Python 本身 crash（非程式邏輯錯誤），補發通知
    if [ $EXIT_CODE -gt 1 ]; then
        notify "徵人需求度更新失敗" "Python 程式異常終止 (exit code: $EXIT_CODE)"
    fi
fi

echo "完成 (exit code: $EXIT_CODE)" >> "$LOG_FILE"

# 爬蟲成功後，自動 commit investment.db 並 push 到 Railway
if [ $EXIT_CODE -eq 0 ]; then
    echo "--- 開始自動部署至 Railway ---" >> "$LOG_FILE"
    STAGE3_DIR="/Users/chiufengjui/D槽/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/stage3_web"
    GIT="/usr/bin/git"
    TODAY=$(date '+%Y/%m/%d %H:%M')

    cd "$STAGE3_DIR"
    "$GIT" add data/investment.db >> "$LOG_FILE" 2>&1
    "$GIT" commit -m "chore: 自動更新徵人需求度資料 ${TODAY}" >> "$LOG_FILE" 2>&1
    PUSH_EXIT=$?

    # 若沒有變動（nothing to commit）也算正常
    "$GIT" push origin main >> "$LOG_FILE" 2>&1
    PUSH_EXIT=$?

    if [ $PUSH_EXIT -eq 0 ]; then
        echo "Railway 部署成功 (${TODAY})" >> "$LOG_FILE"
        notify "徵人需求度更新完成" "資料已自動部署至外網 ${TODAY}"
    else
        echo "Railway push 失敗，exit code: $PUSH_EXIT" >> "$LOG_FILE"
        notify "徵人需求度部署失敗" "爬蟲成功但 git push 失敗，請手動確認"
    fi
fi

echo "" >> "$LOG_FILE"
exit $EXIT_CODE
