# 徵人需求度三層治理架構

更新日期：2026-06-05

## 白話結論

徵人需求度現在分三層管：第一層負責 probe / 抓資料與寫輸出，第二層負責用機器檢查輸出是否可信，第三層負責防止 agent 或 wrapper 越界部署。任何一層失敗，都不能宣稱完成。

## 第一層：內層 workflow / domain skill

| 項目 | 規則 |
|---|---|
| 觸發情境 | 手動執行或 launchd 每天 11:30。 |
| 主要輸入 | 104 搜尋 API、104 職缺詳情、Stock_codes 最新 CSV、`config.yaml`。 |
| preflight sensor | `probe_104_search_api.py` 實際 probe 104 搜尋 API，分類 `cloudflare_challenge`、`http_403`、`non_json_response`、`empty_jobs` 等 typed failure。 |
| recovery policy | `hiring_recovery_policy.json` 把 typed failure 路由到 bounded retry、keyword retry、停止檢查或安全停止。 |
| 處理 | `fetch_hiring_demand.py` 搜尋職缺、比對公司、解析需求人數、計算徵人需求度；員工人數只採 104 搜尋結果與 Google fallback。 |
| 輸出 | `data/YYYYMMDD_hiring_demand.csv`、`investment.db` 的 `hiring_demand` / `hiring_demand_jobs`、run manifest、workflow manifest、JSONL trace receipt、人數不限近三月營收 HTML / CSV / PNG / PDF 報表、anomaly summary JSON、`data/revenue_snapshots/monthly_revenue_summary_{YYYYMMDD}.csv`、media receipt。 |
| PASS 條件 | API probe PASS 後，成功 run 必須寫出 CSV 與 `data/runs/{run_id}/hiring_run_manifest.json`。`write-db` / `deploy` 還必須寫入 DB 與 jobs 明細。 |

失敗時不得只停在「爬蟲失敗」；必須分類成 API / source / matching / special value / DB / deploy gate 等 typed blocker，修正後重跑。

## 第二層：中層 harness / checker / receipt

| 項目 | 規則 |
|---|---|
| checker | `check_hiring_demand_run.py`。 |
| receipt | `api_probe_receipt_attempt_*.json`、`hiring_run_check_receipt.json`、`hiring_run_check_receipt.md`、`typed_blockers.csv`、`warnings.csv`。 |
| trace | `workflow_trace.jsonl`、`workflow_trace_receipt.json`，只作本地 trace evidence，不啟動外部 collector。 |
| report checker | `check_unlimited_hiring_revenue_report.py` 驗人數不限定義、今日新增公司差集、近三月營收覆蓋、月營收 CSV / DB parity 與 artifact path。 |
| revenue snapshot receipt | `monthly_revenue_snapshot_manifest_{YYYYMMDD}.json` 記錄 `source_db_path`、`source_table`、`row_count`、`updated_at_min/max`、CSV path。 |
| media receipt | `render_unlimited_hiring_revenue_media.py` 產 `unlimited_hiring_revenue_media_receipt_{YYYYMMDD}.json`，記錄 `primary_human_artifact=png`、`png_mode=anomaly_detection_summary`、三個 section 的 `total_count/displayed_count` 與 footer。 |
| 必查 | manifest、CSV schema、row count、999/998 特殊值、duplicate stock code。 |
| `write-db` / `deploy` 必查 | DB 當日 row count、CSV/DB 欄位一致、jobs 明細數與 CSV `總職缺數` 一致。 |
| positive control | `tests/test_hiring_demand_checker.py::test_valid_csv_db_and_jobs_pass`。 |
| negative controls | row count mismatch、invalid 999、未明確 deploy mode、scrape-only 不可 deploy。 |

checker PASS 代表本輪 artifact 在本地一致；不代表 104 外部資料永遠正確，也不代表可以自動部署。

## 第三層：外層 agent / session governance

| 項目 | 規則 |
|---|---|
| active truth | `CURRENT_HIRING_DEMAND_EXECUTION.md`。 |
| session guard | 所有修正只限本資料夾；不改 stage0/stage1/stage3。 |
| deploy boundary | 沒有 `HIRING_DEMAND_DEPLOY_MODE=deploy` 時只能停在 CSV / DB / checker receipt；部署只允許 `hiring_reports/` 與 `data/hiring_reports/`。 |
| completion verification | 完成宣告前必跑 unit tests、py_compile、shell syntax check、必要時 checker。 |
| closeout | 回覆要列出新增/修改檔案、verification 結果、仍不能代表什麼。 |

外層發現問題時，不直接用聊天判定 PASS；必須導回第一層修正與第二層重驗。
