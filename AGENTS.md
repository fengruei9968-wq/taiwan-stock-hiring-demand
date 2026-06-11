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
- Do not modify fixed-assets, inventory, transfer-investment, stock-code updater, parent `stage3_web`, or parent repo files as part of hiring-demand work.
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
