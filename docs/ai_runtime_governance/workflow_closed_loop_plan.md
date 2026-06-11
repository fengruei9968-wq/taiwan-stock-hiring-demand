# 徵人需求度閉回路計畫

更新日期：2026-05-15

## 白話結論

徵人需求度不能只看「有 CSV」或「爬蟲 exit 0」。每次都要先產結果，再用獨立 checker 對回 CSV、DB、jobs 明細與 manifest。只要 checker 擋下，就回到最小失敗點修正，修完重跑，再重驗。

## 閉回路

1. `fetch_hiring_demand.py` 產出 CSV、必要 DB rows、jobs 明細、run manifest、workflow manifest 與 JSONL trace receipt。
2. `check_hiring_demand_run.py` 讀 manifest，獨立檢查 CSV / DB / jobs；`workflow_manifest.json` 在 checker 前的 validation 狀態是 `PENDING_CHECKER`。
3. 若核心 checker PASS，產生人數不限近三月營收 HTML / CSV / anomaly summary 與 `data/revenue_snapshots/` 月營收 DB 快照，再跑 report checker；report checker PASS 後渲染定案版 PNG / PDF 與 media receipt；`write-db` mode 要核心 checker、report checker 與 media receipt 都 PASS 才可 closeout。
4. 若 checker FAIL，讀 `typed_blockers.csv`，回到最小失敗點修正。
5. 修正後重跑 unit tests、py_compile、wrapper syntax check，再重跑 checker。

## 必停條件

- 需要真實 104 API 重新抓取，但本輪未授權 live scrape。
- 需要寫入或替換正式 DB，但本輪不是 `write-db` / `deploy`。
- 需要 commit / push，但沒有 `HIRING_DEMAND_DEPLOY_MODE=deploy` 或使用者明確授權。
- 需要修改 stage3_web、stage0、stage1 或其他專案檔案。
- 缺 Stock_codes source、CSV、DB 或 manifest。
- 沒有可信 checker、positive control 或 negative control。
- 超出本輪 path、run-id、artifact root 或資料夾邊界。

## PASS / FAIL / WARN 說明

- PASS：本輪 manifest、CSV、DB 與 jobs 在授權 mode 內一致，可以作為 closeout evidence。
- FAIL：不可 closeout、不可 deploy、不可宣稱完成；必須先處理 typed blocker。
- WARN：目前允許 closeout，但要說清楚限制。例如 `employee_count_unresolved` 表示有職缺但員工人數未取得。

## 修補原則

- schema 錯：先修輸出欄位或 checker contract。
- row count 錯：先確認 fetch_date、CSV path、DB path 是否同一輪。
- jobs coverage 錯：先修 `save_jobs_to_database` 或 aggregation。
- 特殊值錯：先修 `parse_need_emp` / `aggregate_company_data`。
- 人數不限營收報表錯：先修報表 generator、`monthly_revenue_summary` coverage 或今日新增差集邏輯，再重跑 report checker。
- 月營收快照錯：先修 DB 讀取、snapshot CSV writer 或 manifest，再重跑 report checker；不得直接手改 CSV 讓 checker PASS。
- PNG / PDF renderer 錯：先修 `render_unlimited_hiring_revenue_media.py` 或 media receipt metadata，再重跑 renderer test、report checker 與 runtime governance checker。
- deploy gate 錯：不要繞過，改用正確 run mode 重跑。
