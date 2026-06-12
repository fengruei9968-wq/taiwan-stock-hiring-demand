# Hiring Governance Changes Review 2026-06-12

## Plain Summary

This review covers the uncommitted governance, scheduler, cleanup, and crawler-stability changes left after the 2026-06-12 formal hiring-demand deploy.

The daily deploy commit already pushed only web JSON artifacts under `stage3_web/hiring_reports/**` and `stage3_web/data/hiring_reports/**`. The files below are separate repo-template changes. They should be reviewed and staged precisely; do not use `git add .`.

## Current Git State

- Branch: `main`
- Remote sync: `main...origin/main` has no ahead / behind at the time of review.
- Latest deployed data commit: `056de68 chore: 自動更新徵人需求度資料 2026/06/12 22:16`
- Protected files were not part of that deploy commit.

## A. Recommended Include In Governance Commit

These files define the independent hiring-demand repo governance and should be committed together after final user authorization.

| File | Reason |
|---|---|
| `.gitignore` | Keeps 104 detail runtime cache local-only. |
| `AGENTS.md` | Adds 104 detail lookup, benchmark isolation, and report artifact retention rules. |
| `check_hiring_runtime_governance.py` | Updates deploy marker to the correct independent repo path: `stage3_web/hiring_reports` and `stage3_web/data/hiring_reports`. |
| `check_release_readiness.py` | Adds release gates for scheduler docs, cache boundary, and PNG/PDF publish-surface blockers. |
| `docs/COMMANDS.md` | Documents scheduler doctor, benchmark, detail cache monitoring, and report artifact cleanup commands. |
| `docs/CURRENT_EXECUTION.md` | Records current active execution and scheduler/deploy boundaries. |
| `docs/SCHEDULER.md` | Documents the internal-disk local launcher pattern for launchd and new-machine recovery. |
| `manifests/allowed_entrypoints.yaml` | Adds allowed scheduler doctor, benchmark preflight, and restore entrypoints. |
| `manifests/data_contract.yaml` | Adds 104 detail cache and report artifact retention contracts. |
| `manifests/repo_manifest.yaml` | Records local-only cache/report artifact boundaries. |
| `manifests/scheduler_manifest.yaml` | Defines the scheduler architecture and benchmark isolation policy. |
| `scheduler_requirements.txt` | Defines the local scheduler venv requirements. |
| `scheduler_templates/run_hiring_demand_launcher.sh.template` | Template for the internal-disk launcher used by launchd. |
| `scheduler_templates/com.hiring.demand.updater.plist.template` | Points main LaunchAgent to the local launcher. |
| `scheduler_templates/com.hiring.telegram.recipient.probe.plist.template` | Points probe LaunchAgent to the local launcher. |
| `check_scheduler_installation.py` | Read-only scheduler doctor plus benchmark preflight / restore checks. |
| `cleanup_report_artifacts.py` | Dry-run only report artifact cleanup review generator. |
| `tests/test_cleanup_report_artifacts.py` | Covers dry-run report artifact cleanup. |
| `tests/test_company_match_index.py` | Covers fast company matching index behavior. |
| `tests/test_job_detail_cache.py` | Covers 104 detail cache resume / refresh behavior. |
| `tests/test_scheduler_local_runtime.py` | Covers local launcher, scheduler venv, and benchmark checks. |
| `tests/test_hiring_pipeline_path_contract.py` | Updates path contracts for independent repo deploy scope and scheduler rules. |
| `tests/test_release_readiness.py` | Covers new release-readiness blockers. |

## B. Include, But Treat As Runtime-Sensitive

These files are code paths used by the formal crawler or scheduler. They are recommended for commit, but should be included only after the test gates below stay green.

| File | Reason | Risk Control |
|---|---|---|
| `fetch_hiring_demand.py` | Adds company-name match index and 104 detail cache/resume. | Covered by `tests/test_company_match_index.py`, `tests/test_job_detail_cache.py`, and the completed live benchmark. |
| `run_hiring_demand.sh` | Uses local launcher override paths and deploys only `stage3_web/hiring_reports/**` plus `stage3_web/data/hiring_reports/**`. | `bash -n`, pipeline path tests, release checker, and deploy boundary checker. |
| `run_telegram_recipient_probe.sh` | Supports internal-disk wrapper copy with `HIRING_SCRIPT_DIR`. | Scheduler local runtime tests and path contract tests. |
| `install_scheduler.sh` | Adds local launcher install, local scheduler venv bootstrap, doctor, benchmark preflight, and restore support. | `bash -n`, render-only tests, scheduler doctor tests. |

## C. Stock Codes Decision Resolved

| File | Decision |
|---|---|
| `config.yaml` | `paths.stock_codes_dir` now points to repo-local `data/stock_codes`. The independent updater `stock_codes_updater.py` and scheduler label `com.hiring.stock.codes.updater` own this input. The old D-slot `com.stock.updater` is transitional only and must not be treated as active truth for this repo. |

## D. Do Not Include

No runtime cache, protected DB, `.env`, `telegram_recipients.json`, PNG, PDF, HTML report history, log files, venv, or `_test_runtime/**` should be staged.

Protected files that must remain out of commit:

- `.env`
- `.env.*`
- `telegram_recipients.json`
- `stage3_web/investment.db`
- `stage3_web/data/investment.db`
- `stage3_web/fixed_assets.db`
- `stage3_web/data/users.db`

## Verification Run

Commands run on 2026-06-12:

```bash
bash -n install_scheduler.sh run_hiring_demand.sh run_telegram_recipient_probe.sh scheduler_templates/run_hiring_demand_launcher.sh.template
venv/bin/python3 -m py_compile check_release_readiness.py check_hiring_runtime_governance.py check_scheduler_installation.py cleanup_report_artifacts.py fetch_hiring_demand.py
venv/bin/python3 check_hiring_runtime_governance.py --root . --output-dir _test_runtime/runtime_governance_after_marker_fix
TMPDIR="/Volumes/Extreme SSD/tmp" ./run_tests.sh
```

Results:

- Shell syntax: PASS
- Python compile: PASS
- Runtime governance checker: PASS
- Unit tests: PASS, `108` tests

## Recommended Next Step

Do a precise staging review with the A and B files above, then decide whether `config.yaml` should be included in the same commit or split into a separate transitional dependency commit.

Do not stage this review with `git add .`; stage explicit paths only.
