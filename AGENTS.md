# Hiring Demand Agent Rules

Updated: 2026-06-11

## Plain Summary

This folder is the source of truth for the independent hiring-demand project. Keep the scraper, revenue updater, Telegram publication flow, release artifacts, governance receipts, and the dedicated `stage3_web/` runtime together in this repo candidate.

Do not treat the parent project's shared `stage3_web` as the active hiring-demand web runtime. The local `stage3_web/` folder inside this hiring-demand folder is the intended Railway root directory for this independent project.

## Active Truth Order

1. User instructions in the current session.
2. This `AGENTS.md`.
3. `docs/CURRENT_EXECUTION.md`.
4. `docs/COMMANDS.md`.
5. `manifests/repo_manifest.yaml`, `manifests/data_contract.yaml`, and `manifests/allowed_entrypoints.yaml`.
6. Legacy compatibility docs: `CURRENT_HIRING_DEMAND_EXECUTION.md`, `HIRING_DEPLOY_BOUNDARY.md`, `CLAUDE_hiring_demand.md`, and `HIRING_DEMAND_PITFALLS.md`.

Chat summaries, old backup files, copied parent-project files, and launchd logs are not active truth.

## Scope Boundary

- Work only inside this hiring-demand folder unless the user explicitly expands scope.
- Do not modify fixed-assets, inventory, transfer-investment, the parent/shared stock-code updater outside this folder, parent `stage3_web`, or parent repo files as part of hiring-demand work.
- Do not initialize Git, stage, commit, push, reset, restore, or clean unless the user explicitly authorizes that specific action.
- Do not run the formal scraper, send Telegram messages, or deploy unless the user explicitly asks for a live run.
- For normal governance work, use no-live checks, syntax checks, unit tests, manifest checks, and dry-run receipts.

## Protected Files

Never stage, commit, push, overwrite, delete, or move these as part of daily hiring-demand publication:

- `stage3_web/investment.db`
- `stage3_web/data/investment.db`
- `stage3_web/fixed_assets.db`
- `stage3_web/data/users.db`
- `.env`
- `.env.*`
- `telegram_recipients.json`

Daily deployable web data is limited to:

- `stage3_web/hiring_reports/**`
- `stage3_web/data/hiring_reports/**`

## 104 Detail Lookup Rule

- 104 search/list API does not include the final `needEmp` demand-count field.
- Do not remove the per-job detail lookup or treat it as duplicate crawling unless 104's API contract is re-verified and the checker/tests are updated.
- Slow formal runs must first be diagnosed from detail progress logs and the same-day detail cache before restarting from scratch.
- Same-day detail cache lives under `data/runs/job_detail_cache/YYYYMMDD_need_emp_cache.json`; it is a local runtime resume cache, not a source of truth and not a deployable web artifact.
- Empty `needEmp` values must not be cached as confirmed facts, because an empty string can mean either a legitimate missing field or a failed / unreachable detail request.

## Stock Codes Rule

- The hiring-demand scraper must read stock-code/company-name mapping from this repo's `data/stock_codes/` directory.
- `stock_codes_updater.py` is the governed updater for `data/stock_codes/`; it fetches official TWSE / TPEx listed, OTC, and emerging company data and writes `YYYYMMDD_stock_codes_all.csv`.
- The dedicated scheduler label is `com.hiring.stock.codes.updater`, scheduled at 05:00 before the 11:30 hiring scraper to avoid a Stock_codes read/write race.
- Do not make the hiring-demand scraper depend on the old D-slot `com.stock.updater` output as active truth.
- Do not run two writers against the same Stock_codes output directory. The old `com.stock.updater` may stay installed during transition only because it writes to a different D-slot directory.
- `data/stock_codes/**` is local runtime input data and should not be committed unless the user explicitly authorizes a snapshot.

## Path Boundary Rule

- In this independent repo, relative runtime paths in `config.yaml` must resolve from this folder, not from the parent `台股投資資訊系統_完整專案` folder.
- `stock_codes_dir`, `db_path`, and `output_dir` must use the hiring repo root as their default base.
- Do not use parent-project resolution for `data/stock_codes`, `stage3_web/investment.db`, or `data`; otherwise launchd may pass tests but the formal crawler will read the wrong directory.
- Explicit environment overrides such as `STOCK_CODES_DIR`, `DB_PATH`, and `HIRING_OUTPUT_DIR` are allowed only when the caller intentionally points at a known path.
- `check_release_readiness.py` must block a release if `fetch_hiring_demand.py` resolves `stock_codes_dir` through the parent project root.

## Benchmark Isolation Rule

- A benchmark run means measuring one complete formal flow duration, so it must not run while the main LaunchAgent can start another `run_hiring_demand.sh`.
- Before a benchmark, temporarily unload only the main LaunchAgent `com.hiring.demand.updater` and verify no `HiringDemandLauncher`, `run_hiring_demand.sh`, or `fetch_hiring_demand.py` process remains.
- Do not unload the Telegram recipient probe unless the benchmark explicitly needs a totally silent scheduler environment; the probe must not run the formal crawler.
- Restore the main LaunchAgent immediately after the benchmark and verify `launchctl print gui/$(id -u)/com.hiring.demand.updater` succeeds.
- If launchd starts a second formal crawler during a benchmark, mark that benchmark invalid, stop the duplicate processes, archive the partial runtime artifacts as invalid evidence, and rerun from a clean preflight.

## Report Artifact Retention Rule

- PNG/PDF/HTML report files under `data/reports/**` are local runtime artifacts for Telegram and human review.
- The hiring-demand website must use deployable JSON under `stage3_web/hiring_reports/**` and `stage3_web/data/hiring_reports/**` to rebuild the summary UI; do not deploy daily PNG/PDF report history.
- PNG/PDF/JPG/WebP files must not appear under `stage3_web/hiring_reports/**` or `stage3_web/data/hiring_reports/**`.
- Keep recent report media locally for short-term review. The default review threshold is 30 days.
- Older report media should be reviewed through `cleanup_report_artifacts.py`; default mode writes a review report only and does not move or delete files.
- The repo-external archive root is `/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/_archives/上市櫃公司徵人需求度/`.

## External Governance Concepts

External repos are concept sources only. Do not make Railway, GitHub, or the local runtime depend on ZeroSpec, Superpowers, basic-memory, andrej-karpathy-skills, mattpocock/skills, OPA, Temporal, Langfuse, OpenTelemetry, Great Expectations, Prefect, Dagster, or Argo.

Imported concepts must land as local docs, manifests, receipts, tests, or checkers before they can affect execution.

## Required Before Completion

Before saying a governance, release, or deploy-boundary change is complete, run fresh verification appropriate to the change. For the standard template this means:

```bash
venv/bin/python3 -m py_compile check_release_readiness.py
venv/bin/python3 -m unittest tests/test_release_readiness.py
venv/bin/python3 -m unittest discover -s tests
venv/bin/python3 check_hiring_deploy_boundary.py --hiring-dir . --stage3-dir stage3_web --output-dir data/runs/deploy_boundary_check_manual
venv/bin/python3 check_release_readiness.py --root . --output-dir data/runs/release_readiness_manual
```

Use the local `venv/bin/python3` when available. System Python may pass pure governance checks but can fail the full test suite if `pandas` is missing. Do not create or modify the venv just to run governance checks unless the user authorizes environment work.
