# Hiring Demand Current Execution

Updated: 2026-06-13 08:17 Asia/Taipei

## Plain Summary

The hiring-demand project is being shaped into the first independent repo template. The goal is to keep the whole topic together: scraper, revenue pipeline, reports, Telegram publication, release artifacts, governance checks, and the dedicated `stage3_web/` web runtime.

This document is the short active-truth entrypoint. Detailed legacy rules remain in `../CURRENT_HIRING_DEMAND_EXECUTION.md`; when the two disagree, this file and the manifests should be updated first, then the legacy file should be brought back into alignment.

## Current Target Architecture

| Area | Active Decision |
|---|---|
| Repo unit | One complete topic repo candidate: `上市櫃公司徵人需求度`. |
| Railway root directory | `stage3_web`. |
| Web data publish surface | `stage3_web/hiring_reports/**` and `stage3_web/data/hiring_reports/**`. |
| Protected DB policy | DB files remain local/fallback/protected; daily web updates use JSON artifacts, not DB commits. |
| Telegram policy | Sending requires explicit `.env` mode and explicit user authorization for live send work. |
| Git policy | No git init/add/commit/push until the user explicitly authorizes. |

2026-06-11 decision update: user confirmed the entire `上市櫃公司徵人需求度` folder as the future independent Git repo root, with Railway root directory set to `stage3_web`. This records the architecture decision only; it does not authorize `git init`, staging, commit, push, GitHub repo creation, or Railway service changes.

## Standard Modes

| Mode | Purpose | Allowed | Not Allowed |
|---|---|---|---|
| `scrape-only` | Produce CSV and run manifest for inspection. | Read sources, write CSV, write receipts. | DB write, Telegram send, deploy, git. |
| `write-db` | Local scheduled update mode. | Write CSV, local DB, jobs table, receipts, reports. | Git push, web deploy claim. |
| `deploy` | Explicit release mode. | After gates pass, publish JSON artifacts to web copy paths. | Protected DB staging, broad git add, unverified push. |
| `governance-dry-run` | Template and readiness checks. | Docs, manifests, no-live checkers, unit tests. | Formal scraper, Telegram send, deployment. |

## Required Governance Files

- `AGENTS.md`
- `docs/CURRENT_EXECUTION.md`
- `docs/COMMANDS.md`
- `docs/ADR/ADR-001-governance-import-policy.md`
- `manifests/repo_manifest.yaml`
- `manifests/data_contract.yaml`
- `manifests/allowed_entrypoints.yaml`
- `check_release_readiness.py`
- `tests/test_release_readiness.py`

## Stop Conditions

- A protected DB or `.env` file appears in a release/stage candidate.
- A daily deploy candidate includes anything outside the allowed publish surface.
- `stage3_web/` is missing required Railway runtime files.
- The latest deployable JSON artifact is missing or malformed.
- The folder is still being treated as a clean independent Git repo when `git status` shows it is attached to the parent repo.
- A live scraper, Telegram send, or push would be required but the user only authorized governance or dry-run work.

## Next Exact Step

Treat the hiring-demand project as functionally complete pending observation of the next normal Stock_codes 05:00 run and the next normal 11:30 main crawler run. Do not run another live 104 benchmark until the main LaunchAgent benchmark isolation preflight is used.

## 2026-06-13 Raw Monthly Revenue Launcher Closeout

Plain status: raw monthly revenue scheduling now follows the same local-launcher pattern as the main hiring scraper. launchd no longer executes the raw monthly revenue SSD shell script directly.

Current installed raw monthly revenue scheduler state verified at 2026-06-13 14:10 Asia/Taipei:

- `com.stock.monthly.revenue.raw.updater`: loaded, not running, local launcher mode `run-raw-revenue-listed-otc`, day 5 10:10.
- `com.stock.monthly.revenue.raw.emerging.updater`: loaded, not running, local launcher mode `run-raw-revenue-emerging`, day 10 10:10.
- `com.stock.monthly.revenue.raw.missing.retry`: loaded, not running, local launcher mode `run-raw-revenue-missing-retry`, day 15 10:10.
- Local launcher path: `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh`.
- Local raw revenue wrapper copy: `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_stock_monthly_revenue_raw.sh`.
- Local launchd stdout/stderr paths now live under `/Users/chiufengjui/Library/Logs/HiringDemand/`.
- No raw monthly revenue fetch was triggered by this scheduler installation.

Verification for this closeout:

- Local launcher self-test PASS.
- `check_scheduler_installation.py --root .` PASS with raw revenue plist checks.
- Render-only raw revenue plist lint PASS.
- Targeted scheduler/path tests PASS.

## 2026-06-13 Scheduler Trigger Closeout

Plain status: the off-schedule repeated hiring-demand runs were traced to filesystem-triggered launchd behavior, not to 104 blocking or Python restarting itself. The main and Stock_codes LaunchAgents have been corrected to calendar-only triggers.

Current installed LaunchAgent state verified at 2026-06-13 08:17 Asia/Taipei:

- `com.hiring.stock.codes.updater`: loaded, not running, calendar trigger only, daily 05:00 Asia/Taipei.
- `com.hiring.demand.updater`: loaded, not running, calendar trigger only, daily 11:30 Asia/Taipei.
- Both installed plist files pass `plutil -lint`.
- Both installed plist files contain no `StartOnMount`, `WatchPaths`, or `QueueDirectories`.
- `launchctl print` shows `properties = inferred program`, not `start on fs mount`.
- No formal crawler was manually triggered during this closeout verification.

Governance state:

- `scheduler_templates/com.hiring.demand.updater.plist.template` and `scheduler_templates/com.hiring.stock.codes.updater.plist.template` no longer contain `StartOnMount`.
- `check_scheduler_installation.py` now blocks `StartOnMount`, `WatchPaths`, and `QueueDirectories` for scheduled plists.
- `tests/test_scheduler_local_runtime.py` covers both the template rule and the checker failure path.
- Commit pushed: `aa7dff8 chore: remove mount-triggered hiring schedulers`.

Verification for this closeout:

- `TMPDIR="/Volumes/Extreme SSD/tmp" ./run_tests.sh` PASS, 115 tests.
- `check_scheduler_installation.py --root .` PASS.
- `check_release_readiness.py --root .` PASS.
- `check_hiring_deploy_boundary.py --hiring-dir . --stage3-dir stage3_web` PASS.

Remaining note:

- The old D-slot `com.stock.updater` was not modified by this closeout. It remains a separate transitional updater and should only be disabled after explicit authorization.

## 2026-06-13 Functional Closeout Snapshot

Plain status: the independent hiring-demand project is operationally complete as a local SSD project template: it has governed source, governed local scheduler, repo-local Stock_codes input, 104 crawler, Telegram/report/web artifact flow, deploy boundary checker, release readiness checker, tests, and protected-path rules.

Confirmed current scheduler state:

- `com.hiring.stock.codes.updater`: daily 05:00 Asia/Taipei.
- `com.hiring.demand.updater`: daily 11:30 Asia/Taipei.
- Both jobs go through `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh`.
- Main and Stock_codes jobs must be calendar-only. `StartOnMount`, `WatchPaths`, and `QueueDirectories` are forbidden because SSD mount events can create duplicate off-schedule runs.
- Stock_codes writes to `data/stock_codes/`.
- The hiring scraper reads `config.yaml` `paths.stock_codes_dir: "data/stock_codes"`.

Stock_codes auto-update evidence:

- Temporary launchd test at 2026-06-13 00:09 Asia/Taipei triggered automatically.
- `launchctl` reported `runs=1`, `last exit code=0`.
- Generated `data/stock_codes/20260613_stock_codes.csv` and `data/stock_codes/20260613_stock_codes_all.csv`.
- Both generated files have 2321 lines.
- Receipt `data/runs/stock_codes_update/stock_codes_update_receipt_20260613.json` recorded `total_count=2320`, `is_complete=true`, `gate_result=PASS`.
- Formal schedule was restored to 05:00 after the test.

Important fix after the iPhone failure notification:

- The iPhone notification came from a 2026-06-12 late-night `com.hiring.demand.updater` run, not from the 2026-06-13 Stock_codes scheduler.
- Root cause: `fetch_hiring_demand.py` resolved relative `stock_codes_dir: "data/stock_codes"` against the parent project root, producing `/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/data/stock_codes`.
- Fix: `stock_codes_dir` now uses `_resolve_hiring_path(...)`, same as `db_path` and `output_dir`, so it resolves to `/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度/data/stock_codes`.
- Targeted tests for the path contract passed after the fix.
- Governance hardening: this is now a formal path boundary rule in `AGENTS.md` and `manifests/data_contract.yaml`.
- Release gate: `check_release_readiness.py` now emits `path_boundary_violation` if `fetch_hiring_demand.py` resolves `stock_codes_dir` from the parent project root or old D-slot path.
- Negative control: `tests/test_release_readiness.py::test_stock_codes_relative_path_resolving_outside_hiring_root_fails` verifies the bad resolver is blocked.

Remaining authorization points:

- Do not disable old `com.stock.updater` until the 05:00 Stock_codes job and the 11:30 main scraper have both been observed once in normal schedule order.
- Do not stage/commit/push this governance/runtime batch until the release-candidate file list is reviewed.
- Protected DB and `.env` files remain out of release candidates.

## 2026-06-12 Stock Codes Scheduler Integration

Plain status: the hiring-demand project now owns its own stock-code input pipeline. The active input directory is repo-local `data/stock_codes/`, and `config.yaml` reads that directory instead of the old D-slot stock-code updater output.

Installed local scheduler state as of 2026-06-12 23:11 Asia/Taipei:

- New LaunchAgent label: `com.hiring.stock.codes.updater`.
- Installed plist: `/Users/chiufengjui/Library/LaunchAgents/com.hiring.stock.codes.updater.plist`.
- Local launcher path: `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh`.
- Local Stock_codes wrapper path: `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_stock_codes_update.sh`.
- Local scheduler venv: `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/venv`.
- Schedule: daily 05:00 Asia/Taipei, before the main 11:30 hiring scraper. This avoids the main scraper reading Stock_codes while the updater is still writing.
- Output directory: `data/stock_codes/`.
- Local seed copied from the old D-slot 2026-06-12 complete CSVs so the next scraper has an immediate repo-local input.

Transition rule:

- Old `com.stock.updater` is still loaded and was not modified by this change.
- It is not a conflict while it writes only to its old D-slot `Stock_codes` directory.
- Do not point both `com.stock.updater` and `com.hiring.stock.codes.updater` to the same output directory.
- After the new 05:00 scheduler is observed writing a fresh complete CSV before the main scraper starts, the old `com.stock.updater` can be disabled with explicit user authorization.

Verification already run:

- `bash -n install_scheduler.sh run_hiring_demand.sh run_telegram_recipient_probe.sh run_stock_codes_update.sh scheduler_templates/run_hiring_demand_launcher.sh.template` PASS.
- `plutil -lint` for demand, Telegram probe, and Stock_codes plist templates PASS.
- `venv/bin/python3 -m py_compile stock_codes_updater.py check_release_readiness.py check_scheduler_installation.py fetch_hiring_demand.py` PASS.
- `TMPDIR="/Volumes/Extreme SSD/tmp" ./run_tests.sh` PASS, 112 tests.
- `check_release_readiness.py --root . --output-dir _test_runtime/release_readiness_stock_codes_v2` PASS.
- `check_hiring_deploy_boundary.py --hiring-dir . --stage3-dir stage3_web --output-dir _test_runtime/deploy_boundary_stock_codes_v2` PASS.
- `check_scheduler_installation.py --root .` PASS, finding count 0.

## 2026-06-12 Active Handoff: 104 Formal Run And Company Index

Plain status: the 2026-06-12 rerun is not stuck at company matching anymore. The company-name matching optimization has passed the slow section and the active run is currently querying 104 job detail records to fetch `needEmp` demand counts.

Important distinction:

- The 104 search/list API returns job list data such as company name, job title, job id, link id, and employee-count range.
- The 104 search/list API does not include the final demand-count field used by this project.
- The demand-count field (`needEmp`, including values such as explicit headcount or `不限`) comes from the per-job detail API.
- Therefore the scraper is one operational workflow, but it still has two data-source phases: search/list first, then detail lookup for matched jobs.

Current live evidence as of 2026-06-12 16:50 Asia/Taipei:

- Launcher process remained active: `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand.sh`.
- Main Python process remained active: `fetch_hiring_demand.py`.
- Stock code source is now governed inside this repo at `data/stock_codes/`, not the old D-slot stock-code updater output.
- Latest D-slot stock-code CSV before the transition was `/Users/chiufengjui/D槽/Python/台股子公司投資資訊擷取與展示/台股上市櫃公司名稱確認與自動定時更新/Stock_codes/20260612_stock_codes_all.csv`; it may be used only as a one-time seed or comparison input, not as active truth.
- Company index log: `已建立公司名稱比對索引，共 6619 個名稱 key，2320 個包含比對 entries`.
- Company matching completed and moved into detail lookup: `開始查詢 1474 筆職缺的需求人數...`.
- Latest observed progress: `已查詢 900/1474 筆職缺詳情`.

Completion evidence still required before claiming the formal run is complete:

- `職缺詳情查詢完成`
- local calculation/write completion (`計算完成`, `已儲存`, `已寫入`)
- report/media generation completion if triggered by the wrapper
- Telegram publication result
- guarded git add/commit/push result from the scheduler wrapper
- final wrapper success line such as `程式執行完成`

Current implementation changes pending review:

- `fetch_hiring_demand.py`: added prebuilt company-name index and progress logs during company matching.
- `config.yaml`: `paths.stock_codes_dir` now points to repo-local `data/stock_codes`.
- `tests/test_company_match_index.py`: added coverage for exact, suffix-stripped, and contains matching without falling back to pandas row scans.
- `tests/test_hiring_pipeline_path_contract.py`: updated the stock-code path contract to expect repo-local `data/stock_codes` and the independent `com.hiring.stock.codes.updater` scheduler template.

Verification already run before the live rerun:

- `./run_tests.sh tests/test_company_match_index.py tests/test_hiring_pipeline_path_contract.py tests/test_release_readiness.py tests/test_hiring_manifest.py tests/test_hiring_workflow_governance.py` passed.
- `python3 -m py_compile fetch_hiring_demand.py tests/test_company_match_index.py` passed.
- `python3 check_release_readiness.py --root . --output-dir _test_runtime/release_readiness_company_index_v2` passed with blocker count 0.

Known next improvement after this run finishes:

- Done on 2026-06-12: added same-day job-detail cache keyed by `linkJobId` so reruns do not re-query already fetched `needEmp` values.
- Done on 2026-06-12: detail lookup is now resumable at the successful-record level because each successful detail lookup is persisted immediately.
- Consider small, rate-limited parallel detail lookup only after confirming it does not increase 104 blocking risk.

## 2026-06-12 Detail Cache / Resume Implementation

Plain status: future reruns can reuse same-day successful 104 job-detail lookups. If a run is interrupted after hundreds of detail records, the next run should skip cached `linkJobId` records and only call 104 for missing records.

Engineering details:

- Cache path: `data/runs/job_detail_cache/YYYYMMDD_need_emp_cache.json`.
- Cache key: `linkJobId`.
- Cached value: raw `needEmp` text, for example `2人` or `不限`.
- Persistence timing: immediately after each successful non-empty detail lookup.
- Empty `needEmp` values are not cached, because the current 104 helper returns an empty string both for a legitimate missing field and for failed / unreachable detail requests. This avoids preserving network failures as if they were confirmed unspecified jobs.
- `aggregate_company_data()` now loads the same-day cache before detail lookup and uses `fetch_job_detail_need_emp_cached()` for each matched job.

Fresh verification:

- `./run_tests.sh tests/test_job_detail_cache.py` passed.
- `./run_tests.sh tests/test_job_detail_cache.py tests/test_company_match_index.py tests/test_hiring_pipeline_path_contract.py tests/test_release_readiness.py tests/test_hiring_manifest.py tests/test_hiring_workflow_governance.py` passed with 35 tests.
- `venv/bin/python3 -m py_compile fetch_hiring_demand.py tests/test_job_detail_cache.py tests/test_company_match_index.py` passed.
- `venv/bin/python3 check_release_readiness.py --root . --output-dir _test_runtime/release_readiness_detail_cache` passed with `gate_result=PASS`, `blocker_count=0`, `warning_count=0`.
