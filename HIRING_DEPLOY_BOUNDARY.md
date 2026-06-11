# 徵人需求度 Deploy Boundary

更新日期：2026-06-11

## 白話結論

徵人需求度的 pipeline source of truth 在這個獨立資料夾本身。資料夾內的 `stage3_web/` 是徵人需求度專用網站 runtime 與每天可部署的報表 JSON copy；不要再依賴上一層共用 `stage3_web`。

## 邊界分類

| 類別 | 路徑 | 規則 |
|---|---|---|
| pipeline source of truth | `fetch_hiring_demand.py`、`data/runs/`、`data/reports/`、`data/revenue_snapshots/` | 原始爬蟲、probe、report、receipt、checker 與 durable artifacts 都以這裡為準。 |
| web runtime | `stage3_web/app.py`、`stage3_web/templates/hiring_demand.html`、`stage3_web/static/css/style.css` | Flask route、API、模板與 CSS 必須留在資料夾內部 `stage3_web`。目前獨立版模板使用內嵌 JavaScript，不依賴共用站 `static/js/tree.js`。 |
| deployable web copy | `stage3_web/hiring_reports`、`stage3_web/data/hiring_reports` | 只放 `sync_hiring_anomaly_web_artifacts.py` 從 pipeline artifacts / 本輪 DB 匯出的網站可讀 JSON。包含每日異常摘要與 `latest_hiring_demand_web_data.json` 完整表格資料；這是網站可讀 copy，不是 source of truth。 |
| forbidden commit/push surface | `stage3_web/investment.db`、`stage3_web/data/investment.db`、`stage3_web/fixed_assets.db`、`stage3_web/data/users.db` | 徵人需求度自動部署不得 stage / commit / push 這些 DB。 |

## Allowed Publish Surface

每日徵人需求度自動發布只允許 stage / commit / push：

```text
stage3_web/hiring_reports/**
stage3_web/data/hiring_reports/**
```

其他 `stage3_web` 檔案若需要修改，必須是獨立 web app 變更，不得混在每日資料發布或 scraper harness commit 裡。內部 `stage3_web` 初始化成獨立 Git repo 之前，deploy mode 必須停止在 local sync，不得假裝已 commit / push。

`/api/hiring-demand` 正式頁資料來源優先讀 `stage3_web/hiring_reports/latest_hiring_demand_web_data.json`，缺檔或壞檔才退回 `stage3_web/investment.db`。這讓每日網頁表格能隨小型 JSON artifact 部署，不需要 commit / push protected `investment.db`。

## Checker

使用：

```bash
cd /Volumes/Extreme\ SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度
venv/bin/python3 check_hiring_deploy_boundary.py \
  --hiring-dir . \
  --stage3-dir stage3_web \
  --output-dir data/runs/deploy_boundary_check_$(date +%Y%m%d_%H%M%S)
```

這個 checker 只做 read-only 檢查，不搬檔、不 restore、不 stage、不 commit、不 push。
