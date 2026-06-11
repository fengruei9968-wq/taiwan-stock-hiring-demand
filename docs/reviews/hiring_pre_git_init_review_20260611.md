# Hiring Demand Pre-Git-Init Review

Date: 2026-06-11

## 白話結論

可以進入「Git root 決策」討論，但還不能直接 `git init`。

目前範本本身已經通過 release readiness dry-run，明確 include 清單沒有缺檔，daily publish surface 也只有 JSON 報表目錄。但是資料夾裡實際存在 `.env`、`telegram_recipients.json`、`stage3_web/investment.db`，而且目前仍掛在上層 `/Volumes/Extreme SSD/Python` Git worktree；上層 ignore 會把整個 `stage3_web/` 遮住。正式初始化獨立 repo 前，必須先按 dry-run manifest 建立獨立 `.gitignore` 邊界，確保 web runtime 會被納入、DB/secret 會被排除。

## Review Inputs

| Artifact | Purpose |
|---|---|
| `manifests/git_include_exclude_dry_run_20260611.yaml` | Git include/exclude dry-run source |
| `docs/reviews/hiring_template_readonly_review_20260611.md` | Template readiness review |
| `data/runs/pre_git_init_release_readiness_20260611_160257/hiring_release_readiness_receipt.json` | Fresh release readiness dry-run |
| `git check-ignore -v ...` | Parent ignore impact check |
| scoped `git status --short -- ...` | Protected path visibility check |

## Decision

| Item | Result |
|---|---|
| Proceed to Git root decision | YES |
| Run `git init` now | NO |
| Stage or commit now | NO |
| Push to GitHub now | NO |
| Touch protected DB or secrets | NO |
| Use current parent Git status as final truth | NO |

## PASS Evidence

| Check | Result |
|---|---|
| `check_release_readiness.py` | PASS |
| release blocker count | 0 |
| release warning count | 1: `not_independent_git_root_yet` |
| explicit include-required missing files | 0 |
| deployable web JSON files | 10 |
| daily publish surface | `stage3_web/hiring_reports/**`, `stage3_web/data/hiring_reports/**` |

## Required Excludes That Actually Exist

These files exist locally and must be excluded before any independent Git commit:

| Path | Reason |
|---|---|
| `.env` | secret/local env |
| `telegram_recipients.json` | local recipient state |
| `stage3_web/investment.db` | protected local/fallback DB, 117M |

The following protected DB paths are still listed in the contract and must remain excluded even if absent today:

- `stage3_web/data/investment.db`
- `stage3_web/fixed_assets.db`
- `stage3_web/data/users.db`

## Parent Git / Ignore Risk

Current Git root:

```text
/Volumes/Extreme SSD/Python
```

Current parent ignore hides:

- `stage3_web/app.py`
- `stage3_web/templates/hiring_demand.html`
- `stage3_web/static/css/style.css`
- `stage3_web/hiring_reports/latest_hiring_demand_web_data.json`
- `stage3_web/investment.db`

This is acceptable before independent repo initialization, but it is not acceptable as the final repo state. After independent `git init`, the web runtime files must become visible include candidates while DB/secret/log/venv remain ignored.

## Manual Decisions Before Git Init

| Decision | Recommended Choice |
|---|---|
| Repo root | Entire `上市櫃公司徵人需求度` folder |
| Railway root directory | `stage3_web` |
| Include historical `data/*.csv` in Git | No for first commit; keep on SSD / artifacts unless user wants data history in repo |
| Include `data/reports/**` in Git | No for first commit; keep only latest deployable JSON in `stage3_web/hiring_reports` |
| Include launchd `.plist` files | Keep only after path review; machine-specific paths may need template cleanup |
| Include `stage3_web/investment.db` | No |
| Include `.env` or recipient file | No |

## Pre-Git-Init Stop Conditions

Do not initialize or stage if any of these are unresolved:

- `.env`, `telegram_recipients.json`, or protected DB appears in candidate files.
- `stage3_web/app.py`, templates, CSS, `Procfile`, or `requirements.txt` would remain ignored after independent Git init.
- daily publish candidate includes anything outside `stage3_web/hiring_reports/**` and `stage3_web/data/hiring_reports/**`.
- `check_release_readiness.py` reports any blocker.
- user has not explicitly authorized Git initialization.

## Next 5 Steps

1. User confirms whether the repo root should be the whole `上市櫃公司徵人需求度` folder.
2. Create an independent Git-root rehearsal plan that starts with `.gitignore`, not with `git add`.
3. If authorized, initialize Git only inside the hiring-demand folder.
4. Immediately run post-init ignore checks to confirm web runtime is included and DB/secrets are excluded.
5. Only after post-init release readiness PASS, discuss first commit content and GitHub repo name.

