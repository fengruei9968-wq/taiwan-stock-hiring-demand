#!/bin/bash
# =============================================================================
# 徵人需求度更新程式 - launchd 排程安裝/移除腳本
# =============================================================================

PLIST_NAME="com.hiring.demand.updater.plist"
PROBE_PLIST_NAME="com.hiring.telegram.recipient.probe.plist"
STOCK_CODES_PLIST_NAME="com.hiring.stock.codes.updater.plist"
BACKUP_PLIST_NAME="com.hiring.daily.artifacts.backup.plist"
RAW_REVENUE_PLIST_NAME="com.stock.monthly.revenue.raw.updater.plist"
RAW_REVENUE_PLIST_NAMES=(
    "com.stock.monthly.revenue.raw.updater.plist"
    "com.stock.monthly.revenue.raw.emerging.updater.plist"
    "com.stock.monthly.revenue.raw.missing.retry.plist"
)
HIRING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="${HIRING_PROJECT_ROOT:-$(cd "$HIRING_DIR/.." && pwd -P)}"
SCHEDULER_TEMPLATE_DIR="${HIRING_SCHEDULER_TEMPLATE_DIR:-$HIRING_DIR/scheduler_templates}"
SCHEDULER_RENDER_DIR="${HIRING_SCHEDULER_RENDER_DIR:-$HIRING_DIR/_local_runtime/launchd_rendered}"
ARTIFACT_BACKUP_ROOT="${HIRING_ARTIFACT_BACKUP_ROOT:-/Volumes/Extreme SSD/Backup/徵人需求度每日產物Backup}"
LOCAL_LAUNCHER_DIR="${HIRING_LOCAL_LAUNCHER_DIR:-$HOME/Library/Application Support/HiringDemandLauncher}"
LOCAL_LAUNCHER_PATH="${HIRING_LOCAL_LAUNCHER_PATH:-$LOCAL_LAUNCHER_DIR/run_hiring_demand_launcher.sh}"
LOCAL_MAIN_WRAPPER_PATH="${HIRING_LOCAL_MAIN_WRAPPER_PATH:-$LOCAL_LAUNCHER_DIR/run_hiring_demand.sh}"
LOCAL_PROBE_WRAPPER_PATH="${HIRING_LOCAL_PROBE_WRAPPER_PATH:-$LOCAL_LAUNCHER_DIR/run_telegram_recipient_probe.sh}"
LOCAL_STOCK_CODES_WRAPPER_PATH="${HIRING_LOCAL_STOCK_CODES_WRAPPER_PATH:-$LOCAL_LAUNCHER_DIR/run_stock_codes_update.sh}"
LOCAL_RAW_REVENUE_WRAPPER_PATH="${HIRING_LOCAL_RAW_REVENUE_WRAPPER_PATH:-$LOCAL_LAUNCHER_DIR/run_stock_monthly_revenue_raw.sh}"
LOCAL_LOG_DIR="${HIRING_LOCAL_LOG_DIR:-$HOME/Library/Logs/HiringDemand}"
LOCAL_VENV_DIR="${HIRING_LOCAL_VENV_DIR:-$LOCAL_LAUNCHER_DIR/venv}"
LOCAL_VENV_PYTHON="${HIRING_LOCAL_VENV_PYTHON:-$LOCAL_VENV_DIR/bin/python3}"
LOCAL_VENV_BOOTSTRAP_PYTHON="${HIRING_LOCAL_VENV_BOOTSTRAP_PYTHON:-/opt/homebrew/opt/python@3.13/bin/python3.13}"
LOCAL_VENV_REQUIREMENTS="${HIRING_LOCAL_VENV_REQUIREMENTS:-$HIRING_DIR/scheduler_requirements.txt}"
LOCAL_LAUNCHER_TEMPLATE="${SCHEDULER_TEMPLATE_DIR}/run_hiring_demand_launcher.sh.template"
RENDER_ONLY="${HIRING_SCHEDULER_RENDER_ONLY:-0}"
PLIST_SOURCE="${SCHEDULER_TEMPLATE_DIR}/${PLIST_NAME}.template"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_NAME}"
PROBE_PLIST_SOURCE="${SCHEDULER_TEMPLATE_DIR}/${PROBE_PLIST_NAME}.template"
PROBE_PLIST_DEST="$HOME/Library/LaunchAgents/${PROBE_PLIST_NAME}"
STOCK_CODES_PLIST_SOURCE="${SCHEDULER_TEMPLATE_DIR}/${STOCK_CODES_PLIST_NAME}.template"
STOCK_CODES_PLIST_DEST="$HOME/Library/LaunchAgents/${STOCK_CODES_PLIST_NAME}"
BACKUP_PLIST_SOURCE="${SCHEDULER_TEMPLATE_DIR}/${BACKUP_PLIST_NAME}.template"
BACKUP_PLIST_DEST="$HOME/Library/LaunchAgents/${BACKUP_PLIST_NAME}"
RAW_REVENUE_PLIST_SOURCE="${SCHEDULER_TEMPLATE_DIR}/${RAW_REVENUE_PLIST_NAME}.template"
RAW_REVENUE_PLIST_DEST="$HOME/Library/LaunchAgents/${RAW_REVENUE_PLIST_NAME}"

if [ "${1:-}" = "--render-only" ]; then
    RENDER_ONLY=1
    shift
fi

render_plist_template() {
    local source="$1"
    local dest="$2"
    if [ ! -f "$source" ]; then
        echo "錯誤: plist template 不存在：$source"
        exit 1
    fi
    mkdir -p "$(dirname "$dest")"
    sed \
        -e "s|__HIRING_DIR__|$HIRING_DIR|g" \
        -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
        -e "s|__ARTIFACT_BACKUP_ROOT__|$ARTIFACT_BACKUP_ROOT|g" \
        -e "s|__LOCAL_LAUNCHER_DIR__|$LOCAL_LAUNCHER_DIR|g" \
        -e "s|__LOCAL_LAUNCHER_PATH__|$LOCAL_LAUNCHER_PATH|g" \
        -e "s|__LOCAL_LOG_DIR__|$LOCAL_LOG_DIR|g" \
        "$source" > "$dest"
}

render_launcher_template() {
    local dest="$1"
    if [ ! -f "$LOCAL_LAUNCHER_TEMPLATE" ]; then
        echo "錯誤: launcher template 不存在：$LOCAL_LAUNCHER_TEMPLATE"
        exit 1
    fi
    mkdir -p "$(dirname "$dest")"
    sed \
        -e "s|__HIRING_DIR__|$HIRING_DIR|g" \
        -e "s|__LOCAL_LOG_DIR__|$LOCAL_LOG_DIR|g" \
        -e "s|__LOCAL_VENV_PYTHON__|$LOCAL_VENV_PYTHON|g" \
        -e "s|__LOCAL_MAIN_WRAPPER__|$LOCAL_MAIN_WRAPPER_PATH|g" \
        -e "s|__LOCAL_PROBE_WRAPPER__|$LOCAL_PROBE_WRAPPER_PATH|g" \
        -e "s|__LOCAL_STOCK_CODES_WRAPPER__|$LOCAL_STOCK_CODES_WRAPPER_PATH|g" \
        -e "s|__LOCAL_RAW_REVENUE_WRAPPER__|$LOCAL_RAW_REVENUE_WRAPPER_PATH|g" \
        "$LOCAL_LAUNCHER_TEMPLATE" > "$dest"
    chmod 755 "$dest"
}

install_local_wrapper_copies() {
    local main_dest="$LOCAL_MAIN_WRAPPER_PATH"
    local probe_dest="$LOCAL_PROBE_WRAPPER_PATH"
    local stock_codes_dest="$LOCAL_STOCK_CODES_WRAPPER_PATH"
    local raw_revenue_dest="$LOCAL_RAW_REVENUE_WRAPPER_PATH"
    if [ "$RENDER_ONLY" = "1" ]; then
        main_dest="$SCHEDULER_RENDER_DIR/$(basename "$LOCAL_MAIN_WRAPPER_PATH")"
        probe_dest="$SCHEDULER_RENDER_DIR/$(basename "$LOCAL_PROBE_WRAPPER_PATH")"
        stock_codes_dest="$SCHEDULER_RENDER_DIR/$(basename "$LOCAL_STOCK_CODES_WRAPPER_PATH")"
        raw_revenue_dest="$SCHEDULER_RENDER_DIR/$(basename "$LOCAL_RAW_REVENUE_WRAPPER_PATH")"
    fi
    mkdir -p "$(dirname "$main_dest")"
    install -m 755 "$HIRING_DIR/run_hiring_demand.sh" "$main_dest"
    install -m 755 "$HIRING_DIR/run_telegram_recipient_probe.sh" "$probe_dest"
    install -m 755 "$HIRING_DIR/run_stock_codes_update.sh" "$stock_codes_dest"
    install -m 755 "$HIRING_DIR/run_stock_monthly_revenue_raw.sh" "$raw_revenue_dest"
    if [ "$RENDER_ONLY" = "1" ]; then
        echo "render-only: $main_dest"
        echo "render-only: $probe_dest"
        echo "render-only: $stock_codes_dest"
        echo "render-only: $raw_revenue_dest"
    fi
}

install_local_scheduler_venv() {
    if [ "$RENDER_ONLY" = "1" ]; then
        return
    fi
    if [ ! -x "$LOCAL_VENV_PYTHON" ]; then
        if [ ! -x "$LOCAL_VENV_BOOTSTRAP_PYTHON" ]; then
            echo "錯誤: 建立本機排程 venv 的 Python 不存在或不可執行：$LOCAL_VENV_BOOTSTRAP_PYTHON"
            exit 1
        fi
        echo "建立本機排程專用 venv：$LOCAL_VENV_DIR"
        mkdir -p "$LOCAL_LAUNCHER_DIR"
        "$LOCAL_VENV_BOOTSTRAP_PYTHON" -m venv "$LOCAL_VENV_DIR"
    fi
    if [ ! -f "$LOCAL_VENV_REQUIREMENTS" ]; then
        echo "錯誤: 本機排程 venv requirements 不存在：$LOCAL_VENV_REQUIREMENTS"
        exit 1
    fi
    echo "確認本機排程 venv 依賴：$LOCAL_VENV_REQUIREMENTS"
    "$LOCAL_VENV_PYTHON" -m pip install -r "$LOCAL_VENV_REQUIREMENTS"
}

install_local_launcher() {
    local render_dest="$LOCAL_LAUNCHER_PATH"
    if [ "$RENDER_ONLY" = "1" ]; then
        render_dest="$SCHEDULER_RENDER_DIR/$(basename "$LOCAL_LAUNCHER_PATH")"
        echo "render-only：產生 local launcher，不安裝到內建磁碟..."
    else
        echo "安裝 local launcher..."
        mkdir -p "$LOCAL_LAUNCHER_DIR" "$LOCAL_LOG_DIR"
        install_local_scheduler_venv
    fi
    render_launcher_template "$render_dest"
    install_local_wrapper_copies
    if [ "$RENDER_ONLY" = "1" ]; then
        echo "render-only: $render_dest"
        return
    fi
    echo "local launcher 已安裝：$LOCAL_LAUNCHER_PATH"
}

install_plist_from_template() {
    local source="$1"
    local dest="$2"
    local render_dest="$dest"
    if [ "$RENDER_ONLY" = "1" ]; then
        render_dest="$SCHEDULER_RENDER_DIR/$(basename "$dest")"
    fi
    render_plist_template "$source" "$render_dest"
    if [ "$RENDER_ONLY" = "1" ]; then
        echo "render-only: $render_dest"
        return
    fi
    launchctl unload "$dest" 2>/dev/null || true
    launchctl load "$dest"
}

show_help() {
    echo "用法: $0 [--render-only] [install|uninstall|status|run|install-probe|uninstall-probe|status-probe|run-probe|install-stock-codes|uninstall-stock-codes|status-stock-codes|run-stock-codes|install-all-local|doctor|install-raw-revenue|uninstall-raw-revenue|status-raw-revenue|run-raw-revenue|install-artifact-backup|uninstall-artifact-backup|status-artifact-backup|run-artifact-backup]"
    echo ""
    echo "指令:"
    echo "  install   - 安裝排程（每天 11:30 自動執行）"
    echo "  uninstall - 移除排程"
    echo "  status    - 查看排程狀態"
    echo "  run       - 立即執行一次（測試用）"
    echo "  install-probe   - 安裝 Telegram recipient probe（每小時執行一次）"
    echo "  uninstall-probe - 移除 Telegram recipient probe"
    echo "  status-probe    - 查看 Telegram recipient probe 狀態"
    echo "  run-probe       - 立即執行一次 Telegram recipient probe"
    echo "  install-stock-codes   - 安裝徵人需求度專用 Stock_codes 更新（每天 05:00）"
    echo "  uninstall-stock-codes - 移除徵人需求度專用 Stock_codes 更新"
    echo "  status-stock-codes    - 查看徵人需求度專用 Stock_codes 更新狀態"
    echo "  run-stock-codes       - 立即執行一次徵人需求度專用 Stock_codes 更新"
    echo "  install-all-local - 安裝本機 launcher + 主排程 + Telegram recipient probe + 月營收 raw 排程"
    echo "  doctor           - 檢查本機 launcher / LaunchAgent 是否正確安裝（可加 --notify-ntfy）"
    echo "  install-artifact-backup   - 安裝每日產物 SSD 備份（每月 5 號 20:00）"
    echo "  uninstall-artifact-backup - 移除每日產物 SSD 備份"
    echo "  status-artifact-backup    - 查看每日產物 SSD 備份狀態"
    echo "  run-artifact-backup       - 立即執行一次每日產物 SSD 備份"
    echo "  install-raw-revenue   - 安裝月營收 raw 更新（本機 launcher；5 號上市/上櫃、10 號興櫃、15 號缺月補跑）"
    echo "  uninstall-raw-revenue - 移除月營收 raw 更新"
    echo "  status-raw-revenue    - 查看月營收 raw 更新狀態"
    echo "  run-raw-revenue       - 立即執行一次月營收 raw 更新"
    echo ""
}

install_scheduler() {
    if [ "$RENDER_ONLY" = "1" ]; then
        echo "render-only：產生徵人需求度排程 plist，不安裝、不載入 launchd..."
    else
        echo "安裝排程..."
    fi

    # 確保目錄存在
    if [ "$RENDER_ONLY" != "1" ]; then
        mkdir -p "$HOME/Library/LaunchAgents"
    fi
    install_local_launcher

    # 複製 plist 檔案
    install_plist_from_template "$PLIST_SOURCE" "$PLIST_DEST"

    if [ "$RENDER_ONLY" = "1" ]; then
        return
    fi
    echo "排程已安裝！"
    echo "  - 執行時間: 每天 11:30"
    echo "  - local launcher: $LOCAL_LAUNCHER_PATH"
    echo "  - local main wrapper: $LOCAL_MAIN_WRAPPER_PATH"
    echo "  - local probe wrapper: $LOCAL_PROBE_WRAPPER_PATH"
    echo "  - local stock codes wrapper: $LOCAL_STOCK_CODES_WRAPPER_PATH"
    echo "  - local raw revenue wrapper: $LOCAL_RAW_REVENUE_WRAPPER_PATH"
    echo "  - local scheduler venv: $LOCAL_VENV_DIR"
    echo "  - 設定檔: $PLIST_DEST"
    echo ""
    echo "查看狀態: $0 status"
}

uninstall_scheduler() {
    echo "移除排程..."

    # 卸載排程
    launchctl unload "$PLIST_DEST" 2>/dev/null

    # 刪除 plist 檔案
    rm -f "$PLIST_DEST"

    echo "排程已移除！"
}

show_status() {
    echo "排程狀態:"
    echo ""

    if [ -f "$PLIST_DEST" ]; then
        echo "設定檔: 已安裝"
        echo ""
        launchctl list | grep com.hiring.demand.updater
        if [ $? -eq 0 ]; then
            echo ""
            echo "排程已載入並運行中"
        else
            echo "排程未載入（可能需要重新安裝）"
        fi
    else
        echo "設定檔: 未安裝"
    fi
}

run_now() {
    echo "立即執行徵人需求度更新程式..."
    echo ""

    cd "$HIRING_DIR"
    ./venv/bin/python3 fetch_hiring_demand.py
}

install_probe_scheduler() {
    if [ "$RENDER_ONLY" = "1" ]; then
        echo "render-only：產生 Telegram recipient probe plist，不安裝、不載入 launchd..."
    else
        echo "安裝 Telegram recipient probe 排程..."
    fi

    if [ "$RENDER_ONLY" != "1" ]; then
        mkdir -p "$HOME/Library/LaunchAgents"
    fi
    install_local_launcher
    install_plist_from_template "$PROBE_PLIST_SOURCE" "$PROBE_PLIST_DEST"

    if [ "$RENDER_ONLY" = "1" ]; then
        return
    fi
    echo "Telegram recipient probe 排程已安裝！"
    echo "  - 執行頻率: 每 1 小時"
    echo "  - local launcher: $LOCAL_LAUNCHER_PATH"
    echo "  - local probe wrapper: $LOCAL_PROBE_WRAPPER_PATH"
    echo "  - local scheduler venv: $LOCAL_VENV_DIR"
    echo "  - 設定檔: $PROBE_PLIST_DEST"
    echo "  - 邊界: 只更新 telegram_recipients.json，不發 PNG、不部署"
    echo ""
    echo "查看狀態: $0 status-probe"
}

uninstall_probe_scheduler() {
    echo "移除 Telegram recipient probe 排程..."

    launchctl unload "$PROBE_PLIST_DEST" 2>/dev/null || true
    rm -f "$PROBE_PLIST_DEST"

    echo "Telegram recipient probe 排程已移除！"
}

show_probe_status() {
    echo "Telegram recipient probe 排程狀態:"
    echo ""

    if [ -f "$PROBE_PLIST_DEST" ]; then
        echo "設定檔: 已安裝"
        echo ""
        launchctl list | grep com.hiring.telegram.recipient.probe
        if [ $? -eq 0 ]; then
            echo ""
            echo "Telegram recipient probe 排程已載入並運行中"
        else
            echo "Telegram recipient probe 排程未載入（可能需要重新安裝）"
        fi
    else
        echo "設定檔: 未安裝"
    fi
}

run_probe_now() {
    echo "立即執行 Telegram recipient probe..."
    echo ""

    cd "$HIRING_DIR"
    ./run_telegram_recipient_probe.sh
}

install_stock_codes_scheduler() {
    if [ "$RENDER_ONLY" = "1" ]; then
        echo "render-only：產生徵人需求度專用 Stock_codes 更新 plist，不安裝、不載入 launchd..."
    else
        echo "安裝徵人需求度專用 Stock_codes 更新排程..."
    fi

    if [ "$RENDER_ONLY" != "1" ]; then
        mkdir -p "$HOME/Library/LaunchAgents"
    fi
    install_local_launcher
    install_plist_from_template "$STOCK_CODES_PLIST_SOURCE" "$STOCK_CODES_PLIST_DEST"

    if [ "$RENDER_ONLY" = "1" ]; then
        return
    fi
    echo "徵人需求度專用 Stock_codes 更新排程已安裝！"
    echo "  - 執行時間: 每天 05:00"
    echo "  - label: com.hiring.stock.codes.updater"
    echo "  - output: $HIRING_DIR/data/stock_codes"
    echo "  - local launcher: $LOCAL_LAUNCHER_PATH"
    echo "  - 設定檔: $STOCK_CODES_PLIST_DEST"
    echo "  - 舊 com.stock.updater 不會被本指令修改；驗證新排程 PASS 後再手動停用舊排程。"
    echo ""
    echo "查看狀態: $0 status-stock-codes"
}

uninstall_stock_codes_scheduler() {
    echo "移除徵人需求度專用 Stock_codes 更新排程..."

    launchctl unload "$STOCK_CODES_PLIST_DEST" 2>/dev/null || true
    rm -f "$STOCK_CODES_PLIST_DEST"

    echo "徵人需求度專用 Stock_codes 更新排程已移除！"
}

show_stock_codes_status() {
    echo "徵人需求度專用 Stock_codes 更新排程狀態:"
    echo ""

    if [ -f "$STOCK_CODES_PLIST_DEST" ]; then
        echo "設定檔: 已安裝"
        echo ""
        launchctl list | grep com.hiring.stock.codes.updater
        if [ $? -eq 0 ]; then
            echo ""
            echo "徵人需求度專用 Stock_codes 更新排程已載入並運行中"
        else
            echo "徵人需求度專用 Stock_codes 更新排程未載入（可能需要重新安裝）"
        fi
    else
        echo "設定檔: 未安裝"
    fi
}

run_stock_codes_now() {
    echo "立即執行徵人需求度專用 Stock_codes 更新..."
    echo ""

    cd "$HIRING_DIR"
    ./run_stock_codes_update.sh
}

install_all_local() {
    install_stock_codes_scheduler
    install_scheduler
    install_probe_scheduler
    install_raw_revenue_scheduler
    doctor_scheduler
}

doctor_scheduler() {
    local notify_arg=""
    if [ "${2:-}" = "--notify-ntfy" ] || [ "${1:-}" = "--notify-ntfy" ]; then
        notify_arg="--notify-ntfy"
    fi
    if [ -x "$LOCAL_VENV_PYTHON" ]; then
        HIRING_LOCAL_VENV_DIR="$LOCAL_VENV_DIR" "$LOCAL_VENV_PYTHON" "$HIRING_DIR/check_scheduler_installation.py" --root "$HIRING_DIR" $notify_arg
    elif [ -x "$HIRING_DIR/venv/bin/python3" ]; then
        HIRING_LOCAL_VENV_DIR="$LOCAL_VENV_DIR" "$HIRING_DIR/venv/bin/python3" "$HIRING_DIR/check_scheduler_installation.py" --root "$HIRING_DIR" $notify_arg
    else
        HIRING_LOCAL_VENV_DIR="$LOCAL_VENV_DIR" python3 "$HIRING_DIR/check_scheduler_installation.py" --root "$HIRING_DIR" $notify_arg
    fi
}

install_artifact_backup_scheduler() {
    if [ "$RENDER_ONLY" = "1" ]; then
        echo "render-only：產生每日產物 SSD 備份 plist，不安裝、不載入 launchd..."
    else
        echo "安裝每日產物 SSD 備份排程..."
    fi

    if [ "$RENDER_ONLY" != "1" ]; then
        mkdir -p "$HOME/Library/LaunchAgents"
    fi
    install_plist_from_template "$BACKUP_PLIST_SOURCE" "$BACKUP_PLIST_DEST"

    if [ "$RENDER_ONLY" = "1" ]; then
        return
    fi
    echo "每日產物 SSD 備份排程已安裝！"
    echo "  - 執行時間: 每月 5 號 20:00"
    echo "  - 設定檔: $BACKUP_PLIST_DEST"
    echo "  - 目的地: /Volumes/Extreme SSD/Backup/徵人需求度每日產物Backup"
    echo "  - 邊界: copy-only，不刪本機、不搬本機、不碰 stage3_web"
    echo ""
    echo "查看狀態: $0 status-artifact-backup"
}

uninstall_artifact_backup_scheduler() {
    echo "移除每日產物 SSD 備份排程..."

    launchctl unload "$BACKUP_PLIST_DEST" 2>/dev/null || true
    rm -f "$BACKUP_PLIST_DEST"

    echo "每日產物 SSD 備份排程已移除！"
}

show_artifact_backup_status() {
    echo "每日產物 SSD 備份排程狀態:"
    echo ""

    if [ -f "$BACKUP_PLIST_DEST" ]; then
        echo "設定檔: 已安裝"
        echo ""
        launchctl list | grep com.hiring.daily.artifacts.backup
        if [ $? -eq 0 ]; then
            echo ""
            echo "每日產物 SSD 備份排程已載入並運行中"
        else
            echo "每日產物 SSD 備份排程未載入（可能需要重新安裝）"
        fi
    else
        echo "設定檔: 未安裝"
    fi
}

run_artifact_backup_now() {
    echo "立即執行每日產物 SSD 備份..."
    echo "copy-only，不刪本機、不搬本機。"
    echo ""

    cd "$HIRING_DIR"
    ./backup_hiring_daily_artifacts.sh
}

install_raw_revenue_scheduler() {
    if [ "$RENDER_ONLY" = "1" ]; then
        echo "render-only：產生月營收 raw 更新 plist，不安裝、不載入 launchd..."
    else
        echo "安裝月營收 raw 更新排程..."
    fi

    if [ "$RENDER_ONLY" != "1" ]; then
        mkdir -p "$HOME/Library/LaunchAgents"
    fi
    install_local_launcher
    for plist_name in "${RAW_REVENUE_PLIST_NAMES[@]}"; do
        plist_source="${SCHEDULER_TEMPLATE_DIR}/${plist_name}.template"
        plist_dest="$HOME/Library/LaunchAgents/${plist_name}"
        install_plist_from_template "$plist_source" "$plist_dest"
    done

    if [ "$RENDER_ONLY" = "1" ]; then
        return
    fi
    echo "月營收 raw 更新排程已安裝！"
    echo "  - 執行時間: 每月 5 號上市/上櫃、10 號興櫃、15 號缺月補跑"
    echo "  - local launcher: $LOCAL_LAUNCHER_PATH"
    echo "  - local raw revenue wrapper: $LOCAL_RAW_REVENUE_WRAPPER_PATH"
    echo "  - 設定檔:"
    for plist_name in "${RAW_REVENUE_PLIST_NAMES[@]}"; do
        echo "    - $HOME/Library/LaunchAgents/${plist_name}"
    done
    echo "  - 範圍: 2021-01 到上一個完整月份"
    echo "  - 市場別: 上市/上櫃、興櫃、全市場缺月補跑"
    echo "  - 資料: stage3_web/investment.db 的 stock_monthly_revenue + data/stock_monthly_revenue_raw/YYYYMMDD"
    echo "  - 部署: 預設只更新本機資料，不自動 commit/push"
    echo ""
    echo "查看狀態: $0 status-raw-revenue"
}

uninstall_raw_revenue_scheduler() {
    echo "移除月營收 raw 更新排程..."

    for plist_name in "${RAW_REVENUE_PLIST_NAMES[@]}"; do
        plist_dest="$HOME/Library/LaunchAgents/${plist_name}"
        launchctl unload "$plist_dest" 2>/dev/null || true
        rm -f "$plist_dest"
    done

    echo "月營收 raw 更新排程已移除！"
}

show_raw_revenue_status() {
    echo "月營收 raw 更新排程狀態:"
    echo ""

    for plist_name in "${RAW_REVENUE_PLIST_NAMES[@]}"; do
        plist_dest="$HOME/Library/LaunchAgents/${plist_name}"
        label="${plist_name%.plist}"
        if [ -f "$plist_dest" ]; then
            echo "設定檔: 已安裝 $plist_name"
            launchctl list | grep "$label"
            if [ $? -eq 0 ]; then
                echo "排程已載入: $label"
            else
                echo "排程未載入（可能需要重新安裝）: $label"
            fi
        fi
    done
}

run_raw_revenue_now() {
    echo "立即執行月營收 raw 更新..."
    echo "預設只更新本機資料，不自動 commit/push。"
    echo ""

    cd "$HIRING_DIR"
    ./run_stock_monthly_revenue_raw.sh
}

# 主程式
case "$1" in
    install)
        install_scheduler
        ;;
    uninstall)
        uninstall_scheduler
        ;;
    status)
        show_status
        ;;
    run)
        run_now
        ;;
    install-probe)
        install_probe_scheduler
        ;;
    uninstall-probe)
        uninstall_probe_scheduler
        ;;
    status-probe)
        show_probe_status
        ;;
    run-probe)
        run_probe_now
        ;;
    install-stock-codes)
        install_stock_codes_scheduler
        ;;
    uninstall-stock-codes)
        uninstall_stock_codes_scheduler
        ;;
    status-stock-codes)
        show_stock_codes_status
        ;;
    run-stock-codes)
        run_stock_codes_now
        ;;
    install-all-local)
        install_all_local
        ;;
    doctor)
        doctor_scheduler "$@"
        ;;
    install-artifact-backup)
        install_artifact_backup_scheduler
        ;;
    uninstall-artifact-backup)
        uninstall_artifact_backup_scheduler
        ;;
    status-artifact-backup)
        show_artifact_backup_status
        ;;
    run-artifact-backup)
        run_artifact_backup_now
        ;;
    install-raw-revenue)
        install_raw_revenue_scheduler
        ;;
    uninstall-raw-revenue)
        uninstall_raw_revenue_scheduler
        ;;
    status-raw-revenue)
        show_raw_revenue_status
        ;;
    run-raw-revenue)
        run_raw_revenue_now
        ;;
    *)
        show_help
        ;;
esac
