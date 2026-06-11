# Hiring Demand Current Execution

Updated: 2026-06-11

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

Finish the hiring-demand governance template, run no-live verification, then use this folder as the model for `群組每日討論`. Daily memo must replace the data contract with its Railway Volume / DB restore contract before any repo split or deploy decision.
