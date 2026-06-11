# Hiring Demand Git Root Decision

Date: 2026-06-11

## 白話結論

使用者已確認：整個 `上市櫃公司徵人需求度` 資料夾作為未來獨立 Git repo root，Railway root directory 設為 `stage3_web`。

這代表未來不是只把 `stage3_web` 拆出去，也不是只把爬蟲或報表拆出去；徵人需求度的 scraper、月營收 pipeline、報表、Telegram、governance、tests、manifest 與 web runtime 會留在同一個主題 repo。Railway 只部署 repo 內的 `stage3_web` 子目錄。

這還不代表已授權 `git init`、`git add`、commit、push、GitHub 建 repo 或 Railway 切 service。那些仍是下一個獨立授權點。

## Confirmed Decision

| Item | Decision |
|---|---|
| Git repo root | `/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度` |
| Railway root directory | `stage3_web` |
| Repo strategy | one topic, one complete repo |
| Web deployment strategy | deploy web runtime from `stage3_web` |
| Daily data publish strategy | JSON artifacts only, no protected DB commit |

## Still Not Authorized

- `git init`
- `git add`
- `git commit`
- `git push`
- GitHub repo creation
- Railway service creation or reassignment
- Protected DB movement, deletion, restore, staging, or commit
- Telegram live send
- Formal scraper rerun

## Required Before Git Init

1. Review `manifests/git_init_rehearsal_plan_20260611.yaml`.
2. Confirm the initial commit policy for historical `data/` artifacts.
3. Confirm whether launchd `.plist` files should be committed as-is or converted to templates first.
4. Confirm `.gitignore` rules for independent repo root.
5. Run post-init rehearsal checks only after explicit Git initialization authorization.

