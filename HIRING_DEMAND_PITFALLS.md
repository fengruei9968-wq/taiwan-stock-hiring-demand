# 徵人需求度踩坑紀錄

更新日期：2026-06-06

## 目的

這份紀錄只管理 `上市櫃公司徵人需求度` 資料夾內已踩過、容易重複發生、會影響自動排程或對外通知的問題。遇到相同類型問題時，不得只在聊天中說明；必須補到文件、skill、checker 或 regression test。

## 2026-05-16：Telegram token / chat_id 遮罩與 receipt 文字破壞

白話：Telegram sender / probe 會讀 `.env` 裡的 bot token 與 chat id。這類資料不能出現在聊天、receipt、log 或 commit 內容裡；同時也不能因為 chat id 是空字串，就把整份 JSON receipt 的每個字元中間塞入遮罩字串，造成 receipt 壞掉。

工程化：

- 觸發情境：`telegram_sender.py` 或 `telegram_recipient_probe.py` 需要 sanitize Telegram 回應、error message、receipt JSON。
- 根因：`sanitize_text()` 若對空字串 `chat_id` 執行 `.replace("", mask)`，Python 會把 mask 插入每個字元間，導致 JSON receipt 被破壞。
- 必要規則：只有 `bot_token` 或 `chat_id` 非空時才可執行 replace。
- 必要 evidence：receipt 只能保留 `chat_id_masked`，不得保留完整 chat id；不得保留 bot token。
- Regression test：`tests/test_telegram_sender.py::test_sanitize_text_does_not_corrupt_text_when_chat_id_is_empty`。
- Fan-out test：`tests/test_telegram_sender.py::test_send_document_fans_out_to_enabled_recipients` 必須確認 enabled recipients 才會發送，disabled 與重複 chat id 會被排除。
- Probe test：`tests/test_telegram_recipient_probe.py` 必須確認只收 `/start`，並以 chat id 去重。

PASS 代表什麼：

- sender / probe 的 receipt 不會曝光 bot token 或完整 chat id。
- 空 `chat_id` 不會再破壞 JSON receipt。
- 多接收者 fan-out 可以由 dry-run 或 mock test 證明。

還不能代表什麼：

- 不能代表 Telegram 每位實際接收者都已收圖；正式送出仍要看當次 `telegram_send_receipt_*.json`。
- 不能代表朋友已加入清單；朋友必須先對 bot 發 `/start`，再跑 `telegram_recipient_probe.py` 寫入本機 ignored `telegram_recipients.json`。
- 不能代表 `.env` 或 `telegram_recipients.json` 可以 commit；兩者仍屬本機敏感設定。

後續維護規則：

1. 修改 Telegram sender / probe 時，先跑 `tests/test_telegram_sender.py` 與 `tests/test_telegram_recipient_probe.py`。
2. 新增 receipt 欄位時，必須確認 token 與完整 chat id 不會進入 JSON / MD / stdout。
3. 若需要顯示接收者，只能顯示 label、name、username 與 `chat_id_masked`。
4. `telegram_recipients.json` 必須保持 ignored；只可 commit `telegram_recipients.example.json`。
5. governance checker 必須檢查本踩坑紀錄、Telegram sender/probe、tests 與 skill 文件同步。

## 2026-05-17：Telegram recipient opt-out 被 hourly probe 覆蓋

白話：使用者明確指定某位朋友不要接收 PNG 後，`telegram_recipients.json` 會把該 recipient 設為 `enabled=false`。但每小時 probe 再次掃到同一個人曾發過 `/start` 時，如果直接用新掃到的 `enabled=true` 覆蓋舊資料，就會把已停用的人重新加入發送名單。

工程化：

- 觸發情境：`telegram_recipient_probe.py` upsert 既有 recipient，且既有資料 `enabled=false`。
- 根因：probe 產出的 `/start` recipient 預設 `enabled=true`，舊邏輯 `current.update(recipient)` 沒保留 opt-out 狀態。
- 必要規則：既有 recipient 若 `enabled=false`，probe 只能更新名稱、username、source、last seen 類資訊，不得自動改回 `enabled=true`。
- 必要 evidence：sender dry-run receipt 必須證明 enabled fan-out 名單不含已 opt-out recipient，且完整 chat id 仍被遮罩。
- Regression test：`tests/test_telegram_recipient_probe.py::test_upsert_recipients_file_preserves_disabled_opt_out`。

PASS 代表什麼：

- hourly probe 再次看到 `/start` 時，不會自動恢復已停用收件人。
- daily sender 的 dry-run / receipt 可以用 `recipient_count` 與 masked recipient list 證明 fan-out 邊界。

還不能代表什麼：

- 不能回收已經誤送出的 Telegram 訊息。
- 不能代表 Telegram bot 使用者清單等於正式接收名單；正式接收名單仍以本機 ignored `telegram_recipients.json` 的 `enabled=true` 為準。

## 2026-05-19：報表 PASS 但 Telegram / 網頁部署沒有真正送出

白話：11:30 排程有可能完成 scraper、checker、PNG/PDF render 與 web artifact sync，但如果 `.env` 缺少正式開關，wrapper 只會留下本機 artifact，不會送 Telegram，也不會 commit / push 到網頁。這種狀態不能回報成「每日自動發送與網頁端都完成」。

工程化：

- 觸發情境：`launchd_run.log` 出現 `Telegram sendDocument 未啟用` 或 `未開啟 deploy mode`。
- 根因：`.env` 未設定 `HIRING_TELEGRAM_SEND_MODE=enabled` 與 / 或 `HIRING_DEMAND_DEPLOY_MODE=deploy`。
- 必要規則：每日正式 closeout 不能只看 report checker、media checker 或 web sync receipt PASS；還必須確認 Telegram receipt 與 stage3_web git push evidence。
- Telegram 必要 evidence：`telegram_send_receipt_YYYYMMDD*.json` 內 `gate_result=PASS`、`dry_run=false`、`document.sent=true`、`recipient_count=2`，且 recipients 只包含 `.env` 預設接收者與 `Kwolf0 / lin yc`；`Tsaiball / 菜圃` 必須維持 disabled。
- 網頁部署必要 evidence：`hiring_anomaly_web_sync_receipt_YYYYMMDD.json` PASS 只代表本機 sync；還要有 `stage3_web` commit / push，以及 Railway 未登入 smoke `hiring-demand -> 302 /login`、protected API `401`。
- 敏感資訊邊界：`.env`、完整 token、完整 chat id、`telegram_recipients.json` 不得 commit，不得在 receipt 或聊天中曝光。

PASS 代表什麼：

- `.env` 開關為 enabled / deploy 時，下一次每日 wrapper 會嘗試自動送 Telegram 與自動部署網頁。
- 當天若有正式 `telegram_send_receipt` 與 `stage3_web` push evidence，才可說當天 Telegram 與網頁部署完成。

還不能代表什麼：

- 不能代表 Telegram API、GitHub push、Railway deploy 未來一定成功；每天仍要看當次 receipt / git / smoke evidence。
- 不能代表使用者已在手機或登入後網頁實際看見內容；receipt 只證明系統送出 / 部署邊界。

## 2026-06-06：104 已抓到，但正式頁查不到公司

白話：`4770 上品` 這次不是 104 沒抓到。本機最新 `investment.db` 與職缺明細都有 `4770`，但正式網站 `/hiring-demand` 當時還顯示 `2026/05/25 12:42:15 已更新`，搜尋 `4770` 回 `共 0 家公司`。根因是正式頁表格讀 deployed `investment.db`，而每日安全部署只 push `hiring_reports/` 與 `data/hiring_reports/`，不 push protected 大 DB。

工程化：

- 觸發情境：本機 `hiring_demand` / `hiring_demand_jobs` 已有最新公司，但 Chrome 正式頁搜尋不到，且頁面更新日期落後。
- 根因：資料發布 surface 只包含異常摘要 JSON，沒有完整表格 JSON；`/api/hiring-demand` 仍依賴 deployed `investment.db`。
- 必要規則：`sync_hiring_anomaly_web_artifacts.py` 必須匯出 `hiring_demand_web_data_v1`，包含 `data` 與 `jobs_by_stock_code`。
- 必要 deploy copy：`stage3_web/hiring_reports/latest_hiring_demand_web_data.json`、`stage3_web/data/hiring_reports/latest_hiring_demand_web_data.json`，以及 dated `hiring_demand_web_data_YYYYMMDD.json`。
- API 規則：`stage3_web/app.py` 的 `/api/hiring-demand` 與 `/api/hiring-demand/jobs/<stock_code>` 優先讀 web data JSON；JSON 缺檔或壞檔才 fallback 到 DB。
- Closeout 規則：正式站 Chrome gate 必須登入後確認更新日期，並用本輪指定或新增公司搜尋；不能只看未登入 route smoke。
- Typed failure：若本機 artifact 有資料但正式頁舊日期 / 查不到，分類為 `web_data_publication_stale`，修復動作是檢查 JSON artifact、commit/push、Railway deploy 與 bounded Chrome recheck，不是重跑 104。
- Regression tests：`stage3_web/tests/test_hiring_web_data_api.py`、`上市櫃公司徵人需求度/tests/test_unlimited_hiring_revenue_report.py::test_sync_web_artifacts_copies_summary_and_receipts_to_deployable_stage3_dirs`。

PASS 代表什麼：

- 正式表格可以不靠 protected `investment.db` commit/push 取得最新徵人需求度列表。
- `4770` 類「本機已抓到但網頁查不到」問題可由 publication layer 自動修復，而不是誤判為 104 scraping failure。

還不能代表什麼：

- 不能代表 Railway 立即部署完成；剛 push 後仍需 bounded recheck。
- 不能代表 104 外部資料永遠正確；只代表本輪已抓到的資料能安全發布到正式頁。
