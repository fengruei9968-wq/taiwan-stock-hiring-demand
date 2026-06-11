# 徵人需求度第一版 Git commit 範圍審核

日期：2026-06-11

## 白話結論

第一版 commit 建議只納入可維護、可部署、可讓 Codex / Claude 接手的核心內容：source、治理文件、manifest、tests、`stage3_web` runtime、以及 `latest_*.json` 網頁資料。

不要把 `git add .` 當下一步。這個資料夾剛成為獨立 Git root，全部檔案都是 untracked；下一步必須用 manifest 裡的明確清單做精準 staging。

## 建議納入

- repo 治理：`AGENTS.md`、`docs/`、`manifests/`
- source / checker：徵人需求度擷取、月營收、報告、Telegram、治理與 release checker
- tests：`tests/*.py`
- test tooling：`run_tests.sh`、`cleanup_test_runtime.py`
- scheduler template：`install_scheduler.sh`、`scheduler_templates/*.plist.template`
- Railway runtime：`stage3_web/app.py`、`Procfile`、`requirements.txt`、templates、static
- deploy latest JSON：`stage3_web/hiring_reports/latest_*.json`、`stage3_web/data/hiring_reports/latest_*.json`
- 歷史參考：`docs/history/config_20260412_v1.yaml`、`docs/history/run_hiring_demand_20260412_v1.sh`，已標明非 active truth

## 不應納入

- secrets：`.env`、`.env.*`、`telegram_recipients.json`
- protected DB：`stage3_web/investment.db`、`stage3_web/data/investment.db`、`stage3_web/fixed_assets.db`、`stage3_web/data/users.db`
- local runtime：`venv/`、`_test_runtime/`、logs、cache、Backup
- 歷史 bulk：`data/reports/`、`data/runs/`、`data/revenue_snapshots/`、`data/stock_monthly_revenue_raw/`
- dated web history：`stage3_web/hiring_reports/YYYYMMDD/`、`stage3_web/data/hiring_reports/YYYYMMDD/`

## 需要人工確認

- root-level launchd render output：`com.*.plist`

root-level `com.*.plist` 是本機 install/render artifact，不納入 first commit。portable active truth 已改為 `scheduler_templates/*.plist.template`，由 `install_scheduler.sh` 在明確授權時 render / install。

`config_20260412_v1.yaml` 與 `run_hiring_demand_20260412_v1.sh` 已移到 `docs/history/`，只作歷史參考；尤其舊 wrapper 含舊式 DB commit/push 流程，不可作 active entrypoint。

## 工程佐證

- `git diff --cached --name-only`：空，尚未 stage
- protected / local-only ignore probe：PASS
- include candidate not-ignore probe：PASS
- manifest：`manifests/first_commit_scope_20260611.yaml`

下一步授權點：精準 staging 清單審核。仍不得使用 `git add .`。
