# 徵人需求度 SSD 遷移狀態（2026-06-10）

## 白話結論

徵人需求度 pipeline 已整理成可從資料夾所在位置推導專案根目錄的形式，並已同步到 SSD 正式 workspace。launchd 相關排程已重新安裝，現在指向 SSD 路徑；本機原資料夾保留不刪，SSD 同步前也已備份舊 SSD 副本。

## 正式路徑

- 本機來源：`/Users/chiufengjui/D槽/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度`
- SSD 正式路徑：`/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度`
- SSD Stock_codes 依賴：`/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股上市櫃公司名稱確認與自動定時更新/Stock_codes`
- SSD web runtime 依賴：`/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/stage3_web`

## 已完成

- `run_hiring_demand.sh`、`run_telegram_recipient_probe.sh`、`run_monthly_revenue.sh`、`run_stock_monthly_revenue_raw.sh`、`backup_hiring_daily_artifacts.sh` 改為由 `BASH_SOURCE[0]` 推導所在資料夾與 project root。
- `config.yaml` 改為 project-relative path；`fetch_hiring_demand.py` 支援 `HIRING_PROJECT_ROOT`、`STOCK_CODES_DIR`、`DB_PATH`、`HIRING_OUTPUT_DIR` 覆蓋。
- `fetch_stock_monthly_revenue_raw.py` 與 `generate_unlimited_hiring_revenue_report.py` 改為從目前 project root 推導預設依賴。
- `install_scheduler.sh` 會安裝時把 plist 內的 canonical 本機 project root 重寫成當前 project root，並會先 unload 再 load 主排程。
- `stage3_web/run_monthly_revenue.sh` 改為由自身位置推導 project root，不再寫死本機路徑。
- SSD 舊徵人資料夾已備份後，以 rsync 同步本機整理後資料夾到 SSD。
- launchd 主爬蟲、Telegram recipient probe、每日產物備份、raw 月營收三個排程已從 SSD installer 重新安裝。

## 備份與 receipt

- SSD 舊徵人資料夾備份：`/Volumes/Extreme SSD/Python_backup/hiring_demand_before_ssd_sync_20260610_204224/上市櫃公司徵人需求度`
- rsync receipt：`/Volumes/Extreme SSD/Python_backup/hiring_demand_ssd_sync_receipts/20260610_204224/manifest.txt`
- launchd 切換前 plist 備份：`/Volumes/Extreme SSD/Python_backup/hiring_demand_launchagents_before_ssd_switch_20260610_204438`

## 驗證結果

- 本機 `tests.test_hiring_pipeline_path_contract`：PASS
- SSD `tests.test_hiring_pipeline_path_contract`：PASS
- 本機與 SSD shell syntax：PASS
- 本機與 SSD Python compile：PASS
- SSD `check_hiring_deploy_boundary.py`：PASS
- SSD `check_hiring_runtime_governance.py`：PASS
- launchd installed plist 已確認 `ProgramArguments` 與 `WorkingDirectory` 指向 `/Volumes/Extreme SSD/...`。

## 注意事項

- 本次未刪除本機徵人資料夾。
- 本次未 stage / commit / push。
- 本次未修改、複製或提交 protected DB：`stage3_web/investment.db`、`stage3_web/data/investment.db`、`stage3_web/fixed_assets.db`、`stage3_web/data/users.db`。
- 自動爬蟲發布目前依賴 SSD 掛載於 `/Volumes/Extreme SSD`；主爬蟲 plist 有 `StartOnMount=true`，SSD 掛載後 launchd 可重新觸發排程條件。
- 2026-06-10 當日 104 主爬蟲已完成 CSV / DB / manifest，但不等於當日報表、Telegram 與 Railway 發布已完成；完整發布仍需 checker、report、media、web sync、Telegram、deploy evidence。
