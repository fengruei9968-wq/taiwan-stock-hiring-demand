# 徵人需求度治理硬化檢查表

更新日期：2026-06-05

## 白話結論

目前徵人需求度已經從「爬蟲成功就算完成」改成「要有 manifest、checker receipt、negative controls 才能 closeout」。仍要注意：checker PASS 只證明本地資料一致，不保證外部 104 或員工人數來源完全正確。

## 檢查表

| 規則 | 狀態 | evidence |
|---|---|---|
| 三種 mode 邊界 | 已落地 | `CURRENT_HIRING_DEMAND_EXECUTION.md`、`fetch_hiring_demand.py` |
| run manifest | 已落地 | `data/runs/{run_id}/hiring_run_manifest.json` |
| 104 API probe sensor | 已落地 | `probe_104_search_api.py`、`api_probe_receipt_attempt_*.json` |
| typed failure recovery policy | 已落地 | `hiring_recovery_policy.json` |
| wrapper bounded recovery loop | 已落地 | `run_hiring_demand.sh`、`HIRING_104_PROBE_MAX_ATTEMPTS` |
| employee fallback 縮減 | 已落地 | 104 搜尋結果員工數 -> Google；不再用 104 公司頁 API / MOPS |
| latest manifest | 已落地 | `data/runs/latest_hiring_run_manifest.json` |
| workflow manifest schema 對齊 | 已落地 | `data/runs/{run_id}/workflow_manifest.json`、`data/runs/latest_workflow_manifest.json` |
| local JSONL trace | 已落地 | `data/runs/{run_id}/workflow_trace.jsonl`、`workflow_trace_receipt.json` |
| read-only checker | 已落地 | `check_hiring_demand_run.py` |
| checker receipt | 已落地 | `hiring_run_check_receipt.json` / `.md` |
| typed blockers | 已落地 | `typed_blockers.csv` |
| warnings | 已落地 | `warnings.csv` |
| CSV schema expectation | 已落地 | `EXPECTED_HEADER` |
| 999 / 998 特殊值規則 | 已落地 | `validate_special_values()` |
| DB row count / value parity | 已落地 | `validate_csv_db_alignment()` |
| jobs coverage | 已落地 | `job_detail_coverage_mismatch` |
| deploy explicit gate | 已落地 | `--require-deploy-mode`、`HIRING_DEMAND_DEPLOY_MODE=deploy` |
| positive control | 已落地 | `test_valid_csv_db_and_jobs_pass` |
| negative controls | 已落地 | row count mismatch、invalid 999、deploy mode、scrape-only |
| AI runtime governance docs | 已落地 | `docs/ai_runtime_governance/*.md` |
| runtime governance checker | 已落地 | `check_hiring_runtime_governance.py` |
| workflow governance tests | 已落地 | `tests/test_hiring_workflow_governance.py` |
| governance JSON 可提交性 | 已落地 | 本資料夾 `.gitignore` 重新納入 `workflow_manifest.json` / `workflow_trace_receipt.json` |
| 人數不限近三月營收報表 | 已落地 | `generate_unlimited_hiring_revenue_report.py`、`data/reports/{YYYYMMDD}/unlimited_hiring_revenue_report_{YYYYMMDD}.html` |
| 今日新增公司 CSV | 已落地 | `data/reports/{YYYYMMDD}/new_unlimited_companies_{YYYYMMDD}.csv` |
| 本月雙增公司 CSV | 已落地 | `data/reports/{YYYYMMDD}/current_month_revenue_increase_companies_{YYYYMMDD}.csv` |
| 近三月連增公司 CSV | 已落地 | `data/reports/{YYYYMMDD}/revenue_growth_companies_{YYYYMMDD}.csv` |
| 異常偵測摘要 JSON | 已落地 | `data/reports/{YYYYMMDD}/anomaly_summary_{YYYYMMDD}.json` |
| 月營收 DB 快照 CSV | 已落地 | `data/revenue_snapshots/monthly_revenue_summary_{YYYYMMDD}.csv` |
| 月營收快照 manifest | 已落地 | `data/revenue_snapshots/monthly_revenue_snapshot_manifest_{YYYYMMDD}.json` |
| 月營收 CSV / DB parity gate | 已落地 | `revenue_snapshot_db_mismatch`、`revenue_snapshot_row_count_mismatch` |
| PNG / PDF renderer | 已落地 | `render_unlimited_hiring_revenue_media.py`、`unlimited_hiring_revenue_media_receipt_{YYYYMMDD}.json` |
| PNG 定案版面 | 已落地 | `png_mode=anomaly_detection_summary`、本月雙增 `displayed_count=total_count`、footer `同步更新至徵人需求度網頁` |
| report checker | 已落地 | `check_unlimited_hiring_revenue_report.py` |
| report positive / negative controls | 已落地 | `tests/test_unlimited_hiring_revenue_report.py` |
| external runtime install | 禁止 | 只採概念對照，不安裝外部服務 |

## 尚未落地或限制

- 員工人數未取得目前是 warning，不是 blocker。
- 尚未對 Google 備援查詢建立獨立 source receipt。
- 尚未把 launchd 實際排程狀態做成每日 receipt；目前 wrapper 會留下 log。
- `workflow_manifest.json` 的 validation 欄位在 fetch 後會是 `PENDING_CHECKER`；正式 closeout 仍以 `check_hiring_demand_run.py` receipt 為準。
- 上層 repo 仍有全域 `*.json` ignore；目前只對本資料夾治理必要 JSON receipt 與月營收快照 manifest 開例外，避免誤把其他大量資料 JSON 全部納入 Git。
- Telegram 發送尚未落地；目前 PNG / PDF / HTML / CSV 只產本地 artifact 與 receipt。
- 網頁上的「日期_異常偵測摘要」button 尚未落地；PNG footer 只代表同步目標，不代表網站 UI 已改。
- 月營收快照 CSV 是 DB 快取快照，不是 FinMind / MoneyDJ 原始 response 留存。
