# 徵人需求度 scheduler template 整理報告

日期：2026-06-11

## 白話結論

已把 root-level raw `com.*.plist` 從第一版 commit 候選移出，改以 `scheduler_templates/*.plist.template` 作為可提交的 scheduler active truth。

`install_scheduler.sh` 現在從 template render plist；用 `--render-only` 時只輸出到 `_local_runtime/launchd_rendered/`，不安裝、不載入 launchd。真正安裝仍需要使用者明確授權。

## 納入 first commit

- `install_scheduler.sh`
- `scheduler_templates/com.hiring.demand.updater.plist.template`
- `scheduler_templates/com.hiring.telegram.recipient.probe.plist.template`
- `scheduler_templates/com.hiring.daily.artifacts.backup.plist.template`
- `scheduler_templates/com.hiring.test-runtime.cleanup.plist.template`
- `scheduler_templates/com.monthly.revenue.updater.plist.template`
- `scheduler_templates/com.stock.monthly.revenue.raw.updater.plist.template`
- `scheduler_templates/com.stock.monthly.revenue.raw.emerging.updater.plist.template`
- `scheduler_templates/com.stock.monthly.revenue.raw.missing.retry.plist.template`

## 不納入 first commit

- root-level `com.*.plist`
- `_local_runtime/**`

這些是本機 render / install output，不是 source of truth。

## 工程佐證

```text
./run_tests.sh
=> Ran 86 tests, OK

check_release_readiness.py
=> PASS, blocker_count 0, warning_count 0

check_hiring_deploy_boundary.py
=> PASS, typed_blocker_count 0

plutil -lint scheduler_templates/*.plist.template _local_runtime/launchd_rendered/*.plist
=> all OK
```

`git check-ignore` 已確認：

- root-level `com.*.plist` 被 ignore
- `_local_runtime/` 被 ignore
- `scheduler_templates/*.plist.template` 留在 commit 候選

## 邊界

本輪沒有執行 `git add`、commit、push，也沒有載入 launchd。
