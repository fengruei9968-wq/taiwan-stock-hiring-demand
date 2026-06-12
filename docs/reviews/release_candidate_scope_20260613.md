# Release Candidate Scope 2026-06-13

## Plain Summary

This release candidate turns `上市櫃公司徵人需求度` into a governed independent repo template. It includes scheduler hardening, repo-local Stock_codes ownership, 104 detail-cache resume support, path-boundary guards, local cleanup/report retention tooling, and release/deploy readiness checks.

Do not include local runtime data, protected DBs, secrets, logs, report media, or generated Stock_codes CSVs.

## Include In Commit

Governance and handoff:

- `.gitignore`
- `AGENTS.md`
- `docs/COMMANDS.md`
- `docs/CURRENT_EXECUTION.md`
- `docs/SCHEDULER.md`
- `docs/reviews/hiring_governance_changes_review_20260612.md`
- `docs/reviews/release_candidate_scope_20260613.md`
- `manifests/allowed_entrypoints.yaml`
- `manifests/data_contract.yaml`
- `manifests/repo_manifest.yaml`
- `manifests/scheduler_manifest.yaml`

Runtime and scheduler source:

- `config.yaml`
- `fetch_hiring_demand.py`
- `run_hiring_demand.sh`
- `run_telegram_recipient_probe.sh`
- `run_stock_codes_update.sh`
- `install_scheduler.sh`
- `scheduler_requirements.txt`
- `scheduler_templates/com.hiring.demand.updater.plist.template`
- `scheduler_templates/com.hiring.telegram.recipient.probe.plist.template`
- `scheduler_templates/com.hiring.stock.codes.updater.plist.template`
- `scheduler_templates/run_hiring_demand_launcher.sh.template`
- `stock_codes_updater.py`

Checkers and cleanup tools:

- `check_hiring_runtime_governance.py`
- `check_release_readiness.py`
- `check_scheduler_installation.py`
- `cleanup_report_artifacts.py`

Tests:

- `tests/test_cleanup_report_artifacts.py`
- `tests/test_company_match_index.py`
- `tests/test_hiring_pipeline_path_contract.py`
- `tests/test_job_detail_cache.py`
- `tests/test_release_readiness.py`
- `tests/test_scheduler_local_runtime.py`
- `tests/test_stock_codes_updater.py`

## Exclude From Commit

Protected or local-only paths:

- `.env`
- `.env.*`
- `telegram_recipients.json`
- `stage3_web/investment.db`
- `stage3_web/data/investment.db`
- `stage3_web/fixed_assets.db`
- `stage3_web/data/users.db`
- `data/stock_codes/**`
- `data/runs/**`
- `data/reports/**/*.png`
- `data/reports/**/*.pdf`
- `data/reports/**/*.html`
- `*.log`
- `venv/**`
- `_local_runtime/**`
- `_test_runtime/**`
- `__pycache__/**`

## Required Evidence Before Commit

- The 5-minute launchd test must show `fetch_hiring_demand.py` reading `上市櫃公司徵人需求度/data/stock_codes/20260613_stock_codes_all.csv`.
- `./run_tests.sh` must pass.
- `check_scheduler_installation.py --root .` must pass.
- `check_release_readiness.py --root .` must pass.
- `check_hiring_deploy_boundary.py --hiring-dir . --stage3-dir stage3_web` must pass.
- Staged files must not include protected DBs, `.env`, Telegram recipient secrets, Stock_codes CSVs, runtime cache, logs, or PNG/PDF report media.

