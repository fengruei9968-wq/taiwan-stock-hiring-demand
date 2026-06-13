# Hiring Demand Commands

Updated: 2026-06-11

All commands are intended to run from the hiring-demand folder:

```bash
cd "/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度"
```

## No-Live Governance Checks

Syntax check:

```bash
venv/bin/python3 -m py_compile check_release_readiness.py
```

Focused release-readiness tests:

```bash
./run_tests.sh tests/test_release_readiness.py
```

All local unit tests:

```bash
./run_tests.sh
```

`run_tests.sh` sets `TMPDIR` to `_test_runtime/tmp` so temporary test fixtures stay in a repo-local test-only folder on the SSD instead of macOS `/var/folders/...` on the internal disk.

Scan test runtime files older than seven days and write a user-review request:

```bash
venv/bin/python3 cleanup_test_runtime.py --older-than-days 7 --review-file _test_runtime/cleanup_review_required.md
```

Delete old test runtime files after review:

```bash
venv/bin/python3 cleanup_test_runtime.py --older-than-days 7 --delete
```

Daily scanning can be enabled later from `scheduler_templates/com.hiring.test-runtime.cleanup.plist.template`, but the template is not installed or loaded by default. The daily scan only asks for deletion review; it does not pass `--delete`.

Scan PNG/PDF/HTML report artifacts older than 30 days and write a user-review request only:

```bash
venv/bin/python3 cleanup_report_artifacts.py \
  --older-than-days 30 \
  --archive-root "/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/_archives/上市櫃公司徵人需求度" \
  --output-dir _test_runtime/report_artifacts_cleanup_review
```

This command does not move or delete files. It only writes:

```text
_test_runtime/report_artifacts_cleanup_review/report_artifacts_cleanup_review.md
_test_runtime/report_artifacts_cleanup_review/report_artifacts_cleanup_receipt.json
```

Report artifact policy:

- `data/reports/**/*.png`, `data/reports/**/*.pdf`, and `data/reports/**/*.html` are local runtime artifacts for Telegram and human review.
- Railway/GitHub should use `stage3_web/hiring_reports/**/*.json` to rebuild the web summary UI.
- Do not deploy daily PNG/PDF history under `stage3_web/hiring_reports/**` or `stage3_web/data/hiring_reports/**`.
- Archive destinations must be outside this repo under `/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/_archives/上市櫃公司徵人需求度/`.

Render launchd scheduler templates without installing or loading launchd:

```bash
./install_scheduler.sh --render-only install
./install_scheduler.sh --render-only install-probe
./install_scheduler.sh --render-only install-stock-codes
./install_scheduler.sh --render-only install-artifact-backup
./install_scheduler.sh --render-only install-raw-revenue
```

Real scheduler installation requires explicit manual authorization. The committed source of truth is `scheduler_templates/*.plist.template`; root-level `com.*.plist` files are local install artifacts and stay ignored.

Scheduler doctor for a new Mac or after moving the SSD:

```bash
./install_scheduler.sh doctor
./install_scheduler.sh doctor --notify-ntfy
```

Install the internal-disk local launcher plus the main, Telegram recipient probe, and Stock_codes LaunchAgents:

```bash
./install_scheduler.sh install-all-local
```

The local launcher path is:

```text
/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh
```

The local wrapper copies are:

```text
/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand.sh
/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_telegram_recipient_probe.sh
/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_stock_codes_update.sh
```

The local scheduler venv path is:

```text
/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/venv
```

On a new Mac, `./install_scheduler.sh install-all-local` must create this venv from `scheduler_requirements.txt` and install the local wrapper copies; `./install_scheduler.sh doctor --notify-ntfy` is the reminder/check if it was forgotten.

The local launcher log directory is:

```text
/Users/chiufengjui/Library/Logs/HiringDemand/
```

The detailed scheduler contract is documented in `docs/SCHEDULER.md` and `manifests/scheduler_manifest.yaml`.

Stock_codes updater commands:

```bash
./install_scheduler.sh --render-only install-stock-codes
./install_scheduler.sh install-stock-codes
./install_scheduler.sh status-stock-codes
./install_scheduler.sh run-stock-codes
./install_scheduler.sh uninstall-stock-codes
```

The dedicated LaunchAgent label is `com.hiring.stock.codes.updater`. It runs daily at 05:00 and writes local input CSVs under `data/stock_codes/`. The hiring scraper reads `config.yaml` `paths.stock_codes_dir: "data/stock_codes"`.

The old D-slot `com.stock.updater` writes to a different folder. Do not point both jobs at the same Stock_codes output directory.

Main and Stock_codes LaunchAgents must be calendar-only jobs. Confirm they do not contain filesystem-triggered keys:

```bash
plutil -p "$HOME/Library/LaunchAgents/com.hiring.demand.updater.plist" | rg 'StartOnMount|WatchPaths|QueueDirectories' || true
plutil -p "$HOME/Library/LaunchAgents/com.hiring.stock.codes.updater.plist" | rg 'StartOnMount|WatchPaths|QueueDirectories' || true
```

## MOPS Monthly Revenue Refresh

Use this when MOPS official monthly revenue should be refreshed for all repo-local listed, OTC, and emerging companies. This updates local/protected DB state and rebuilds deployable JSON; it must not commit protected DBs or report PNG/PDF files.

Official source URLs:

```text
上市: https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{roc_year}_{month}.csv
上櫃: https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{roc_year}_{month}.csv
興櫃: https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_{roc_year}_{month}.csv
興櫃 fallback: https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_{roc_year}_{month}_0.html
```

Preserve MOPS official percentage columns:

```text
營業收入-上月比較增減(%) -> MoM%
營業收入-去年同月增減(%) -> YoY%
```

Refresh raw MOPS monthly revenue for the current validation window:

```bash
venv/bin/python3 fetch_stock_monthly_revenue_raw.py \
  --start-month 2025-09 \
  --end-month 2026-05 \
  --skip-git \
  --sleep 0
```

Recompute monthly revenue summary for all repo-local Stock_codes companies using MOPS:

```bash
venv/bin/python3 fetch_monthly_revenue.py \
  --source mops \
  --all-stock-codes \
  --skip-git \
  --output-receipt data/reports/monthly_revenue_mops_all_$(date +%Y%m%d)/monthly_revenue_fetch_receipt.json
```

Rebuild report/media/web artifacts from the refreshed DB:

```bash
venv/bin/python3 generate_unlimited_hiring_revenue_report.py \
  --data-dir data \
  --db-path stage3_web/investment.db \
  --latest-manifest-path data/reports/latest_unlimited_hiring_revenue_report_manifest.json

REPORT_MANIFEST="data/reports/latest_unlimited_hiring_revenue_report_manifest.json"
REPORT_KEY="$(venv/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["report_yyyymmdd"])' "$REPORT_MANIFEST")"
REPORT_OUTPUT_DIR="$(venv/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["outputs"]["output_dir"])' "$REPORT_MANIFEST")"

venv/bin/python3 render_unlimited_hiring_revenue_media.py \
  --manifest "$REPORT_MANIFEST" \
  --png-scale 1.5 \
  --png-dpi 150

venv/bin/python3 check_unlimited_hiring_revenue_report.py \
  --manifest "$REPORT_MANIFEST" \
  --output-dir "data/reports/report_media_check_$(date +%Y%m%d_%H%M%S)" \
  --require-media \
  --media-receipt "$REPORT_OUTPUT_DIR/unlimited_hiring_revenue_media_receipt_${REPORT_KEY}.json"

venv/bin/python3 sync_hiring_anomaly_web_artifacts.py \
  --manifest "$REPORT_MANIFEST" \
  --stage3-dir stage3_web
```

Verify a known emerging-company case:

```bash
venv/bin/python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("stage3_web/hiring_reports/latest_hiring_revenue_batch.json").read_text(encoding="utf-8"))
print(json.dumps(payload["data"]["7689"], ensure_ascii=False, indent=2))
PY
```

Expected 2026/5 evidence for 7689 大鵬科 after the 2026-06-13 fix:

```text
months[-1] = 2026/5
mom[-1] = -29.84
yoy[-1] = 19.26
```

Monthly revenue release boundary:

- Allowed release surface: `stage3_web/hiring_reports/**` and `stage3_web/data/hiring_reports/**`.
- Do not stage/commit/push `stage3_web/investment.db`, `.env`, `telegram_recipients.json`, `data/stock_monthly_revenue_raw/**`, `data/reports/**/*.png`, `data/reports/**/*.pdf`, or `data/runs/**`.
- Run `check_release_readiness.py` and `check_hiring_deploy_boundary.py` before any commit/push.

Deploy boundary dry-run:

```bash
venv/bin/python3 check_hiring_deploy_boundary.py \
  --hiring-dir . \
  --stage3-dir stage3_web \
  --output-dir data/runs/deploy_boundary_check_$(date +%Y%m%d_%H%M%S)
```

Release readiness dry-run:

```bash
venv/bin/python3 check_release_readiness.py \
  --root . \
  --output-dir data/runs/release_readiness_$(date +%Y%m%d_%H%M%S)
```

## 104 Detail Lookup Monitor And Resume

The 104 search/list API does not include `needEmp`. The scraper must fetch `needEmp` through per-job detail lookup after company matching. When a run looks slow, inspect detail progress and cache state before restarting.

Check whether a formal run is still alive:

```bash
ps -axo pid,ppid,stat,etime,command | rg '[H]iringDemandLauncher|[f]etch_hiring_demand.py|[r]un_hiring_demand.sh' || true
```

Check latest detail progress and network/DNS failures:

```bash
tail -n 260 launchd_run.log \
  | rg '已查詢 [0-9]+/[0-9]+ 筆職缺詳情|職缺詳情查詢完成|Network is unreachable|Failed to resolve|NameResolutionError|ERROR|Traceback|程式執行完成' \
  | tail -n 80
```

Inspect today's detail cache count:

```bash
CACHE="data/runs/job_detail_cache/$(date +%Y%m%d)_need_emp_cache.json"
DETAIL_CACHE="$CACHE" venv/bin/python3 - <<'PY'
import json
import os
from pathlib import Path
cache = Path(os.environ["DETAIL_CACHE"])
if not cache.exists():
    print(f"cache_missing {cache}")
else:
    payload = json.loads(cache.read_text(encoding="utf-8"))
    print(f"cache={cache} records={len(payload.get('records', {}))} updated_at={payload.get('updated_at')}")
PY
```

Rerun policy:

- If the process is alive and detail progress is increasing, keep monitoring.
- If the process stopped after partial detail lookup, a same-day rerun can resume from cached successful `linkJobId` records.
- If logs show DNS / network failures, fix network first; do not delete the cache.
- Detail cache is local-only runtime state. Do not stage, commit, push, or deploy `data/runs/job_detail_cache/**`.

## Benchmark Isolation

Use this only when measuring the true duration of one complete formal run. It temporarily disables the main daily LaunchAgent so launchd cannot start a second crawler during the benchmark. This does not change committed scheduler templates or the GitHub/Railway deploy contract.

Preflight: unload the main crawler LaunchAgent and verify no crawler process remains.

```bash
UID_NUM="$(id -u)"
MAIN_PLIST="$HOME/Library/LaunchAgents/com.hiring.demand.updater.plist"

launchctl bootout "gui/$UID_NUM" "$MAIN_PLIST" 2>/tmp/hiring_benchmark_bootout.err || true
cat /tmp/hiring_benchmark_bootout.err

ps -axo pid,ppid,stat,etime,command \
  | rg '[H]iringDemandLauncher|[r]un_hiring_demand.sh|[f]etch_hiring_demand.py' || true

launchctl print "gui/$UID_NUM/com.hiring.demand.updater" 2>&1 \
  | sed -n '1,80p' || true

venv/bin/python3 check_scheduler_installation.py \
  --root . \
  --benchmark-preflight \
  --output-dir data/runs/scheduler_benchmark_preflight_$(date +%Y%m%d_%H%M%S)
```

Benchmark rule:

- If `ps` shows any main crawler process, stop and do not start the benchmark.
- If `launchctl print` still shows `com.hiring.demand.updater`, the main LaunchAgent is still loaded; do not start the benchmark.
- If launchd starts another crawler while a benchmark is running, mark that benchmark invalid and rerun after cleanup.
- Use a fresh benchmark cache key when the goal is to avoid same-day detail-cache reuse:

```bash
BENCH_KEY="benchmark_$(date +%H%M%S)"
env HIRING_JOB_DETAIL_CACHE_MODE=refresh \
  HIRING_JOB_DETAIL_CACHE_REFRESH_KEY="$BENCH_KEY" \
  ./run_hiring_demand.sh
```

Restore the main LaunchAgent immediately after the benchmark:

```bash
UID_NUM="$(id -u)"
MAIN_PLIST="$HOME/Library/LaunchAgents/com.hiring.demand.updater.plist"

launchctl bootstrap "gui/$UID_NUM" "$MAIN_PLIST"
launchctl print "gui/$UID_NUM/com.hiring.demand.updater" | sed -n '1,120p'

venv/bin/python3 check_scheduler_installation.py \
  --root . \
  --benchmark-restore-check \
  --output-dir data/runs/scheduler_benchmark_restore_$(date +%Y%m%d_%H%M%S)
```

After restore, confirm the event trigger still points to the daily main job and the local launcher:

```text
/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh
run-main
```

## Live Commands Need Explicit Authorization

These commands can touch external services or production-facing outputs. Do not run them unless the user explicitly asks for a live run:

```bash
./run_hiring_demand.sh
./run_monthly_revenue.sh
./run_stock_monthly_revenue_raw.sh
venv/bin/python3 telegram_sender.py --send-document ...
```

## Git Boundary

Do not run these until the user explicitly authorizes the exact repo initialization or release action:

```bash
git init
git add
git commit
git push
git reset
git restore
git clean
```

When Git is authorized later, release candidates must first pass `check_release_readiness.py`, and daily publish commits must include only:

```text
stage3_web/hiring_reports/**
stage3_web/data/hiring_reports/**
```
