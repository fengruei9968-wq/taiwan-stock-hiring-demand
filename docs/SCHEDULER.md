# Hiring Demand Scheduler

Updated: 2026-06-12

## Plain Summary

The independent hiring-demand project lives on the SSD, but macOS `launchd` should not directly run the SSD scripts. On this machine, `launchd` calendar events triggered correctly, then failed before entering the wrapper with:

```text
Service could not initialize: posix_spawn(/bin/bash), error 0x1 - Operation not permitted
```

The durable setup is:

```text
launchd
-> /Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh
-> /Users/chiufengjui/Library/Application Support/HiringDemandLauncher/venv/bin/python3
-> /Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand.sh
-> HIRING_SCRIPT_DIR=/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度
```

The launcher exports `HIRING_PYTHON` to the internal-disk scheduler venv and `HIRING_SCRIPT_DIR` to the SSD repo before it delegates to an internal-disk wrapper copy. This avoids macOS blocking launchd from executing SSD `.sh` files directly, and avoids background Python reading the external-SSD `venv/pyvenv.cfg`.

Local launcher logs are written to:

```text
/Users/chiufengjui/Library/Logs/HiringDemand/
```

## Paths

| Role | Path |
|---|---|
| SSD active repo | `/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度` |
| Local launcher | `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh` |
| Local main wrapper copy | `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand.sh` |
| Local Telegram probe wrapper copy | `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_telegram_recipient_probe.sh` |
| Local Stock_codes wrapper copy | `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_stock_codes_update.sh` |
| Local scheduler venv | `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/venv` |
| Local scheduler venv Python | `/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/venv/bin/python3` |
| Scheduler requirements | `scheduler_requirements.txt` |
| Local launcher logs | `/Users/chiufengjui/Library/Logs/HiringDemand/` |
| Main LaunchAgent | `/Users/chiufengjui/Library/LaunchAgents/com.hiring.demand.updater.plist` |
| Stock_codes LaunchAgent | `/Users/chiufengjui/Library/LaunchAgents/com.hiring.stock.codes.updater.plist` |
| Telegram probe LaunchAgent | `/Users/chiufengjui/Library/LaunchAgents/com.hiring.telegram.recipient.probe.plist` |

## New Machine First Run

From the SSD repo:

```bash
cd "/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度"
./install_scheduler.sh doctor --notify-ntfy
```

If the local launcher, local scheduler venv, or LaunchAgents are missing, the checker fails. When `NTFY_TOPIC` is available from `.env`, `--notify-ntfy` sends a phone notification.

Install the local launcher and the standard main/probe/Stock_codes LaunchAgents:

```bash
./install_scheduler.sh install-all-local
```

On a new Mac, this command must create the internal-disk scheduler venv. Do not rely on the SSD repo's `venv/` for launchd. The SSD `venv/` can still exist for interactive development, but scheduled jobs should use the local scheduler venv.

## Verification

Self-test the local launcher without running the formal crawler:

```bash
"/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh" self-test
```

Check installed scheduler state:

```bash
./install_scheduler.sh doctor
./install_scheduler.sh status
./install_scheduler.sh status-probe
./install_scheduler.sh status-stock-codes
```

The Stock_codes job should be `05:00` and point to the local launcher with argument `run-stock-codes`. The main daily job should be `11:30` and should point to the local launcher with argument `run-main`; keep this order so the scraper reads a complete Stock_codes CSV.

The main and Stock_codes LaunchAgents must be calendar-only jobs. Do not add `StartOnMount`, `WatchPaths`, or `QueueDirectories`, because external SSD mount events can trigger duplicate formal runs outside the expected 05:00 and 11:30 windows.

The local launcher should export:

```bash
HIRING_PYTHON="/Users/chiufengjui/Library/Application Support/HiringDemandLauncher/venv/bin/python3"
HIRING_SCRIPT_DIR="/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/台股投資資訊系統_完整專案/上市櫃公司徵人需求度"
```

The Telegram recipient probe should point to the same local launcher with argument `run-probe`.

## Stock Codes Scheduler

The hiring-demand project owns its own stock-code/company-name input under:

```text
data/stock_codes/
```

The updater is:

```text
stock_codes_updater.py
```

The scheduler wrapper is:

```text
run_stock_codes_update.sh
```

The LaunchAgent label is:

```text
com.hiring.stock.codes.updater
```

This is intentionally separate from the old D-slot `com.stock.updater`. During transition the old job can remain loaded because it writes to a different D-slot `Stock_codes` folder. Do not configure both jobs to write to the same output directory.

## Benchmark Isolation

When measuring the true duration of a complete formal crawler run, temporarily unload the main LaunchAgent first. This prevents macOS `launchd` from starting a second `run_hiring_demand.sh` while the manual benchmark is already running.

Only the main crawler LaunchAgent is part of this benchmark preflight:

```text
com.hiring.demand.updater
```

The Telegram recipient probe can remain loaded because it must only run recipient discovery and must not call the formal crawler:

```text
com.hiring.telegram.recipient.probe
```

Required benchmark sequence:

1. `bootout` the main crawler LaunchAgent.
2. Confirm `launchctl print gui/$(id -u)/com.hiring.demand.updater` no longer finds the service.
3. Confirm `ps` shows no `HiringDemandLauncher`, `run_hiring_demand.sh`, or `fetch_hiring_demand.py` process.
4. Run the benchmark with a fresh cache key if same-day detail cache must not be reused.
5. `bootstrap` the main crawler LaunchAgent immediately after the benchmark.
6. Confirm `launchctl print gui/$(id -u)/com.hiring.demand.updater` succeeds and still points to the local launcher with `run-main`.

If a second crawler starts during the benchmark, the measurement is invalid. Stop both runs, archive the partial runtime artifacts as invalid benchmark evidence, then rerun from a clean preflight.

## Boundaries

- `self-test` does not run the formal crawler.
- `doctor` is read-only except for optional ntfy notification when `--notify-ntfy` is passed.
- `install-all-local` modifies local macOS launcher and LaunchAgent files only.
- `launchd` must not execute SSD `.sh` files directly; it should execute internal-disk wrapper copies.
- Main and Stock_codes LaunchAgents must not use filesystem-triggered plist keys such as `StartOnMount`, `WatchPaths`, or `QueueDirectories`.
- `com.hiring.stock.codes.updater` writes only `data/stock_codes/**` and `data/runs/stock_codes_update/**`; it does not run the 104 scraper, send Telegram PNG, or deploy.
- Benchmark preflight may temporarily unload only `com.hiring.demand.updater`; restore it immediately after the benchmark.
- Do not commit `.env`, `telegram_recipients.json`, local logs, local launcher output, or protected DB files.
