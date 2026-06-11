# 徵人需求度本輪檔案變更清單

更新日期：2026-05-15

## 白話結論

本輪變更只限徵人需求度資料夾。目的不是新增外部服務，而是把 AI Runtime Governance 的概念落地成本地文件、manifest 欄位、checker、receipt 與 tests。

## 新增檔案

| 檔案 | 用途 |
|---|---|
| `docs/ai_runtime_governance/governance_reference_mapping.md` | 外部 runtime 概念對照到本地治理規則。 |
| `docs/ai_runtime_governance/workflow_three_layer_architecture.md` | 徵人需求度三層治理架構。 |
| `docs/ai_runtime_governance/workflow_closed_loop_plan.md` | 失敗後修正、重測、重驗的閉回路規則。 |
| `docs/ai_runtime_governance/workflow_hardening_checklist.md` | 已落地、未落地與限制清單。 |
| `docs/ai_runtime_governance/proposed_file_change_list.md` | 本輪變更用途清單。 |
| `check_hiring_runtime_governance.py` | read-only governance checker，檢查三層治理文件與本地 gate 是否存在。 |
| `tests/test_hiring_runtime_governance.py` | governance checker 的 positive / negative controls。 |
| `hiring_workflow_governance.py` | 將 `hiring_run_manifest.json` 對齊 common workflow manifest，並寫本地 JSONL trace / receipt。 |
| `tests/test_hiring_workflow_governance.py` | workflow manifest 與 trace receipt 的 positive controls。 |
| `.gitignore` | 讓本資料夾的 workflow manifest / trace receipt / 月營收快照 manifest JSON 不被上層 `*.json` 規則忽略，方便後續 commit closeout evidence。 |
| `generate_unlimited_hiring_revenue_report.py` | 產出人數不限公司近三月營收 HTML 報表、三類 CSV、月營收 DB 快照 CSV 與今日新增公司 CSV。 |
| `check_unlimited_hiring_revenue_report.py` | 驗人數不限定義、今日新增差集、營收覆蓋率、月營收 CSV / DB parity 與 report artifact path。 |
| `tests/test_unlimited_hiring_revenue_report.py` | 報表 generator / checker 的 positive control、缺營收 negative control、月營收快照 drift negative control。 |
| `render_unlimited_hiring_revenue_media.py` | 產出定案版異常偵測 PNG、PDF 與 media receipt。 |

## 修改檔案

| 檔案 | 用途 |
|---|---|
| `CURRENT_HIRING_DEMAND_EXECUTION.md` | 新增 AI Runtime Governance 本地 gate 與驗證命令。 |
| `CLAUDE_hiring_demand.md` | 補上本資料夾治理入口、禁止外部 runtime 與 checker 說明。 |
| `fetch_hiring_demand.py` | manifest 補上本地 governance contract / lineage / external runtime policy 欄位。 |
| `tests/test_hiring_manifest.py` | 驗證 manifest 具備 governance 與 lineage 欄位。 |
| `CURRENT_HIRING_DEMAND_EXECUTION.md` | 補上 `workflow_manifest.json` / `workflow_trace.jsonl` / `workflow_trace_receipt.json` gate。 |
| `CLAUDE_hiring_demand.md` | 補上 v4.1 trace receipt 與 schema 對齊規則。 |
| `check_hiring_runtime_governance.py` | 補上 `.gitignore` receipt 例外檢查，避免 governance JSON 只存在本機但無法被 Git 追蹤。 |
| `run_hiring_demand.sh` | 核心 checker PASS 後產報表並跑 report checker；仍預設不 commit / push。 |
| `generate_unlimited_hiring_revenue_report.py` | 預設更新 `data/reports/latest_unlimited_hiring_revenue_report_manifest.json`，讓 renderer 預設讀到最新日報表。 |
| `check_hiring_runtime_governance.py` | 補上 PNG renderer 與 receipt metadata 必要標記。 |
| `generate_unlimited_hiring_revenue_report.py` | 新增 `data/revenue_snapshots/monthly_revenue_summary_{YYYYMMDD}.csv` 與 `monthly_revenue_snapshot_manifest_{YYYYMMDD}.json`。 |
| `check_unlimited_hiring_revenue_report.py` | 新增 `revenue_snapshot_db_mismatch` / `revenue_snapshot_row_count_mismatch` hard gate。 |
| `check_hiring_runtime_governance.py` | 補上月營收快照與 negative control marker。 |

## 不修改

- 不修改 stage0、stage1、stage2、stage3_web。
- 不修改正式主專案 `AGENTS.md`。
- 不安裝、不啟動外部 runtime。
- 不 commit / push。
- 不發 Telegram；目前只落地本地 PNG / PDF / HTML / CSV 報表與 receipt。
- 不修改徵人需求度網頁；「日期_異常偵測摘要」button 等 Telegram / PNG 流程定案後另行規劃。
