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

Render launchd scheduler templates without installing or loading launchd:

```bash
./install_scheduler.sh --render-only install
./install_scheduler.sh --render-only install-probe
./install_scheduler.sh --render-only install-artifact-backup
./install_scheduler.sh --render-only install-raw-revenue
```

Real scheduler installation requires explicit manual authorization. The committed source of truth is `scheduler_templates/*.plist.template`; root-level `com.*.plist` files are local install artifacts and stay ignored.

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
