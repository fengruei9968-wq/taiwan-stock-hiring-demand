# 徵人需求度 Git 初始化 rehearsal 結果

日期：2026-06-11

## 白話結論

這次已在徵人需求度獨立資料夾內完成 `git init` rehearsal。現在這個資料夾本身就是 Git root，第一版可以用「整個 `上市櫃公司徵人需求度` 當 repo、Railway root directory 設 `stage3_web`」的方式往下一步審核。

這次沒有做 `git add`、沒有 commit、沒有 push，也沒有建立 GitHub / Railway 資源，沒有跑正式爬蟲，沒有送 Telegram。

## 工程化結果

- Git root：`/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度`
- `git diff --cached --name-only`：空，代表沒有 staged files
- `check_release_readiness.py`：PASS，blocker 0，warning 0
- `check_hiring_deploy_boundary.py`：PASS，typed blocker 0
- `tests/test_release_readiness.py`：PASS，3 tests OK

## Ignore 邊界

已確認下列類型不會進入第一版 Git 候選：

- secrets：`.env`、`.env.*`、`telegram_recipients.json`
- protected DB：`stage3_web/investment.db`、`stage3_web/data/investment.db`、`stage3_web/fixed_assets.db`、`stage3_web/data/users.db`
- local runtime：`venv/`、`__pycache__/`、`*.log`、`logs/`、`Backup/`
- 大型歷史資料：`data/reports/`、`data/runs/`、`data/revenue_snapshots/`、`data/stock_monthly_revenue_raw/`
- web dated history：`stage3_web/hiring_reports/YYYYMMDD/`、`stage3_web/data/hiring_reports/YYYYMMDD/`

已確認下列類型仍會留在第一版 Git 候選：

- governance：`AGENTS.md`、`docs/`、`manifests/`
- checker/test：`check_release_readiness.py`、`tests/test_release_readiness.py`
- web runtime：`stage3_web/app.py`、`stage3_web/Procfile`、`stage3_web/requirements.txt`、`stage3_web/templates/`、`stage3_web/static/`
- deploy latest JSON：`stage3_web/hiring_reports/latest_*.json`、`stage3_web/data/hiring_reports/latest_*.json`

## Fresh Verification

```text
git rev-parse --show-toplevel
=> /Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度

venv/bin/python3 check_release_readiness.py --root . --output-dir data/runs/release_readiness_post_init_rehearsal2_20260611_162940
=> gate_result PASS, blocker_count 0, warning_count 0

venv/bin/python3 check_hiring_deploy_boundary.py --hiring-dir . --stage3-dir stage3_web --output-dir data/runs/deploy_boundary_post_init_rehearsal2_20260611_162940
=> gate_result PASS, typed_blocker_count 0

TMPDIR="$PWD/data/runs/tmp_unittest_rehearsal_20260611" venv/bin/python3 -m unittest tests/test_release_readiness.py
=> Ran 3 tests, OK
```

## 注意事項

第一次直接跑 unittest 時，macOS 預設暫存目錄在內建磁碟 `/var/folders/...`，因 `/` 只剩約 117MiB 而失敗。這不是測試邏輯失敗；改用 SSD 專案內 ignored runtime 目錄作為 `TMPDIR` 後，同一組測試通過。

下一步授權點是「staging/first commit scope review」。仍不應直接 `git add .`、commit 或 push。
