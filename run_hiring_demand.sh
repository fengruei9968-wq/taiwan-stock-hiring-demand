#!/bin/bash
# =============================================================================
# 徵人需求度更新 - 包裝腳本
# 功能：檢查執行環境是否就緒，若無法執行則跳出 macOS + ntfy 雙通道通知
# 排程：每天 11:30 由 launchd 呼叫
# =============================================================================

SCRIPT_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_DIR="${HIRING_SCRIPT_DIR:-$SCRIPT_SELF_DIR}"
PROJECT_ROOT="${HIRING_PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd -P)}"
PYTHON="${HIRING_PYTHON:-$SCRIPT_DIR/venv/bin/python3}"
MAIN_SCRIPT="$SCRIPT_DIR/fetch_hiring_demand.py"
PROBE_SCRIPT="$SCRIPT_DIR/probe_104_search_api.py"
CHECKER_SCRIPT="$SCRIPT_DIR/check_hiring_demand_run.py"
REPORT_SCRIPT="$SCRIPT_DIR/generate_unlimited_hiring_revenue_report.py"
REPORT_CHECKER_SCRIPT="$SCRIPT_DIR/check_unlimited_hiring_revenue_report.py"
REPORT_RENDER_SCRIPT="$SCRIPT_DIR/render_unlimited_hiring_revenue_media.py"
WEB_SYNC_SCRIPT="$SCRIPT_DIR/sync_hiring_anomaly_web_artifacts.py"
TELEGRAM_SCRIPT="$SCRIPT_DIR/telegram_sender.py"
MONTHLY_REVENUE_SCRIPT="$SCRIPT_DIR/fetch_monthly_revenue.py"
LOG_FILE="$SCRIPT_DIR/launchd_run.log"
STAGE3_DIR="${HIRING_STAGE3_DIR:-$SCRIPT_DIR/stage3_web}"
DB_PATH="${DB_PATH:-$STAGE3_DIR/investment.db}"
export HIRING_STAGE3_DIR="$STAGE3_DIR"
export DB_PATH

# 雙通道通知（macOS + ntfy）
TOOLS_DIR="$PROJECT_ROOT"
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

run_python_script() {
    local script_path="$1"
    shift
    "$PYTHON" -c '
import importlib.abc
import importlib.util
from pathlib import Path
import sys

script = Path(sys.argv[1]).resolve()
script_dir = script.parent

LOCAL_MODULES = {
    "generate_unlimited_hiring_revenue_report": "generate_unlimited_hiring_revenue_report.py",
    "hiring_anomaly_detector": "hiring_anomaly_detector.py",
    "hiring_workflow_governance": "hiring_workflow_governance.py",
    "telegram_sender": "telegram_sender.py",
}


class RepoLocalLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        filename = LOCAL_MODULES.get(fullname)
        if not filename:
            return None
        module_path = script_dir / filename
        if not module_path.exists():
            return None
        return importlib.util.spec_from_loader(fullname, self, origin=str(module_path))

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module_path = Path(module.__spec__.origin)
        module.__file__ = str(module_path)
        module.__package__ = ""
        code = compile(module_path.read_text(encoding="utf-8"), str(module_path), "exec")
        exec(code, module.__dict__)


sys.meta_path.insert(0, RepoLocalLoader())
sys.argv = [str(script)] + sys.argv[2:]
globals_dict = {
    "__name__": "__main__",
    "__file__": str(script),
    "__package__": None,
    "__cached__": None,
}
code = compile(script.read_text(encoding="utf-8"), str(script), "exec")
exec(code, globals_dict)
' "$script_path" "$@"
}

# 記錄時間
echo "========================================" >> "$LOG_FILE"
echo "執行時間: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"

if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    . "$SCRIPT_DIR/.env"
    set +a
fi

# 檢查 1：正式專案根目錄是否存在
if [ ! -d "$PROJECT_ROOT" ]; then
    MSG="正式專案根目錄不存在：$PROJECT_ROOT"
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

# 檢查 5：checker 是否存在
if [ ! -f "$CHECKER_SCRIPT" ]; then
    MSG="checker 不存在：$CHECKER_SCRIPT"
    echo "錯誤: $MSG" >> "$LOG_FILE"
    notify "徵人需求度更新失敗" "$MSG"
    exit 1
fi

# 檢查 6：104 搜尋 API probe + typed recovery loop
if [ ! -f "$PROBE_SCRIPT" ]; then
    MSG="104 API probe 腳本不存在：$PROBE_SCRIPT"
    echo "錯誤: $MSG" >> "$LOG_FILE"
    notify "徵人需求度更新失敗" "$MSG"
    exit 1
fi

PROBE_ROOT="$SCRIPT_DIR/data/runs/api_probe_$(date '+%Y%m%d_%H%M%S')"
mkdir -p "$PROBE_ROOT"
PROBE_MAX_ATTEMPTS="${HIRING_104_PROBE_MAX_ATTEMPTS:-3}"
PROBE_RETRY_DELAYS="${HIRING_104_PROBE_RETRY_DELAYS:-0 600 1200}"
PROBE_TIMEOUT="${HIRING_104_PROBE_TIMEOUT_SECONDS:-8}"
PROBE_KEYWORD="${HIRING_104_PROBE_KEYWORD:-作業員}"
PROBE_PASS=0
PROBE_ATTEMPT=1

for PROBE_DELAY in $PROBE_RETRY_DELAYS; do
    if [ "$PROBE_ATTEMPT" -gt "$PROBE_MAX_ATTEMPTS" ]; then
        break
    fi
    if [ "$PROBE_DELAY" -gt 0 ]; then
        echo "104 API probe 第 ${PROBE_ATTEMPT} 輪前等待 ${PROBE_DELAY} 秒" >> "$LOG_FILE"
        sleep "$PROBE_DELAY"
    fi

    PROBE_RECEIPT="$PROBE_ROOT/api_probe_receipt_attempt_${PROBE_ATTEMPT}.json"
    echo "--- 104 API probe attempt ${PROBE_ATTEMPT} ---" >> "$LOG_FILE"
    run_python_script "$PROBE_SCRIPT" \
        --keyword "$PROBE_KEYWORD" \
        --timeout "$PROBE_TIMEOUT" \
        --output "$PROBE_RECEIPT" >> "$LOG_FILE" 2>&1
    PROBE_EXIT=$?

    PROBE_STATUS=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("gate_result","UNKNOWN"))' "$PROBE_RECEIPT" 2>/dev/null || echo "UNKNOWN")
    PROBE_FAILURE=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("failure_type") or "")' "$PROBE_RECEIPT" 2>/dev/null || echo "probe_receipt_unreadable")
    PROBE_ACTION=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("recovery_action","unknown"))' "$PROBE_RECEIPT" 2>/dev/null || echo "unknown")
    echo "104 API probe result: status=${PROBE_STATUS} failure=${PROBE_FAILURE} action=${PROBE_ACTION} receipt=${PROBE_RECEIPT}" >> "$LOG_FILE"

    if [ "$PROBE_EXIT" -eq 0 ] && [ "$PROBE_STATUS" = "PASS" ]; then
        PROBE_PASS=1
        break
    fi
    if [ "$PROBE_ACTION" != "wait_and_retry" ] && [ "$PROBE_ACTION" != "keyword_probe_then_retry" ]; then
        break
    fi
    PROBE_ATTEMPT=$((PROBE_ATTEMPT + 1))
done

if [ "$PROBE_PASS" -ne 1 ]; then
    MSG="104 搜尋 API probe 未通過，typed failure=${PROBE_FAILURE:-unknown}，recovery=${PROBE_ACTION:-unknown}，receipt=$PROBE_ROOT"
    echo "錯誤: $MSG" >> "$LOG_FILE"
    notify "徵人需求度更新失敗" "$MSG"
    exit 1
fi

# 檢查 7：人數不限營收報表 generator / checker / renderer / web sync 是否存在
if [ ! -f "$REPORT_SCRIPT" ] || [ ! -f "$REPORT_CHECKER_SCRIPT" ] || [ ! -f "$REPORT_RENDER_SCRIPT" ] || [ ! -f "$WEB_SYNC_SCRIPT" ] || [ ! -f "$TELEGRAM_SCRIPT" ] || [ ! -f "$MONTHLY_REVENUE_SCRIPT" ]; then
    MSG="人數不限營收報表腳本、media renderer、web sync、Telegram sender 或月營收補抓腳本不存在"
    echo "錯誤: $MSG" >> "$LOG_FILE"
    notify "徵人需求度更新失敗" "$MSG"
    exit 1
fi

# 一切就緒，執行主程式
echo "環境檢查通過，開始執行..." >> "$LOG_FILE"
cd "$SCRIPT_DIR"
DEPLOY_MODE="${HIRING_DEMAND_DEPLOY_MODE:-disabled}"
RUN_MODE="${HIRING_DEMAND_RUN_MODE:-write-db}"
if [ "$DEPLOY_MODE" = "deploy" ] && [ -z "${HIRING_DEMAND_RUN_MODE:-}" ]; then
    RUN_MODE="deploy"
fi
export HIRING_DEMAND_RUN_MODE="$RUN_MODE"
echo "Run mode: $HIRING_DEMAND_RUN_MODE / Deploy mode: $DEPLOY_MODE" >> "$LOG_FILE"
run_python_script "$MAIN_SCRIPT" >> "$LOG_FILE" 2>&1
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

# 爬蟲成功後，先跑 read-only checker。預設不部署。
if [ $EXIT_CODE -eq 0 ]; then
    MANIFEST="$SCRIPT_DIR/data/runs/latest_hiring_run_manifest.json"
    CHECK_ROOT="$SCRIPT_DIR/data/runs/check_$(date '+%Y%m%d_%H%M%S')"
    echo "--- 開始徵人需求度 checker ---" >> "$LOG_FILE"
    run_python_script "$CHECKER_SCRIPT" --manifest "$MANIFEST" --output-dir "$CHECK_ROOT" >> "$LOG_FILE" 2>&1
    CHECK_EXIT=$?
    if [ $CHECK_EXIT -ne 0 ]; then
        echo "checker 失敗，exit code: $CHECK_EXIT" >> "$LOG_FILE"
        notify "徵人需求度 checker 失敗" "爬蟲成功但 CSV/DB gate 未通過，已停止部署"
        exit $CHECK_EXIT
    fi
    echo "checker PASS: $CHECK_ROOT" >> "$LOG_FILE"

    REPORT_MANIFEST="$SCRIPT_DIR/data/reports/latest_unlimited_hiring_revenue_report_manifest.json"
    REPORT_CHECK_ROOT="$SCRIPT_DIR/data/reports/report_check_$(date '+%Y%m%d_%H%M%S')"
    echo "--- 開始人數不限公司近六月營收報表 ---" >> "$LOG_FILE"
    run_python_script "$REPORT_SCRIPT" \
        --data-dir "$SCRIPT_DIR/data" \
        --db-path "$DB_PATH" \
        --latest-manifest-path "$REPORT_MANIFEST" >> "$LOG_FILE" 2>&1
    REPORT_EXIT=$?
    if [ $REPORT_EXIT -ne 0 ]; then
        echo "人數不限營收報表產生失敗，exit code: $REPORT_EXIT" >> "$LOG_FILE"
        notify "徵人需求度報表失敗" "人數不限營收報表產生失敗，已停止部署"
        exit $REPORT_EXIT
    fi

    run_python_script "$REPORT_CHECKER_SCRIPT" \
        --manifest "$REPORT_MANIFEST" \
        --output-dir "$REPORT_CHECK_ROOT" >> "$LOG_FILE" 2>&1
    REPORT_CHECK_EXIT=$?
    if [ $REPORT_CHECK_EXIT -ne 0 ]; then
        echo "人數不限營收報表 checker 失敗，exit code: $REPORT_CHECK_EXIT" >> "$LOG_FILE"
        MISSING_REVENUE_CODES=$("$PYTHON" - "$REPORT_CHECK_ROOT/typed_blockers.csv" <<'PY'
import csv
import sys
from pathlib import Path

path = Path(sys.argv[1])
codes = []
if path.exists():
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("finding_type") == "missing_revenue_summary":
                code = str(row.get("affected_key") or "").strip()
                if code and code not in codes:
                    codes.append(code)
print(",".join(codes))
PY
)
        if [ -n "$MISSING_REVENUE_CODES" ]; then
            echo "偵測到缺月營收公司，開始自動補抓: $MISSING_REVENUE_CODES" >> "$LOG_FILE"
            REVENUE_REMEDIATION_ROOT="$SCRIPT_DIR/data/reports/revenue_remediation_$(date '+%Y%m%d_%H%M%S')"
            mkdir -p "$REVENUE_REMEDIATION_ROOT"
            run_python_script "$MONTHLY_REVENUE_SCRIPT" \
                --codes "$MISSING_REVENUE_CODES" \
                --skip-git \
                --output-receipt "$REVENUE_REMEDIATION_ROOT/monthly_revenue_backfill_receipt.json" >> "$LOG_FILE" 2>&1
            REVENUE_REMEDIATION_EXIT=$?
            if [ $REVENUE_REMEDIATION_EXIT -ne 0 ]; then
                echo "缺月營收自動補抓失敗，exit code: $REVENUE_REMEDIATION_EXIT" >> "$LOG_FILE"
                notify "徵人需求度報表修復失敗" "缺月營收補抓失敗：$MISSING_REVENUE_CODES"
                exit $REVENUE_REMEDIATION_EXIT
            fi

            echo "缺月營收補抓完成，重新產生報表並重跑 checker" >> "$LOG_FILE"
            run_python_script "$REPORT_SCRIPT" \
                --data-dir "$SCRIPT_DIR/data" \
                --db-path "$DB_PATH" \
                --latest-manifest-path "$REPORT_MANIFEST" >> "$LOG_FILE" 2>&1
            REPORT_RETRY_EXIT=$?
            if [ $REPORT_RETRY_EXIT -ne 0 ]; then
                echo "補抓後報表重新產生失敗，exit code: $REPORT_RETRY_EXIT" >> "$LOG_FILE"
                notify "徵人需求度報表修復失敗" "補抓月營收後仍無法重新產生報表"
                exit $REPORT_RETRY_EXIT
            fi

            REPORT_CHECK_ROOT="$SCRIPT_DIR/data/reports/report_check_retry_$(date '+%Y%m%d_%H%M%S')"
            run_python_script "$REPORT_CHECKER_SCRIPT" \
                --manifest "$REPORT_MANIFEST" \
                --output-dir "$REPORT_CHECK_ROOT" >> "$LOG_FILE" 2>&1
            REPORT_CHECK_EXIT=$?
            if [ $REPORT_CHECK_EXIT -ne 0 ]; then
                echo "補抓後人數不限營收報表 checker 仍失敗，exit code: $REPORT_CHECK_EXIT" >> "$LOG_FILE"
                notify "徵人需求度報表 checker 失敗" "缺月營收已嘗試補抓，但 artifact gate 仍未通過"
                exit $REPORT_CHECK_EXIT
            fi
            echo "缺月營收自動補抓閉回路 PASS: $REVENUE_REMEDIATION_ROOT / $REPORT_CHECK_ROOT" >> "$LOG_FILE"
        else
            notify "徵人需求度報表 checker 失敗" "報表 artifact gate 未通過，已停止部署"
            exit $REPORT_CHECK_EXIT
        fi
    fi
    echo "人數不限營收報表 checker PASS: $REPORT_CHECK_ROOT" >> "$LOG_FILE"

    REPORT_KEY=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["report_yyyymmdd"])' "$REPORT_MANIFEST")
    REPORT_OUTPUT_DIR=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["outputs"]["output_dir"])' "$REPORT_MANIFEST")
    REPORT_MEDIA_RECEIPT="$REPORT_OUTPUT_DIR/unlimited_hiring_revenue_media_receipt_${REPORT_KEY}.json"

    echo "--- 開始 PNG/PDF media render ---" >> "$LOG_FILE"
    run_python_script "$REPORT_RENDER_SCRIPT" \
        --manifest "$REPORT_MANIFEST" \
        --png-scale "${HIRING_REPORT_PNG_SCALE:-1.5}" \
        --png-dpi "${HIRING_REPORT_PNG_DPI:-150}" >> "$LOG_FILE" 2>&1
    RENDER_EXIT=$?
    if [ $RENDER_EXIT -ne 0 ]; then
        echo "PNG/PDF media render 失敗，exit code: $RENDER_EXIT" >> "$LOG_FILE"
        notify "徵人需求度媒體報表失敗" "PNG/PDF 產生失敗，已停止部署與 Telegram"
        exit $RENDER_EXIT
    fi

    REPORT_MEDIA_CHECK_ROOT="$SCRIPT_DIR/data/reports/report_media_check_$(date '+%Y%m%d_%H%M%S')"
    run_python_script "$REPORT_CHECKER_SCRIPT" \
        --manifest "$REPORT_MANIFEST" \
        --output-dir "$REPORT_MEDIA_CHECK_ROOT" \
        --require-media \
        --media-receipt "$REPORT_MEDIA_RECEIPT" >> "$LOG_FILE" 2>&1
    REPORT_MEDIA_CHECK_EXIT=$?
    if [ $REPORT_MEDIA_CHECK_EXIT -ne 0 ]; then
        echo "PNG/PDF media checker 失敗，exit code: $REPORT_MEDIA_CHECK_EXIT" >> "$LOG_FILE"
        notify "徵人需求度媒體 gate 失敗" "PNG/PDF receipt 與 report manifest 未同步，已停止部署與 Telegram"
        exit $REPORT_MEDIA_CHECK_EXIT
    fi
    echo "PNG/PDF media checker PASS: $REPORT_MEDIA_CHECK_ROOT" >> "$LOG_FILE"

    echo "--- 同步異常偵測摘要到 stage3_web/hiring_reports 與 data/hiring_reports ---" >> "$LOG_FILE"
    run_python_script "$WEB_SYNC_SCRIPT" \
        --manifest "$REPORT_MANIFEST" \
        --stage3-dir "$STAGE3_DIR" >> "$LOG_FILE" 2>&1
    WEB_SYNC_EXIT=$?
    if [ $WEB_SYNC_EXIT -ne 0 ]; then
        echo "stage3_web 異常偵測摘要同步失敗，exit code: $WEB_SYNC_EXIT" >> "$LOG_FILE"
        notify "徵人需求度網頁摘要同步失敗" "stage3_web/hiring_reports 未同步，已停止部署與 Telegram"
        exit $WEB_SYNC_EXIT
    fi

    REPORT_PNG_PATH="$REPORT_OUTPUT_DIR/unlimited_hiring_revenue_report_${REPORT_KEY}.png"
    REPORT_DATE=$("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("report_date",""))' "$REPORT_OUTPUT_DIR/anomaly_summary_${REPORT_KEY}.json")
    TELEGRAM_DOCUMENT_PATH="$REPORT_OUTPUT_DIR/${REPORT_DATE}_徵人需求度每日異常偵測摘要.png"
    cp "$REPORT_PNG_PATH" "$TELEGRAM_DOCUMENT_PATH"
    TELEGRAM_RECEIPT="$REPORT_OUTPUT_DIR/telegram_send_receipt_${REPORT_KEY}.json"
    if [ "${HIRING_TELEGRAM_SEND_MODE:-disabled}" = "enabled" ]; then
        echo "--- Telegram sendDocument 已啟用，開始發送 PNG 文件（無文字說明） ---" >> "$LOG_FILE"
        run_python_script "$TELEGRAM_SCRIPT" \
            --env-path "$SCRIPT_DIR/.env" \
            --recipients-path "$SCRIPT_DIR/telegram_recipients.json" \
            --photo-path "$REPORT_PNG_PATH" \
            --document-path "$TELEGRAM_DOCUMENT_PATH" \
            --output-receipt "$TELEGRAM_RECEIPT" \
            --message-text "" \
            --caption "" \
            --timeout-seconds "${HIRING_TELEGRAM_TIMEOUT_SECONDS:-180}" \
            --send-document >> "$LOG_FILE" 2>&1
        TELEGRAM_EXIT=$?
        if [ $TELEGRAM_EXIT -ne 0 ]; then
            echo "Telegram sendDocument 失敗，exit code: $TELEGRAM_EXIT" >> "$LOG_FILE"
            notify "徵人需求度 Telegram 發送失敗" "PNG 文件未成功送出，已停止部署"
            exit $TELEGRAM_EXIT
        fi
    else
        echo "Telegram sendDocument 未啟用；若要每日自動發送，需設定 HIRING_TELEGRAM_SEND_MODE=enabled。" >> "$LOG_FILE"
    fi

    if [ "$DEPLOY_MODE" != "deploy" ]; then
        echo "未開啟 deploy mode，略過 commit/push。若要部署，需設定 HIRING_DEMAND_DEPLOY_MODE=deploy。" >> "$LOG_FILE"
        echo "" >> "$LOG_FILE"
        exit 0
    fi

    DEPLOY_CHECK_ROOT="$SCRIPT_DIR/data/runs/deploy_check_$(date '+%Y%m%d_%H%M%S')"
    run_python_script "$CHECKER_SCRIPT" --manifest "$MANIFEST" --output-dir "$DEPLOY_CHECK_ROOT" --require-deploy-mode >> "$LOG_FILE" 2>&1
    DEPLOY_CHECK_EXIT=$?
    if [ $DEPLOY_CHECK_EXIT -ne 0 ]; then
        echo "deploy checker 失敗，exit code: $DEPLOY_CHECK_EXIT" >> "$LOG_FILE"
        notify "徵人需求度部署停止" "deploy mode 未通過 checker，未 commit/push"
        exit $DEPLOY_CHECK_EXIT
    fi

    echo "--- checker PASS，開始部署至 Railway ---" >> "$LOG_FILE"
    GIT="/usr/bin/git"
    TODAY=$(date '+%Y/%m/%d %H:%M')

    cd "$SCRIPT_DIR"
    if ! "$GIT" rev-parse --show-toplevel >/dev/null 2>&1; then
        echo "徵人需求度外層資料夾尚未初始化 Git repo，停止自動 commit/push：$SCRIPT_DIR" >> "$LOG_FILE"
        notify "徵人需求度部署需初始化" "外層徵人需求度 repo 尚未設定 Git remote，未 commit/push"
        exit 1
    fi

    PRE_STAGED=$("$GIT" diff --cached --name-only)
    if [ -n "$PRE_STAGED" ]; then
        echo "外層 repo 已有 staged changes，停止自動部署：" >> "$LOG_FILE"
        echo "$PRE_STAGED" >> "$LOG_FILE"
        notify "徵人需求度部署停止" "外層 repo 已有 staged changes，請人工確認"
        exit 1
    fi

    "$GIT" add stage3_web/hiring_reports stage3_web/data/hiring_reports >> "$LOG_FILE" 2>&1
    STAGED_AFTER_ADD=$("$GIT" diff --cached --name-only)
    UNRELATED_STAGED=$(printf '%s\n' "$STAGED_AFTER_ADD" | grep -Ev '^stage3_web/(hiring_reports/|data/hiring_reports/)' || true)
    if [ -n "$UNRELATED_STAGED" ]; then
        echo "自動部署只允許 stage3_web/hiring_reports 與 stage3_web/data/hiring_reports，停止：" >> "$LOG_FILE"
        echo "$UNRELATED_STAGED" >> "$LOG_FILE"
        notify "徵人需求度部署停止" "偵測到非 stage3_web hiring_reports staged changes"
        exit 1
    fi

    if "$GIT" diff --cached --quiet -- stage3_web/hiring_reports stage3_web/data/hiring_reports; then
        echo "stage3_web/hiring_reports 與 stage3_web/data/hiring_reports 無 staged 變更，略過 commit/push。" >> "$LOG_FILE"
        notify "徵人需求度更新完成" "checker PASS；stage3_web hiring_reports 無需部署 ${TODAY}"
        echo "" >> "$LOG_FILE"
        exit 0
    fi

    "$GIT" commit -m "chore: 自動更新徵人需求度資料 ${TODAY}" >> "$LOG_FILE" 2>&1
    COMMIT_EXIT=$?
    if [ $COMMIT_EXIT -ne 0 ]; then
        echo "Railway commit 失敗，exit code: $COMMIT_EXIT" >> "$LOG_FILE"
        notify "徵人需求度部署失敗" "checker PASS 但 git commit 失敗，請手動確認"
        exit $COMMIT_EXIT
    fi

    "$GIT" push origin main >> "$LOG_FILE" 2>&1
    PUSH_EXIT=$?

    if [ $PUSH_EXIT -eq 0 ]; then
        echo "Railway 部署成功 (${TODAY})" >> "$LOG_FILE"
        notify "徵人需求度更新完成" "資料已自動部署至外網 ${TODAY}"
    else
        echo "Railway push 失敗，exit code: $PUSH_EXIT" >> "$LOG_FILE"
        notify "徵人需求度部署失敗" "爬蟲成功但 git push 失敗，請手動確認"
        exit $PUSH_EXIT
    fi
fi

echo "" >> "$LOG_FILE"
exit $EXIT_CODE
