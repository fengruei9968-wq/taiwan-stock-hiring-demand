# Hiring Demand Template Read-Only Review

Date: 2026-06-11

## 白話結論

徵人需求度現在可以作為「三核心專案」的第一個治理範本。它已經具備 active truth、Railway root boundary、protected DB boundary、data contract、allowed entrypoints、release readiness checker、deploy boundary checker 與測試。

這還不能代表它已經是獨立 GitHub repo。現在資料夾仍掛在上層 Git worktree：`/Volumes/Extreme SSD/Python`。正式獨立前，必須先按 `manifests/git_include_exclude_dry_run_20260611.yaml` 建立 include/exclude 清單，再由使用者授權初始化 Git。

## 工程化佐證

| 項目 | 結果 |
|---|---|
| active truth | `AGENTS.md`、`docs/CURRENT_EXECUTION.md`、`docs/COMMANDS.md` 已建立 |
| governance ADR | `docs/ADR/ADR-001-governance-import-policy.md` 已建立 |
| manifests | `repo_manifest.yaml`、`data_contract.yaml`、`allowed_entrypoints.yaml` 已建立 |
| release checker | `check_release_readiness.py` 已建立 |
| release checker tests | `tests/test_release_readiness.py` 已建立 |
| Railway root | `stage3_web` |
| deploy boundary | daily publish 只允許 `stage3_web/hiring_reports/**` 與 `stage3_web/data/hiring_reports/**` |
| protected DB | `stage3_web/investment.db`、`stage3_web/data/investment.db`、`stage3_web/fixed_assets.db`、`stage3_web/data/users.db` |
| local-only secrets | `.env`、`.env.*`、`telegram_recipients.json` |

## Read-Only Findings

| Severity | Finding | 說明 | 建議 |
|---|---|---|---|
| WARN | `not_independent_git_root_yet` | `git rev-parse --show-toplevel` 回到 `/Volumes/Extreme SSD/Python`，不是本資料夾 | 下一步只做 dry-run include/exclude；未授權前不 `git init` |
| WARN | parent ignore hides `stage3_web/` | 上層規則會忽略整個 `stage3_web/`，不適合作為獨立 repo 的最終判斷 | 獨立 repo 初始化後使用本資料夾 `.gitignore` 與 `stage3_web/.gitignore` 重建邊界 |
| PASS | protected paths not in scoped status | scoped status 未列出 protected DB、`.env`、`telegram_recipients.json` | 保持 release checker 作為正式 Git 前置 gate |
| PASS | web JSON artifacts present | `stage3_web/hiring_reports` 與 `stage3_web/data/hiring_reports` 各有 5 個 latest JSON | 未來 daily publish 可只推 JSON，不推 DB |

## 引用外部治理概念的狀態

| Concept | 狀態 | 本地落地 |
|---|---|---|
| ZeroSpec | L2 workflow adoption | active truth 文件與 manifests |
| Superpowers | L2 workflow adoption | planning/debug/verification discipline，但受 `AGENTS.md` 約束 |
| basic-memory | L1-L2 | durable docs、pitfalls、ADR，而非聊天記憶 |
| andrej-karpathy-skills | L1 | anti-assumption / minimal-change 行為規則 |
| mattpocock skills | L1-L2 selective | diagnose、grill-with-docs、zoom-out 概念 |
| OPA | L3 local checker | protected path / forbidden action gate |
| Temporal / Prefect | L2 | run mode、state boundary、step unlock |
| Langfuse / OpenTelemetry | L2-L3 local receipt | local JSONL trace / receipt |
| Great Expectations | L3 local tests | schema、row count、negative controls |
| Dagster / Argo | L2 | artifact lineage / allowed dependency surface |

## 不能代表什麼

- 不代表已經初始化獨立 Git repo。
- 不代表可以 push 到 GitHub。
- 不代表可以切 Railway service。
- 不代表可以刪除、搬移或提交任何 protected DB。
- 不代表可以套用到 `群組每日討論`，daily memo 仍要先替換成 Railway Volume `/app/data/users.db` 的 data contract。

## 下一步

1. 以 `manifests/git_include_exclude_dry_run_20260611.yaml` 作為 Git 初始化前的人工審核清單。
2. 使用者確認後，才建立獨立 Git root。
3. Git root 建立後先跑 `check_release_readiness.py`，確認 `root_is_git_root=true` 且 blocker 仍為 0。
4. 再決定 GitHub repo 名稱與 Railway service root directory=`stage3_web`。
5. 徵人需求度 PASS 後，複製治理骨架到 `群組每日討論`，只替換 data contract 與 restore/backup contract。

