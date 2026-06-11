# 徵人需求度現況紀錄 - 2026-06-06

記錄時間：2026-06-06 02:18 CST

## 白話狀態

104 徵人需求度已於 2026-06-06 跑完正式 deploy 流程。104 API 可抓，Telegram 已只傳給使用者本人，網頁報表資料已同步到 `stage3_web` 並推送成功。

B 類 latest runtime pointer 已改成本機保留、git 不追蹤。這些檔案仍會在本機被程式更新，但不再造成每次執行後的 git dirty noise。

目前仍需注意兩個 dirty 狀態：root 專案根 `.gitignore` 是既有 dirty；`stage3_web/investment.db` 是 protected DB dirty，不得隨便 stage / commit / restore。

## 工程化狀態

### Root repo

- repo top-level：`/Users/chiufengjui/D槽/Python`
- branch：`main`
- latest commit：`f152b7b4e9 chore: stop tracking hiring latest runtime pointers`
- 已推送：是
- 目前 root 相關 dirty：
  - `台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/.gitignore`

### B 類 latest pointer

已從 git index 移除、保留本機檔案，並由徵人需求度 `.gitignore` 管控為 local-only：

- `data/reports/latest_unlimited_hiring_revenue_report_manifest.json`
- `data/runs/latest_workflow_manifest.json`
- `data/runs/latest_workflow_trace.jsonl`
- `data/runs/latest_workflow_trace_receipt.json`

對應 commit：

- `f152b7b4e9 chore: stop tracking hiring latest runtime pointers`

驗證：

- `venv/bin/python -m unittest tests.test_hiring_workflow_governance tests.test_unlimited_hiring_revenue_report`：PASS，21 tests
- `venv/bin/python check_hiring_runtime_governance.py --output-dir data/runs/runtime_governance_check_latest_pointer_local_only_20260606_010128`：PASS

### 2026-06-06 正式徵人需求度執行

- run_id：`20260606_010313_hiring_demand`
- run_mode：`deploy`
- fetch_date：`2026-06-06`
- CSV：`data/20260606_hiring_demand.csv`
- 104 搜尋關鍵字：
  - `作業員`
  - `包裝員`
  - `產線作業員`
  - `技術員`

104 抓取摘要：

- total_jobs：`10937`
- unique_jobs：`8656`
- filtered_jobs：`9709`
- matched_jobs：`1150`
- matched_company_count：`556`
- job_detail_count：`1150`

deploy checker：

- gate_result：`PASS`
- csv_row_count：`556`
- db_hiring_demand_count：`556`
- db_hiring_demand_jobs_count：`1150`
- typed_blocker_count：`0`
- warning_count：`34`
- warning type：`employee_count_unresolved`
- checker receipt：`data/runs/deploy_check_20260606_015329/hiring_run_check_receipt.json`

### Telegram

本輪要求只傳給使用者本人，因此執行時臨時隱藏 `telegram_recipients.json`，讓 `telegram_sender.py` 只讀 `.env` 的 `TELEGRAM_CHAT_ID`。執行後已還原 `telegram_recipients.json`。

- receipt：`data/reports/20260606/telegram_send_receipt_20260606.json`
- gate_result：`PASS`
- recipient_count：`1`
- recipient：`env_default`
- chat_id_masked：`1100***2834`
- document.sent：`true`
- message_id：`84`

目前 `telegram_recipients.json` 已還原：

- recipient_file_count：`3`
- enabled_count：`2`

### stage3_web / 網頁資料

- stage3_web latest commit：`12ca03d chore: 自動更新徵人需求度資料 2026/06/06 01:53`
- 已推送：是，推送到 `github.com:fengruei9968-wq/stock-data-processing.git main`
- 第一次自動 push 失敗原因：本機 process 資源壓力，`cannot fork() for pack-objects`
- 後續手動重試 `git push origin main`：成功

同步到 stage3_web 的主要資料：

- `stage3_web/hiring_reports/20260606/anomaly_summary_20260606.json`
- `stage3_web/hiring_reports/20260606/unlimited_hiring_revenue_report_manifest_20260606.json`
- `stage3_web/hiring_reports/20260606/unlimited_hiring_revenue_media_receipt_20260606.json`
- `stage3_web/hiring_reports/latest_anomaly_summary.json`
- `stage3_web/hiring_reports/latest_unlimited_hiring_revenue_report_manifest.json`
- `stage3_web/hiring_reports/latest_unlimited_hiring_revenue_media_receipt.json`
- `stage3_web/data/hiring_reports/20260606/...`
- `stage3_web/data/hiring_reports/latest_*.json`

### Protected DB 狀態

`stage3_web` 目前仍有 protected DB dirty：

- `stage3_web/investment.db`

這是 protected DB，不得未經授權 stage、commit、push、restore 或刪除。

### 後續注意

- 若要再次正式跑徵人需求度並只傳給使用者本人，不能直接用原 wrapper 的預設 recipient list；需使用同樣的 single-recipient 控制，或正式新增 wrapper 參數來指定 Telegram recipient mode。
- 若再次遇到 `fork: Resource temporarily unavailable`，先檢查本機 process 壓力，再重試 push；不要把它誤判成 104 或報表邏輯失敗。
- 匿名 CLI 打正式站 `/api/hiring-demand/*` 會回 `401 Unauthorized`，因正式站 API 需要登入；不能用未登入 curl 當網頁資料未更新的證據。
