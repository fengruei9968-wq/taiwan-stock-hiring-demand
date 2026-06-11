# 上市櫃公司徵人需求度擷取模組

## 功能說明

從 104 人力銀行搜尋台股上市櫃/興櫃公司的作業員/包裝員類職缺，計算各公司的徵人需求度（需求人數 / 員工人數），並寫入資料庫供網頁展示。

2026-05-15 起，本資料夾位於正式專案根目錄底下，並管理徵人需求度與月營收摘要 pipeline；`stage3_web` 只保留網站展示與 `investment.db`。

2026-06-05 起，每日 wrapper 採徵人需求度 Harness Runtime：先用 `probe_104_search_api.py` 實際 probe 104 搜尋 API，依 `hiring_recovery_policy.json` 的 typed failure 執行 bounded retry 或安全停止。員工人數 fallback 縮減為 104 搜尋結果本身員工數與 Google，不再使用 104 公司頁 employee API 或 MOPS。

## 檔案清單

| 檔案 | 功能 |
|-----|------|
| `fetch_hiring_demand.py` | 主爬蟲程式 |
| `probe_104_search_api.py` | 104 搜尋 API preflight sensor；輸出 `api_probe_receipt_attempt_*.json` |
| `hiring_recovery_policy.json` | typed failure 到 recovery action 的路由表 |
| `config.yaml` | 設定檔（關鍵字、API 參數、路徑） |
| `com.hiring.demand.updater.plist` | macOS launchd 排程（每天 11:30） |
| `run_hiring_demand.sh` | 包裝腳本（環境檢查 + 失敗通知） |
| `fetch_monthly_revenue.py` | FinMind 上市/上櫃月營收摘要擷取，寫入 `stage3_web/investment.db` |
| `fetch_emerging_revenue.py` | MoneyDJ 興櫃月營收摘要擷取，補 `monthly_revenue_summary` |
| `run_monthly_revenue.sh` | 月營收包裝腳本（每週一 11:30 launchd 呼叫） |
| `com.monthly.revenue.updater.plist` | macOS launchd 月營收排程來源檔 |
| `fetch_stock_monthly_revenue_raw.py` | 個股 raw 月營收擷取；上市 / 上櫃以 MOPS CSV 為主、缺月可補 FinMind，興櫃以 MOPS rotc CSV 為主、rotc HTML 備援，寫入 `stock_monthly_revenue` |
| `run_stock_monthly_revenue_raw.sh` | raw 月營收包裝腳本；預設日期範圍 `2021-01` 到上一個完整月份，支援 `RAW_REVENUE_MISSING_ONLY=1` 缺月補跑，預設不自動 commit/push |
| `com.stock.monthly.revenue.raw.updater.plist` | raw 月營收 launchd 排程來源檔（每月 5 號 10:10，上市 / 上櫃） |
| `com.stock.monthly.revenue.raw.emerging.updater.plist` | raw 月營收 launchd 排程來源檔（每月 10 號 10:10，興櫃） |
| `com.stock.monthly.revenue.raw.missing.retry.plist` | raw 月營收 launchd 排程來源檔（每月 15 號 10:10，全市場缺月補跑） |
| `generate_unlimited_hiring_revenue_report.py` | 產出人數不限公司近六月營收 HTML / CSV / anomaly summary 與月營收 DB 快照 CSV |
| `check_unlimited_hiring_revenue_report.py` | 報表與月營收快照 read-only checker |
| `telegram_sender.py` | 發送 Telegram 測試文字 / PNG / `sendDocument` 高清 PNG；支援 `telegram_recipients.json` 多接收者，並產生遮罩 receipt |
| `telegram_recipient_probe.py` | 讀取 Telegram `/start` updates，維護本機 ignored `telegram_recipients.json` |
| `run_telegram_recipient_probe.sh` | 每小時 Telegram recipient probe wrapper；只更新收件者，不發 PNG、不部署 |
| `com.hiring.telegram.recipient.probe.plist` | 每 1 小時 launchd recipient probe 排程 |
| `backup_hiring_daily_artifacts.sh` | 每日產物 SSD copy-only 備份；只備份一個月前 artifacts，不刪本機、不搬本機 |
| `com.hiring.daily.artifacts.backup.plist` | 每月 5 號 20:00 launchd 每日產物 SSD 備份排程 |
| `telegram_recipients.example.json` | 多接收者清單範例；正式 `telegram_recipients.json` 不得 commit |
| `HIRING_DEMAND_PITFALLS.md` | 徵人需求度踩坑紀錄；Telegram receipt / masking / handoff 類重複問題需同步到此 |
| `../tools/create_ascii_handoff.py` | 將深層或中文 artifact 複製成 `/tmp` ASCII 可點擊 handoff link |
| `install_scheduler.sh` | 排程安裝/移除腳本 |
| `CLAUDE_hiring_demand.md` | 本文件 |
| `data/` | CSV 輸出目錄 |
| `Backup/` | 程式備份目錄 |

## 執行方式

```bash
cd /Users/chiufengjui/D槽/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度
python3 fetch_hiring_demand.py
```

## raw 月營收來源規則（2026-05-25）

白話：上市、上櫃月營收以 MOPS 官方月營收 CSV 為主；若 MOPS 該公司缺月份，允許用 FinMind 補缺月。興櫃月營收先抓 MOPS `rotc` CSV；若 CSV 抓不到或沒有可比對資料，再用 MOPS `rotc` 月營收 HTML 頁作備援。

工程化：

- 上市：`https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{民國年}_{月份}.csv`
- 上櫃：`https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{民國年}_{月份}.csv`
- 興櫃主來源：`https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_{民國年}_{月份}.csv`
- 興櫃備援來源：`https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_{民國年}_{月份}_0.html`
- 上市 / 上櫃缺月備援：FinMind `TaiwanStockMonthRevenue` API，只補 MOPS 未覆蓋月份；同月同公司若 MOPS 與 FinMind 同時存在，網站 API 以 MOPS 優先。
- 年份使用民國年，例如 `2026/04` 對應 `115_4`。
- 公司範圍以最新 stock code CSV 為準；DR 股排除不下載月營收，判斷方式為公司簡稱或全名以 `-DR` 結尾。
- 擷取欄位為 `營業收入-當月營收`，CSV 原始單位為千元，寫入 `stock_monthly_revenue.revenue_unit='thousand_twd'`。
- 每月 5 號更新上市 / 上櫃；每月 10 號更新興櫃；每月 15 號以 `RAW_REVENUE_MISSING_ONLY=1` 掃描上市 / 上櫃 / 興櫃缺月公司並補跑。
- 每次 wrapper 排程執行範圍預設為 `2021-01` 到上一個完整月份，避免把尚未公告的執行當月誤判為缺月；手動可用 `RAW_REVENUE_END_MONTH=YYYY-MM` 覆蓋。
- 存貨與固定資產網頁透過 `stage3_web` 的 `/api/stock-revenue/<stock_code>` 讀 `stage3_web/investment.db.stock_monthly_revenue`；該 raw table 由本資料夾 `fetch_stock_monthly_revenue_raw.py` 更新。

## 三層治理規則（2026-05-13）

白話：徵人需求度不能只用「爬蟲成功」當完成。成功 run 必須留下 manifest，checker 必須依 mode 驗 CSV / manifest；`write-db` 與 `deploy` 還必須確認 DB 彙總與職缺明細一致。預設不自動部署，只有明確開啟 deploy mode 且 checker PASS 才可 commit / push。

工程化：

- active truth：`CURRENT_HIRING_DEMAND_EXECUTION.md`
- run manifest：`data/runs/{run_id}/hiring_run_manifest.json`
- latest manifest：`data/runs/latest_hiring_run_manifest.json`
- workflow manifest：`data/runs/{run_id}/workflow_manifest.json`
- local trace：`data/runs/{run_id}/workflow_trace.jsonl`
- trace receipt：`data/runs/{run_id}/workflow_trace_receipt.json`
- checker：`check_hiring_demand_run.py`
- runtime governance checker：`check_hiring_runtime_governance.py`
- 人數不限營收報表：`data/reports/{YYYYMMDD}/unlimited_hiring_revenue_report_{YYYYMMDD}.html`
- 今日新增公司 CSV：`data/reports/{YYYYMMDD}/new_unlimited_companies_{YYYYMMDD}.csv`
- 月營收 DB 快照 CSV：`data/revenue_snapshots/monthly_revenue_summary_{YYYYMMDD}.csv`
- 月營收快照 manifest：`data/revenue_snapshots/monthly_revenue_snapshot_manifest_{YYYYMMDD}.json`
- 104 API probe receipt：`data/runs/api_probe_*/api_probe_receipt_attempt_*.json`
- raw 月營收 CSV / receipt：`data/stock_monthly_revenue_raw/{YYYYMMDD}/stock_monthly_revenue_raw_{YYYYMMDD}.csv` 與 `stock_monthly_revenue_raw_receipt_{YYYYMMDD}.json`
- 每日產物 SSD copy-only 備份：每月 5 號 20:00 執行 `backup_hiring_daily_artifacts.sh`，把一個月前的 `data/runs/`、`data/reports/YYYYMMDD/`、`data/revenue_snapshots/`、`data/stock_monthly_revenue_raw/` 複製到 `/Volumes/Extreme SSD/Backup/徵人需求度每日產物Backup/{YYYYMM}/backup_run_{run_id}/`；不刪本機、不搬本機、不碰 `stage3_web`。
- 報表 checker：`check_unlimited_hiring_revenue_report.py`
- AI Runtime Governance 文件：`docs/ai_runtime_governance/`
- tests：`tests/test_hiring_demand_checker.py`、`tests/test_hiring_manifest.py`、`tests/test_hiring_runtime_governance.py`、`tests/test_hiring_workflow_governance.py`、`tests/test_hiring_harness_runtime.py`、`tests/test_unlimited_hiring_revenue_report.py`

外部 runtime 邊界：

- OPA、Temporal、Langfuse、Great Expectations、Prefect、Dagster、Argo Workflows、OpenTelemetry、Superpowers 只作概念參考。
- 本資料夾不得因治理導入而安裝、啟動或依賴上述外部服務。
- 治理落地只能用本地文件、manifest、checker、receipt、harness/test 與 closeout evidence。

### mode 邊界

| mode | 說明 |
|---|---|
| `scrape-only` | 只擷取 / 產 CSV / manifest，不寫 DB、不 deploy |
| `write-db` | 預設模式，寫 CSV、`investment.db`、`hiring_demand_jobs`，跑 checker，不 deploy |
| `deploy` | 只有設定 `HIRING_DEMAND_DEPLOY_MODE=deploy` 時才允許，且必須先通過 checker |

### 完成 gate

1. `fetch_hiring_demand.py` 成功後必須寫 manifest。
2. manifest 必須記錄 `governance_contract_id`、`ai_runtime_governance`、`lineage`。
3. 每次成功 run 必須同步寫 `workflow_manifest.json`、`workflow_trace.jsonl`、`workflow_trace_receipt.json`。
4. `check_hiring_demand_run.py` 必須 PASS。
5. checker 必須驗 CSV schema、row count、`999.0` / `998.0` 特殊值；`write-db` / `deploy` 另驗 DB 當日資料、職缺明細 coverage、CSV / DB 欄位一致。
6. `check_hiring_runtime_governance.py` 必須 PASS，確認三層治理文件與 tests 存在。
7. 每日更新後必須產出人數不限公司近三月營收報表與月營收 DB 快照 CSV，並由 `check_unlimited_hiring_revenue_report.py` 驗證 CSV / DB parity。
8. deploy 前必須再跑 `--require-deploy-mode`。
9. 自動部署只能 stage / commit / push `stage3_web/hiring_reports` 與 `stage3_web/data/hiring_reports`，若已有 staged changes 或出現其他 staged file，必須停止。
10. 對話交付 PNG / PDF / HTML / CSV / JSON receipt 時，若原始路徑位於中文資料夾或深層 `data/` artifact root，必須先用 `../tools/create_ascii_handoff.py` 產生 `/tmp` ASCII copy，再把 `/tmp` Markdown 連結放在回覆最前面。

## 資料流程

```
104 搜尋 API → 篩選職缺 → 比對股票代碼表 → 計算需求度 → CSV + investment.db
```

## 搜尋策略

以關鍵字全域搜尋（非逐間公司），大幅減少 API 請求次數：
- 搜尋關鍵字：作業員、包裝員、產線作業員
- 二次篩選：職缺名稱包含「作業員/包裝員/產線」，排除「主管/組長/經理」
- 用公司名稱比對股票代碼表（精確 → 去後綴 → 包含匹配）

## 員工人數查詢策略

縮減查詢來源，降低非 JSON / Cloudflare HTML 雜訊：
1. 104 搜尋結果（範圍值取中間）
2. Google 搜尋

## 「不限」處理

- `demand_ratio = 999.0` 表示「人數不限」
- 前端顯示「人數不限」文字
- 篩選時一律顯示（視為高需求）
- 報表規則以 `不限職缺數 > 0` 判斷人數不限公司；這會納入同時有明確需求人數與不限職缺的公司。

## 資料庫

在 `investment.db` 中的 `hiring_demand` 表格。

## 排程

- **每天 11:30** 自動執行
- 透過 `run_hiring_demand.sh` 包裝腳本執行，執行前檢查：
  1. 磁碟 `/Volumes/D` 是否掛載
  2. 程式目錄是否存在
  3. Python venv 是否存在
  4. 主程式是否存在
  5. checker 是否存在
  6. 104 搜尋 API probe 是否 PASS；若 typed failure 可重試，依 bounded recovery loop 重試
- 任何檢查失敗或程式異常 → 發送雙通道通知（macOS + iPhone ntfy）
- 爬蟲成功後必須先跑 checker；預設略過 commit / push。
- checker PASS 後會產出本地人數不限公司近六月營收 HTML 報表、今日新增不限徵才、營收雙指標改善觀察與營收強勢延續公司 CSV，並跑報表 checker。
- Telegram 每日自動推播可由 `HIRING_TELEGRAM_SEND_MODE=enabled` 啟用；wrapper 會使用 `sendDocument` 發送 PNG。
- 預設接收者是 `.env` 的 `TELEGRAM_CHAT_ID`；若本機存在 `telegram_recipients.json`，會 fan-out 給 `enabled=true` 的接收者。
- `telegram_recipients.json` 存放朋友或群組 chat id，必須保持 ignored；只可 commit `telegram_recipients.example.json`。
- `telegram_recipient_probe.py` 可在朋友對 bot 發 `/start` 後讀取 getUpdates 並寫入本機 recipient list；它不是長駐 bot runtime。
- `com.hiring.telegram.recipient.probe.plist` 每 1 小時呼叫 `run_telegram_recipient_probe.sh`。這個 hourly probe 只更新 `telegram_recipients.json` 與 receipt，不會發 PNG、不會跑主爬蟲、不會部署。
- Telegram / `.env` / receipt 相關踩坑必須同步到 `HIRING_DEMAND_PITFALLS.md`；修改 sender / probe 前要讀該檔，並確認 `sanitize_text()` 不會因空 `chat_id` 破壞 JSON receipt。
- 手機閱讀版 PNG 使用 `--png-scale 2 --png-dpi 300` 產生，再用 `sendDocument` 文件模式發送，避免 `sendPhoto` 壓縮造成點開後模糊。
- PNG 定案字型為 `hiragino_mixed`，預設中文與圖表月份使用 `Hiragino Sans GB`，英文與數字使用 `SFNS`。A/B 測試仍可使用 `--png-font-profile system_heiti|sf_mixed|sf_mono_numbers|hiragino_mixed`，receipt 會記錄 `png_font_profile` 與實際 `png_fonts` 路徑；圖表月份標籤的「月」必須使用 `chart_month` 中文字型，不得使用 SF 英文字型。
- 對話交付本地 artifact 時必須提供 `/tmp` ASCII 可點擊連結；原始 repo 路徑保留作 durable evidence，不得成為唯一交付方式。
- 若要部署，需明確設定 `HIRING_DEMAND_DEPLOY_MODE=deploy`。
- launchd plist 安裝到 `~/Library/LaunchAgents/`
- 日誌：`launchd_run.log`（包裝腳本）、`launchd_stdout.log` / `launchd_stderr.log`（launchd）

## 通知系統（雙通道）

| 通道 | 方式 | 目標 |
|------|------|------|
| macOS | osascript 系統通知 | 電腦端（`fetch_hiring_demand.py` 內建 + `run_hiring_demand.sh`） |
| iPhone | ntfy.sh 推播 | 手機端（自動載入共用模組 `tools/notify.py`） |

- 設定: `台股投資資訊系統_完整專案/.env` → `NTFY_TOPIC`
- Fallback: 若 `tools/notify.py` 不存在 → 自動退回純 macOS 通知（不影響程式執行）
- 通知時機: 更新完成、更新失敗、Railway 部署成功/失敗

## 備份紀錄

| 日期 | 版本 | 說明 |
|-----|------|------|
| 2026-02-07 | 初版 | 建立模組 |
| 2026-02-08 | v2 | 修復 hiring_demand / hiring_demand_jobs 資料不一致（save_to_database 加 DELETE） |
| 2026-02-08 | v3 | 排程改為每天 11:30、新增 run_hiring_demand.sh 包裝腳本 |
| 2026-02-25 | v3.1 | 通知改為雙通道（macOS + ntfy iPhone），整合共用 `tools/notify.py` |
| 2026-05-13 | v4 | 新增 active truth、run manifest、read-only checker、negative controls；deploy 改為 explicit mode |
| 2026-05-15 | v4.1 | 新增 workflow manifest schema 對齊與本地 JSONL trace receipt |
| 2026-05-15 | v4.2 | 新增人數不限公司近三月營收報表、今日新增公司 CSV、report checker 與 tests |
| 2026-05-15 | v4.3 | 新增本機 artifact `/tmp` ASCII 可點擊 handoff 規則 |
| 2026-05-16 | v4.4 | 新增 Telegram 手動測試 sender 與遮罩 receipt |
| 2026-05-16 | v4.5 | 新增多接收者 Telegram fan-out、recipient probe 與 Telegram masking 踩坑紀錄 |
| 2026-05-16 | v4.6 | 新增每小時 Telegram recipient probe launchd 排程 |

> **最後更新：2026-05-16**
