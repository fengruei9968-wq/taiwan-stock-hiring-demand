# 徵人需求度 AI Runtime Governance 概念對照表

更新日期：2026-05-15

## 白話結論

本資料夾不安裝、不啟動 OPA、Temporal、Langfuse、Great Expectations、Prefect、Dagster、Argo Workflows、OpenTelemetry 或 Superpowers runtime。這些專案只拿來參考治理概念，落地成徵人需求度自己的本地規則、checker、receipt、manifest 與 tests。

## 工程化對照

| 外部專案 | 參考概念 | 徵人需求度本地落地 |
|---|---|---|
| OPA | policy-as-code、deny rule、hard gate | `check_hiring_demand_run.py` 擋缺 CSV、錯 schema、錯特殊值、錯 DB row count、未明確 deploy mode。 |
| Temporal | durable workflow、history、retry、failure propagation | `CURRENT_HIRING_DEMAND_EXECUTION.md` 定義 `scrape-only / write-db / deploy` 狀態邊界；run manifest 保留 run-id、mode、輸入、輸出與 API 摘要。 |
| Langfuse | execution trace、tool metadata、receipt | `hiring_run_manifest.json`、`workflow_trace.jsonl` 與 checker receipt 記錄 run metadata、evidence path、typed blockers、warnings。 |
| Great Expectations | executable expectations | checker 驗 CSV header、row count、duplicate stock code、999/998 特殊值、CSV/DB/jobs 一致性。 |
| Prefect | staged orchestration、state transition、step unlock | wrapper 預設只到 `write-db` checker；只有 `HIRING_DEMAND_DEPLOY_MODE=deploy` 且 `--require-deploy-mode` PASS 才能進 deploy。 |
| Dagster | asset lineage、materialization、dependency graph | manifest 記錄 `input_stock_codes_file`、`csv_path`、`db_path`、`db_inserted_count`、`job_inserted_count`。 |
| Argo Workflows | DAG、artifact dependency、hard fail | wrapper 將 `fetch -> manifest -> checker -> optional deploy checker -> scoped git stage` 串成硬依賴，任一步非 0 即停止。 |
| OpenTelemetry | trace/span/correlation id | `run_id` 作為本地 correlation id；`workflow_trace.jsonl` 逐步記錄 source gate、fetch、match、CSV、DB、checker-required spans。 |
| Superpowers | skill routing、debugging、fresh verification | 文件要求完成前 fresh checker；測試提供 positive / negative controls；不靠口頭宣稱完成。 |

## 禁止事項

- 不 clone 外部 repo 到本資料夾。
- 不啟動外部 server、daemon、collector、dashboard 或 UI。
- 不把外部 runtime 設為部署必要條件。
- 不把聊天摘要當 receipt；必須有本地 JSON / MD / CSV evidence。
