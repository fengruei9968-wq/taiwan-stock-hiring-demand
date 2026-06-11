# 徵人需求度精準 staging 清單審核

日期：2026-06-11

## 白話結論

第一版 staging 建議只使用 `manifests/first_commit_precise_staging_list_20260611.txt` 內的逐行清單，不使用 `git add .`。

這份清單收的是可維護核心：程式碼、治理文件、manifest、測試、portable scheduler templates、`stage3_web` runtime，以及網頁需要的 `latest_*.json`。它不收 DB、secrets、本機 runtime、raw launchd plist、歷史 bulk data 或 dated web history。

## 建議 staging 指令

等使用者明確授權 staging 後，才可執行：

```bash
git add -- $(cat manifests/first_commit_precise_staging_list_20260611.txt)
```

若遇到路徑含特殊字元或 shell 展開風險，改用逐行安全版本：

```bash
while IFS= read -r path; do
  git add -- "$path"
done < manifests/first_commit_precise_staging_list_20260611.txt
```

本輪沒有執行上述指令。

## 明確排除

- `.env`、`.env.*`
- `telegram_recipients.json`
- `stage3_web/investment.db`
- `stage3_web/data/investment.db`
- `stage3_web/fixed_assets.db`
- `stage3_web/data/users.db`
- `venv/`
- `_test_runtime/`
- `_local_runtime/`
- root-level `com.*.plist`
- `data/reports/`、`data/runs/`、`data/revenue_snapshots/`、`data/stock_monthly_revenue_raw/`
- `stage3_web/hiring_reports/YYYYMMDD/`
- `stage3_web/data/hiring_reports/YYYYMMDD/`

## Staging 後必跑

```bash
git diff --cached --name-only
./run_tests.sh
venv/bin/python3 check_release_readiness.py --root . --output-dir data/runs/release_readiness_post_stage_$(date +%Y%m%d_%H%M%S)
venv/bin/python3 check_hiring_deploy_boundary.py --hiring-dir . --stage3-dir stage3_web --output-dir data/runs/deploy_boundary_post_stage_$(date +%Y%m%d_%H%M%S)
```

如果 cached files 出現 protected DB、secret、本機 runtime、raw plist 或歷史 bulk artifact，必須停止，不得 commit。
