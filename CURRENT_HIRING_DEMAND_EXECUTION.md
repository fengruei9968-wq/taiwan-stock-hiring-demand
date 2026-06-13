# 上市櫃公司徵人需求度 Active Truth

更新日期：2026-06-09

## 白話結論

徵人需求度流程現在分成三種模式：只擷取檢查、寫入 DB、部署。每日正式排程應在 checker、報表 checker、PNG/PDF media checker 都 PASS 後，用 `sendDocument` 發送 PNG 到 Telegram，並把本輪摘要同步到 `stage3_web` 後 commit / push 到網頁端。這兩件事不是由報表 PASS 自動代表，必須由 `.env` 開關與本輪 receipt / git evidence 證明。

2026-06-05 harness runtime active setting：每日 wrapper 不再用 `ping www.104.com.tw` 判斷 104 是否可抓，改用 `probe_104_search_api.py` 實際呼叫 `https://www.104.com.tw/jobs/search/api/jobs`，產生 `api_probe_receipt_attempt_*.json`。typed failure 會依 `hiring_recovery_policy.json` 路由到 `wait_and_retry`、`keyword_probe_then_retry`、`stop_for_code_review` 或 `stop_without_mutating_user_files`；這些分類是修復路由，不是只供回報。員工人數 fallback 縮減為「104 搜尋結果本身員工數 -> Google」，不再用 104 公司頁 employee API 或 MOPS，避免非 JSON / Cloudflare HTML 造成大量低品質 warning。

2026-06-06 web publication active setting：正式 `/api/hiring-demand` 優先讀 `stage3_web/hiring_reports/latest_hiring_demand_web_data.json`，缺檔或壞檔才 fallback 到 `stage3_web/investment.db`。每日 web sync 必須同時同步異常摘要與完整表格 JSON：`hiring_demand_web_data_{YYYYMMDD}.json`、`latest_hiring_demand_web_data.json`，並同步到 `stage3_web/hiring_reports/` 與 `stage3_web/data/hiring_reports/`。這條規則是為了避免「104 已抓到、DB 本機有資料，但正式網頁仍讀舊 deployed DB」。

2026-06-09 monthly revenue web publication active setting：正式 `/api/hiring-demand/revenue-batch` 優先讀 `stage3_web/hiring_reports/latest_hiring_revenue_batch.json`，缺檔或壞檔才 fallback 到 `stage3_web/investment.db.monthly_revenue_summary`。本機 DB 仍保留月營收資料作原始查詢與 fallback；但網頁發佈用的上市 / 上櫃 / 興櫃月營收、MoM%、YoY% 必須由小型 JSON artifact 發佈，不得為了更新徵人需求度頁面而 commit / push protected `investment.db`。

2026-05-19 active setting：每日正式自動發送 / 部署需在 `上市櫃公司徵人需求度/.env` 設定 `HIRING_TELEGRAM_SEND_MODE=enabled` 與 `HIRING_DEMAND_DEPLOY_MODE=deploy`。若缺任一設定，wrapper 仍會產出本機 CSV / DB / PNG / PDF / web sync artifact，但不會送 Telegram 或 push 網頁；closeout 不得宣稱「手機與網頁端已完成」。

2026-05-15 起，本資料夾已移入正式專案根目錄底下；月營收摘要擷取也歸到本資料夾管理。`stage3_web` 保留網站 route、模板、CSS、相容 wrapper 與 `investment.db`，不再作為月營收擷取腳本的主要維護位置。

2026-05-25 raw 月營收 active setting：上市 / 上櫃每月 5 號抓 MOPS CSV，MOPS 缺月可用 FinMind 補；興櫃每月 10 號抓 MOPS `rotc` CSV，CSV 不可用或無可比對資料時用使用者補充的 `rotc` HTML `_0.html` 備援；每月 15 號全市場以 missing-only 模式掃描 `stock_monthly_revenue` 缺月公司並補跑。wrapper 預設抓到上一個完整月份，避免把尚未公告的執行當月誤判為缺月。存貨與固定資產網頁引用月營收時，透過 `stage3_web` `/api/stock-revenue/<stock_code>` 讀 `stage3_web/investment.db.stock_monthly_revenue`，該 raw table 由本資料夾 raw updater 更新。

## 三種模式

| mode | 用途 | 允許動作 | 不允許動作 |
|---|---|---|---|
| `scrape-only` | 只產 CSV / manifest 做檢查 | 讀 104 / Stock_codes、寫 CSV、寫 manifest | 寫 DB、commit、push |
| `write-db` | 排程預設模式 | 寫 CSV、寫 `investment.db`、寫職缺明細、跑 checker | commit、push |
| `deploy` | 明確部署模式 | checker PASS 後，只 stage / commit / push `stage3_web/hiring_reports`、`stage3_web/data/hiring_reports` | 帶入 DB、其他 staged changes、未驗證直接 push |

## Active Gate

1. `fetch_hiring_demand.py` 成功後必須輸出：
   - `data/runs/{run_id}/hiring_run_manifest.json`
   - `data/runs/latest_hiring_run_manifest.json`
   - `data/runs/{run_id}/workflow_manifest.json`
   - `data/runs/{run_id}/workflow_trace.jsonl`
   - `data/runs/{run_id}/workflow_trace_receipt.json`
   - `data/runs/latest_workflow_manifest.json`
   - `data/runs/latest_workflow_trace.jsonl`
   - `data/runs/latest_workflow_trace_receipt.json`
   - manifest 內必須包含 `governance_contract_id`、`ai_runtime_governance`、`lineage`
2. `check_hiring_demand_run.py` 必須讀 manifest 並依 mode 驗：
   - 共通：CSV schema、CSV row count、`999.0` / `998.0` 特殊值規則。
   - `write-db` / `deploy`：`hiring_demand` 當日 DB row count、`hiring_demand_jobs` 職缺明細 coverage、CSV / DB 欄位值一致。
3. checker PASS 才能 closeout。
4. deploy 前必須額外通過 `--require-deploy-mode`，且 `manifest.run_mode=deploy`。
5. `check_hiring_runtime_governance.py` 必須能驗出本資料夾內三層治理文件、checker、manifest helper 與 tests 都存在。
6. 核心 checker PASS 後，`generate_unlimited_hiring_revenue_report.py` 必須產出人數不限公司近三月營收 HTML 報表、CSV 與 anomaly summary：
   - `data/reports/{YYYYMMDD}/unlimited_hiring_revenue_report_{YYYYMMDD}.html`
   - `data/reports/{YYYYMMDD}/new_unlimited_companies_{YYYYMMDD}.csv`
   - `data/reports/{YYYYMMDD}/current_month_revenue_increase_companies_{YYYYMMDD}.csv`
   - `data/reports/{YYYYMMDD}/revenue_turnaround_companies_{YYYYMMDD}.csv`
   - `data/reports/{YYYYMMDD}/revenue_growth_companies_{YYYYMMDD}.csv`
   - `data/reports/{YYYYMMDD}/anomaly_summary_{YYYYMMDD}.json`
   - `data/reports/{YYYYMMDD}/unlimited_hiring_revenue_report_manifest_{YYYYMMDD}.json`
   - `data/revenue_snapshots/monthly_revenue_summary_{YYYYMMDD}.csv`
   - `data/revenue_snapshots/monthly_revenue_snapshot_manifest_{YYYYMMDD}.json`
7. `check_unlimited_hiring_revenue_report.py` 必須驗：
   - 人數不限公司定義為 `不限職缺數 > 0`，不是只看 `徵人需求度 = 999.0`。
   - 今日新增公司 CSV 必須等於最新日與前一日 unlimited set 差集，且逐列標示 `今日新增公司=YES`。
   - `monthly_revenue_summary` 必須覆蓋所有人數不限公司。
   - 月營收快照 CSV 必須和 `stage3_web/investment.db` 的 `monthly_revenue_summary` row count、stock_code、m1/m2/m3 MoM / YoY / updated_at 完全一致。
   - HTML / CSV / manifest artifact path 都存在。
8. PNG 版面定案規格（2026-05-15）：
   - 主要人讀 artifact 是 PNG，`primary_human_artifact=png`。
   - `render_unlimited_hiring_revenue_media.py` 必須產出 `unlimited_hiring_revenue_report_{YYYYMMDD}.png`、PDF 與 `unlimited_hiring_revenue_media_receipt_{YYYYMMDD}.json`。
   - PNG 模式固定為 `png_mode=anomaly_detection_summary`。
   - 版面固定為監控摘要：上方指標卡、下方四個觀察區塊，MoM / YoY 以近六月直方圖呈現。
   - 四個區塊名稱與順序固定為「今日新增不限徵才」、「營收轉正觀察」、「營收雙指標改善觀察」、「營收強勢延續公司」。
   - 「營收雙指標改善觀察」定義為不限徵才、最新月 MoM 與 YoY 均較上月走升，且上月 MoM 或 YoY 至少一項偏弱（<= 0）。
   - 「營收轉正觀察」定義為不限徵才、最新月 YoY > 0、上月 YoY <= 0、最新月 MoM > 0，且未命中「營收雙指標改善觀察」。
   - 「營收強勢延續公司」定義為不限徵才，且 MoM、YoY 近三個有效月同步走升。
   - `current_month_revenue_increase` 必須全數呈現，不得只列前 10 家；receipt 必須記錄 `total_count` 與 `displayed_count`。
   - 表格下方不得再放「完整清單請看 PDF/HTML/CSV」類備註。
   - PNG 最下方文字固定為 `同步更新至徵人需求度網頁` 並附 `https://financial-report-data-processing.up.railway.app/hiring-demand`。
   - PNG 目前定案字型為 `hiragino_mixed`，預設中文與圖表月份使用 `Hiragino Sans GB`，英文與數字使用 `SFNS`。A/B 測試仍可用 `--png-font-profile system_heiti|sf_mixed|sf_mono_numbers|hiragino_mixed`；receipt 必須記錄 `png_font_profile` 與 `png_fonts`，讓中文字、英文字與數字字型可追蹤。圖表月份標籤的「月」必須使用中文字型 `chart_month`，不得跟著 `MoM` / `YoY` 使用 SF 英文字型，避免手機端亂碼。
9. 對話交付 artifact 時必須產出可點擊 ASCII handoff：
   - PNG / PDF / HTML / CSV / JSON receipt 若原始路徑在本中文資料夾或深層 `data/` artifact root，回覆前必須用專案根目錄的 `tools/create_ascii_handoff.py` 複製到 `/tmp/<short_ascii_name>`。
   - 回覆中優先提供 `/tmp` Markdown 連結，例如 `[hiring_report.png](/tmp/hiring_report.png)`；原始 repo 路徑只作 durable evidence，不作唯一交付連結。
   - 這條規則只改善使用者開檔體驗，不代表 checker PASS，也不取代 manifest / receipt / report checker。
10. Telegram 發送邊界（2026-05-16）：
   - 每日 wrapper 在 `HIRING_TELEGRAM_SEND_MODE=enabled` 時會呼叫 `telegram_sender.py`，用 `sendDocument` 發送 PNG。
   - 預設會送到 `.env` 的 `TELEGRAM_CHAT_ID`；若存在本機 ignored `telegram_recipients.json`，會同時送給其中 `enabled=true` 的接收者。
   - `telegram_recipient_probe.py` 只用來讀 Telegram `/start` updates 並維護本機 `telegram_recipients.json`；不作長駐 bot runtime。
   - 只有使用者明確授權讀取 `.env` 並發送或探測時，才可讀 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`。
   - receipt 必須遮罩 chat id，且不得寫入 bot token。
   - `telegram_recipients.json` 不得 commit；只能 commit `telegram_recipients.example.json` 作 schema 參考。
   - 手機閱讀用 PNG 必須用 `render_unlimited_hiring_revenue_media.py --png-scale 2 --png-dpi 300` 產生高清版，receipt 必須記錄 `png_scale`、`png_dpi`、`png_pixel_width`、`png_pixel_height`。
   - Telegram 圖檔正式採 `sendDocument` 文件模式，避免 `sendPhoto` 壓縮造成手機點開後模糊；receipt 必須記錄 `document_path`、`document_exists`、`document.sent`、`recipient_count` 與每位 recipient 的送達狀態。
   - 每日正式自動發送需設定 `HIRING_TELEGRAM_SEND_MODE=enabled`；缺此設定時，報表與 media checker PASS 只代表本機 PNG/PDF 已產生，不代表 Telegram 已送出。
11. 踩坑紀錄同步邊界（2026-05-16）：
   - Telegram / `.env` / receipt / handoff 類重複問題必須寫入 `HIRING_DEMAND_PITFALLS.md`。
   - 修改 `telegram_sender.py` 或 `telegram_recipient_probe.py` 前必須讀該踩坑紀錄。
   - `sanitize_text()` 類安全遮罩邏輯必須有 regression test，避免空 `chat_id` 破壞 JSON receipt。
   - governance checker 必須檢查踩坑紀錄與 tests marker，不能只靠聊天提醒。
12. Telegram recipient hourly probe（2026-05-16）：
   - `com.hiring.telegram.recipient.probe.plist` 每 1 小時呼叫 `run_telegram_recipient_probe.sh`。
   - hourly probe 只執行 `telegram_recipient_probe.py`，讀 `/start` updates 並更新本機 ignored `telegram_recipients.json`。
   - hourly probe 不得呼叫 `telegram_sender.py`、不得 `--send-document`、不得跑 `fetch_hiring_demand.py`、不得 render PNG、不得 commit / push。
   - 每次 probe 必須寫 `data/runs/telegram_recipient_probe_hourly_*/telegram_recipient_probe_receipt_*.json`，receipt 只能有遮罩後的 chat id。
13. 每日產物 SSD 備份（2026-05-25）：
   - `com.hiring.daily.artifacts.backup.plist` 每月 5 號 20:00 呼叫 `backup_hiring_daily_artifacts.sh`。
   - backup root 固定為 `/Volumes/Extreme SSD/Backup/徵人需求度每日產物Backup`，可用 `HIRING_ARTIFACT_BACKUP_ROOT` 覆蓋。
   - 預設只 copy 一個月前 artifacts，`HIRING_ARTIFACT_BACKUP_RETENTION_DAYS=30`。
   - backup 範圍限 `data/runs/`、`data/reports/YYYYMMDD/`、`data/revenue_snapshots/`、`data/stock_monthly_revenue_raw/`。
   - 邊界：不刪本機、不搬本機、不 restore tracked files、不碰 `stage3_web`、不 commit、不 push。
14. 每日正式 closeout evidence（2026-05-19）：
   - 必須讀 `launchd_run.log` 最後一段，確認沒有 `Telegram sendDocument 未啟用` 或 `未開啟 deploy mode`。
   - 必須有當日 `telegram_send_receipt_YYYYMMDD*.json`，且 `gate_result=PASS`、`dry_run=false`、`document.sent=true`、`recipient_count=2`。
   - Telegram recipients 必須只包含 `.env` 預設接收者與 `Kwolf0 / lin yc`；`Tsaiball / 菜圃` 必須維持 disabled。
   - `hiring_anomaly_web_sync_receipt_YYYYMMDD.json` PASS 只代表本機同步到 `stage3_web`；仍需 `stage3_web` commit / push 證明網頁部署已送出。
   - Railway 未登入 smoke `hiring-demand -> 302 /login`、protected API `401` 只證明 route / auth 邊界在線；不等於登入後人工確認畫面內容。
15. 104 API harness runtime（2026-06-05）：
   - `run_hiring_demand.sh` 執行主爬蟲前必須先跑 `probe_104_search_api.py`。
   - probe receipt 必須記錄 `gate_result`、`failure_type`、`recovery_action`、`http_status`、`content_type`、`job_count`、keyword、endpoint 與 timeout。
   - `cloudflare_challenge`、`http_403`、`http_429`、`network_timeout`、`non_json_response` 預設只允許 bounded `wait_and_retry`，不得加大請求量或改成逐公司搜尋。
   - `empty_jobs` 可做 keyword probe retry；多輪仍空時停止，不得把空結果當成功。
   - `deploy_scope_violation` 必須停止且不得 restore / stage / commit / push 使用者檔案。
   - probe PASS 後才可進 scrape / write-db / deploy 主流程。
16. 網頁表格資料發布閉回路（2026-06-06）：
   - `sync_hiring_anomaly_web_artifacts.py` 必須從本輪 manifest 指向的 `stage3_web/investment.db` 匯出 `hiring_demand` 最新日與 `hiring_demand_jobs` 最新日，寫成 `hiring_demand_web_data_v1` JSON。
   - `hiring_anomaly_web_sync_receipt_YYYYMMDD.json` 的 `copied` 必須包含 `deploy_latest_hiring_web_data` 與 `legacy_data_latest_hiring_web_data`。
   - `stage3_web/app.py` 的 `/api/hiring-demand` 與 `/api/hiring-demand/jobs/<stock_code>` 必須優先讀 `latest_hiring_demand_web_data.json`；DB 只能當 fallback。
   - 正式 closeout 不能只看未登入 smoke；登入後 Chrome gate 必須確認頁面更新日期、公司數，並用本輪新增或指定股票代碼搜尋，例如 `4770`。
   - 若本機 artifact 有公司、正式頁查不到，分類為 `web_data_publication_stale`，修復動作是檢查 web data JSON 是否存在、是否 pushed、Railway 是否部署完成，再重跑 Chrome 搜尋，不得把它誤判為 104 scraping miss。
17. 月營收 batch 網頁發布閉回路（2026-06-09）：
   - `sync_hiring_anomaly_web_artifacts.py` 必須從本輪 manifest 指向的 `stage3_web/investment.db.monthly_revenue_summary` 匯出 `hiring_revenue_batch_v1` JSON。
   - `hiring_anomaly_web_sync_receipt_YYYYMMDD.json` 的 `copied` 必須包含 `deploy_latest_hiring_revenue_batch` 與 `legacy_data_latest_hiring_revenue_batch`。
   - `stage3_web/app.py` 的 `/api/hiring-demand/revenue-batch` 必須優先讀 `latest_hiring_revenue_batch.json`；DB 只能當 fallback。
   - JSON payload 必須保留 `window_months=6`、`count`、`updated_at`，並以股票代碼索引每家公司近六月 `months`、`mom`、`yoy`。
   - 若正式頁有徵人資料但月營收 / MoM / YoY 缺漏，分類為 `revenue_batch_publication_stale`，修復動作是重跑 web sync、確認 JSON 是否 pushed、Railway 是否部署完成；不得用 commit / push `investment.db` 修復。

## Stop Conditions

- 找不到 manifest、CSV 或 Stock_codes source。
- `write-db` / `deploy` 找不到 DB。
- CSV / DB row count 不一致。
- 職缺明細筆數與 CSV `總職缺數` 不一致。
- `999.0` / `998.0` 特殊值不符合語意。
- `scrape-only` 不能部署；它的 DB check 會明確標為 `skipped_scrape_only`。
- stage3_web 已有 staged changes。
- 104 API probe 連續 bounded retry 後仍不是 PASS。
- 自動部署偵測到 staged file 不是 `hiring_reports/` 或 `data/hiring_reports/`。
- 人數不限營收報表缺 `monthly_revenue_summary`。
- 月營收快照 CSV 與 DB `monthly_revenue_summary` 不一致。
- 今日新增公司 CSV 與最新/前一日 CSV 比對結果不一致。
- 報表 HTML、CSV 或 manifest artifact 缺漏。
- 每日正式模式缺 `HIRING_TELEGRAM_SEND_MODE=enabled` 或 `HIRING_DEMAND_DEPLOY_MODE=deploy` 時，不得宣稱 Telegram 或網頁部署完成。
- 缺當日正式 `telegram_send_receipt`、缺 `stage3_web` commit / push，或只有 web sync receipt PASS 時，不得宣稱手機與網頁端已完成。
- `latest_hiring_demand_web_data.json` 缺檔、壞檔、公司數 / 職缺數為 0，或不含當輪 checker 已驗證的指定股票代碼時，不得宣稱網頁表格資料已完成。
- 正式站 Chrome gate 還顯示舊日期或指定股票代碼查不到時，狀態是 `web_data_publication_stale`；不得回報成 104 沒抓到。

## 本輪已落地

- 新增 read-only checker：`check_hiring_demand_run.py`。
- 新增 runtime governance checker：`check_hiring_runtime_governance.py`。
- 新增 manifest helper：`fetch_hiring_demand.py` 成功 run 會寫 manifest。
- 新增 negative-control tests：`tests/test_hiring_demand_checker.py`。
- 新增 manifest contract tests：`tests/test_hiring_manifest.py`。
- 新增 runtime governance tests：`tests/test_hiring_runtime_governance.py`。
- 新增 workflow manifest / JSONL trace：`hiring_workflow_governance.py`。
- 新增 workflow trace tests：`tests/test_hiring_workflow_governance.py`。
- 新增 AI Runtime Governance 文件：`docs/ai_runtime_governance/`。
- 新增人數不限近三月營收報表：`generate_unlimited_hiring_revenue_report.py`。
- 新增報表 read-only checker：`check_unlimited_hiring_revenue_report.py`。
- 新增報表 positive / negative tests：`tests/test_unlimited_hiring_revenue_report.py`。
- 新增月營收 CSV 快照：`data/revenue_snapshots/monthly_revenue_summary_{YYYYMMDD}.csv`。
- 新增月營收快照 manifest：`data/revenue_snapshots/monthly_revenue_snapshot_manifest_{YYYYMMDD}.json`。
- report checker 新增 DB / CSV parity gate：`revenue_snapshot_db_mismatch`、`revenue_snapshot_row_count_mismatch`。
- 新增人數不限異常偵測 PNG / PDF renderer：`render_unlimited_hiring_revenue_media.py`。
- PNG 版面已定案：`anomaly_detection_summary` 卡片版、三類事件 count、公司卡片與 MoM / YoY 直方圖；本月雙增公司全數呈現。
- 新增踩坑紀錄：`HIRING_DEMAND_PITFALLS.md`，記錄 Telegram token / chat id masking 與 receipt 破壞 regression。
- 新增 hourly recipient probe：`run_telegram_recipient_probe.sh` 與 `com.hiring.telegram.recipient.probe.plist`，每 1 小時自動讀 `/start` 並更新 recipient list。
- 更新 wrapper：`run_hiring_demand.sh` 預設不 deploy；deploy 需明確環境變數。
- 搬遷資料夾：正式位置為 `台股投資資訊系統_完整專案/上市櫃公司徵人需求度`。
- 月營收 pipeline 歸戶：`fetch_monthly_revenue.py`、`fetch_emerging_revenue.py`、`run_monthly_revenue.sh` 由本資料夾管理，DB 仍寫入 `stage3_web/investment.db`。
- raw 月營收 pipeline 歸戶：`fetch_stock_monthly_revenue_raw.py` 與 `run_stock_monthly_revenue_raw.sh` 由本資料夾管理，寫入 `stage3_web/investment.db.stock_monthly_revenue`；5 號上市/上櫃、10 號興櫃、15 號全市場缺月補跑。
- 新增 104 API harness runtime：`probe_104_search_api.py`、`hiring_recovery_policy.json`、wrapper bounded recovery loop 與 `tests/test_hiring_harness_runtime.py`。
- 員工人數 fallback 縮減為 104 搜尋結果與 Google；104 公司頁 employee API / MOPS 不再是主流程 fallback。
- 新增網頁表格小型 deploy artifact：`latest_hiring_demand_web_data.json` 與 `hiring_demand_web_data_{YYYYMMDD}.json`，讓正式 `/api/hiring-demand` 不再依賴 protected `investment.db` 是否被 push。
- 新增徵人需求度頁月營收小型 deploy artifact：`latest_hiring_revenue_batch.json` 與 `hiring_revenue_batch_{YYYYMMDD}.json`，讓正式 `/api/hiring-demand/revenue-batch` 不再依賴 protected `investment.db` 是否被 push。
- 新增 web publication regression：`stage3_web/tests/test_hiring_web_data_api.py`，驗證 `4770` 可由 deployable JSON 被 `/api/hiring-demand` 與 `/api/hiring-demand/jobs/4770` 讀到。
- 舊路徑只保留 compatibility shim：避免 launchd 已載入舊 ProgramArguments 時找不到 `run_hiring_demand.sh`；不得再把舊路徑當 active truth。

## 操作方式

一般排程 / 手動寫 DB：

```bash
cd /Users/chiufengjui/D槽/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度
./venv/bin/python3 fetch_hiring_demand.py
./venv/bin/python3 check_hiring_demand_run.py \
  --manifest data/runs/latest_hiring_run_manifest.json \
  --output-dir data/runs/manual_check_$(date +%Y%m%d_%H%M%S)
```

治理文件 / gate 檢查：

```bash
./venv/bin/python3 check_hiring_runtime_governance.py \
  --root . \
  --output-dir data/runs/governance_check_$(date +%Y%m%d_%H%M%S)
```

人數不限公司近三月營收報表：

```bash
./venv/bin/python3 generate_unlimited_hiring_revenue_report.py \
  --data-dir data \
  --db-path /Users/chiufengjui/D槽/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/stage3_web/investment.db \
  --latest-manifest-path data/reports/latest_unlimited_hiring_revenue_report_manifest.json
./venv/bin/python3 check_unlimited_hiring_revenue_report.py \
  --manifest data/reports/latest_unlimited_hiring_revenue_report_manifest.json \
  --output-dir data/reports/report_check_$(date +%Y%m%d_%H%M%S)
./venv/bin/python3 render_unlimited_hiring_revenue_media.py \
  --manifest data/reports/latest_unlimited_hiring_revenue_report_manifest.json
```

明確允許 wrapper 部署：

```bash
HIRING_TELEGRAM_SEND_MODE=enabled HIRING_DEMAND_DEPLOY_MODE=deploy ./run_hiring_demand.sh
```

## 還不能代表什麼

- checker PASS 只代表本輪 CSV / DB / jobs 明細一致，不代表 104 或 Google 的外部資料完全正確。
- 員工人數查不到會列 warning；目前只代表 104 搜尋結果與 Google 都未取得，不代表公司完全沒有員工資料。
- deploy mode 只允許處理 `stage3_web/hiring_reports`、`stage3_web/data/hiring_reports`，不處理 DB 或其他 stage3_web 檔案。
- AI Runtime Governance 只在本資料夾內落地為本地文件、checker、manifest 與 tests；不代表已安裝或啟動任何外部 runtime。
- `workflow_manifest.json` / `workflow_trace.jsonl` 是本地 trace evidence；它的 `PENDING_CHECKER` 代表還要以 `check_hiring_demand_run.py` receipt 判斷 closeout，不得單獨當 PASS。
- 人數不限異常偵測摘要已接入每日 wrapper；但只有 `HIRING_TELEGRAM_SEND_MODE=enabled` 且當日正式 `telegram_send_receipt` PASS 時，才代表當日真的送出 Telegram。
- 網頁摘要已接入 wrapper web sync；但只有 `HIRING_DEMAND_DEPLOY_MODE=deploy` 且 `stage3_web` commit / push 完成時，才代表當日真的推到網頁端。
- 網頁表格 JSON 推到 `stage3_web` 後，仍需等 Railway 部署完成；Chrome 若短時間內還看到舊日期，應 bounded recheck，而不是重新爬 104。
- 月營收快照 CSV 只證明本輪採用的 DB 快取資料可追溯，不代表 FinMind / MoneyDJ 原始資料一定正確，也不代表月營收已更新到最新公告月份。
- `/tmp` ASCII handoff copy 只代表 Codex 對話中可直接點擊開啟，不是 durable source of truth；正式 evidence 仍以本資料夾 `data/` 下的 manifest、receipt、checker output 與原始 artifact 為準。
