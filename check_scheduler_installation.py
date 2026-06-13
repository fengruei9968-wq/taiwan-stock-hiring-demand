#!/usr/bin/env python3
"""Check the local launcher and LaunchAgent installation for hiring-demand."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path


LABEL_MAIN = "com.hiring.demand.updater"
LABEL_PROBE = "com.hiring.telegram.recipient.probe"
LABEL_STOCK_CODES = "com.hiring.stock.codes.updater"
LABEL_RAW_REVENUE_LISTED_OTC = "com.stock.monthly.revenue.raw.updater"
LABEL_RAW_REVENUE_EMERGING = "com.stock.monthly.revenue.raw.emerging.updater"
LABEL_RAW_REVENUE_MISSING_RETRY = "com.stock.monthly.revenue.raw.missing.retry"
RAW_REVENUE_LABELS = (
    LABEL_RAW_REVENUE_LISTED_OTC,
    LABEL_RAW_REVENUE_EMERGING,
    LABEL_RAW_REVENUE_MISSING_RETRY,
)
OLD_D_DRIVE = "/Users/chiufengjui/D槽/Python"
MAIN_CRAWLER_PROCESS_MARKERS = (
    "HiringDemandLauncher",
    "run_hiring_demand.sh",
    "fetch_hiring_demand.py",
)
PROHIBITED_PLIST_TRIGGER_KEYS = ("StartOnMount", "WatchPaths", "QueueDirectories")


def default_launcher_path() -> Path:
    return Path.home() / "Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh"


def default_local_main_wrapper_path() -> Path:
    return Path.home() / "Library/Application Support/HiringDemandLauncher/run_hiring_demand.sh"


def default_local_probe_wrapper_path() -> Path:
    return Path.home() / "Library/Application Support/HiringDemandLauncher/run_telegram_recipient_probe.sh"


def default_local_stock_codes_wrapper_path() -> Path:
    return Path.home() / "Library/Application Support/HiringDemandLauncher/run_stock_codes_update.sh"


def default_local_raw_revenue_wrapper_path() -> Path:
    return Path.home() / "Library/Application Support/HiringDemandLauncher/run_stock_monthly_revenue_raw.sh"


def default_log_dir() -> Path:
    return Path.home() / "Library/Logs/HiringDemand"


def default_local_venv_dir() -> Path:
    configured = os.environ.get("HIRING_LOCAL_VENV_DIR")
    if configured:
        return Path(configured)
    return Path.home() / "Library/Application Support/HiringDemandLauncher/venv"


def launch_agents_dir() -> Path:
    return Path.home() / "Library/LaunchAgents"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_plist(path: Path) -> dict:
    with path.open("rb") as handle:
        return plistlib.load(handle)


def launchctl_labels() -> set[str]:
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return set()
    labels: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts:
            labels.add(parts[-1])
    return labels


def launchctl_print(label: str) -> subprocess.CompletedProcess[str]:
    uid = os.getuid()
    return subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{label}"],
        check=False,
        capture_output=True,
        text=True,
    )


def process_table() -> str:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid,ppid,stat,etime,command"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return f"PROCESS_TABLE_UNAVAILABLE {exc}"
    return result.stdout


def add_finding(findings: list[dict], severity: str, check_id: str, message: str) -> None:
    findings.append({"severity": severity, "check_id": check_id, "message": message})


def result_from_findings(findings: list[dict]) -> str:
    if any(item["severity"] == "FAIL" for item in findings):
        return "FAIL"
    if findings:
        return "WARN"
    return "PASS"


def emit_receipt(
    *,
    receipt_type: str,
    root: Path,
    findings: list[dict],
    extra: dict | None = None,
    output_dir: str | None = None,
) -> int:
    result = result_from_findings(findings)
    receipt = {
        "receipt_type": receipt_type,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "gate_result": result,
        "finding_count": len(findings),
        "findings": findings,
    }
    if extra:
        receipt.update(extra)
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        receipt_path = out / f"{receipt_type}.json"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt["receipt_path"] = str(receipt_path)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if result == "PASS" else 1


def crawler_process_lines(process_text: str) -> list[str]:
    lines = []
    for line in process_text.splitlines():
        if any(marker in line for marker in MAIN_CRAWLER_PROCESS_MARKERS):
            if "check_scheduler_installation.py" not in line:
                lines.append(line)
    return lines


def check_benchmark_preflight(findings: list[dict]) -> None:
    printed = launchctl_print(LABEL_MAIN)
    if printed.returncode == 0:
        add_finding(
            findings,
            "FAIL",
            "benchmark_main_launchagent_loaded",
            f"Main LaunchAgent must be unloaded before benchmark: {LABEL_MAIN}",
        )

    active_lines = crawler_process_lines(process_table())
    if active_lines:
        add_finding(
            findings,
            "FAIL",
            "benchmark_crawler_process_running",
            "Crawler-related process is still running before benchmark: " + " | ".join(active_lines[:5]),
        )


def check_benchmark_restore(findings: list[dict], expected_launcher: Path) -> None:
    printed = launchctl_print(LABEL_MAIN)
    output = (printed.stdout or "") + "\n" + (printed.stderr or "")
    if printed.returncode != 0:
        add_finding(
            findings,
            "FAIL",
            "benchmark_main_launchagent_not_restored",
            f"Main LaunchAgent is not loaded after benchmark: {LABEL_MAIN}",
        )
        return
    if str(expected_launcher) not in output:
        add_finding(
            findings,
            "FAIL",
            "benchmark_main_launchagent_launcher_mismatch",
            f"Main LaunchAgent must point to local launcher {expected_launcher}",
        )
    if "run-main" not in output:
        add_finding(
            findings,
            "FAIL",
            "benchmark_main_launchagent_mode_missing",
            "Main LaunchAgent must pass run-main to the local launcher",
        )
    if OLD_D_DRIVE in output:
        add_finding(
            findings,
            "FAIL",
            "benchmark_main_launchagent_old_d_drive_path",
            "Main LaunchAgent output contains old D drive path",
        )


def check_plist(
    findings: list[dict],
    plist_path: Path,
    label: str,
    expected_launcher: Path,
    expected_mode: str,
    expected_schedule: dict | None,
) -> None:
    if not plist_path.exists():
        add_finding(findings, "FAIL", f"{label}_plist_missing", f"Missing plist: {plist_path}")
        return
    try:
        plist = load_plist(plist_path)
    except Exception as exc:
        add_finding(findings, "FAIL", f"{label}_plist_unreadable", f"Cannot read plist {plist_path}: {exc}")
        return

    args = [str(item) for item in plist.get("ProgramArguments", [])]
    text = json.dumps(plist, ensure_ascii=False)
    if OLD_D_DRIVE in text:
        add_finding(findings, "FAIL", f"{label}_old_d_drive_path", f"Plist contains old D drive path: {plist_path}")
    for trigger_key in PROHIBITED_PLIST_TRIGGER_KEYS:
        if trigger_key in plist:
            add_finding(
                findings,
                "FAIL",
                f"{label}_prohibited_trigger_{trigger_key}",
                f"Plist must not use {trigger_key}; only the explicit schedule should trigger this job: {plist_path}",
            )
    if not args:
        add_finding(findings, "FAIL", f"{label}_args_missing", f"ProgramArguments missing: {plist_path}")
        return
    if args[0] != str(expected_launcher):
        add_finding(
            findings,
            "FAIL",
            f"{label}_launcher_mismatch",
            f"Expected launcher {expected_launcher}, got {args[0]}",
        )
    if expected_mode not in args[1:]:
        add_finding(findings, "FAIL", f"{label}_mode_missing", f"Expected mode {expected_mode} in {args}")
    if expected_schedule:
        schedule = plist.get("StartCalendarInterval")
        for key, value in expected_schedule.items():
            if not isinstance(schedule, dict) or schedule.get(key) != value:
                add_finding(
                    findings,
                    "FAIL",
                    f"{label}_schedule_mismatch",
                    f"Expected StartCalendarInterval {expected_schedule}, got {schedule}",
                )
                break


def notify_ntfy(topic: str, title: str, message: str) -> tuple[bool, str]:
    request = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers={"Title": title},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status < 300, f"HTTP {response.status}"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Hiring-demand repo root")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--notify-ntfy", action="store_true")
    benchmark_group = parser.add_mutually_exclusive_group()
    benchmark_group.add_argument(
        "--benchmark-preflight",
        action="store_true",
        help="Read-only gate before a benchmark: main LaunchAgent must be unloaded and no crawler process may be running.",
    )
    benchmark_group.add_argument(
        "--benchmark-restore-check",
        action="store_true",
        help="Read-only gate after a benchmark: main LaunchAgent must be restored to the local launcher run-main path.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    launcher = default_launcher_path()
    local_main_wrapper = default_local_main_wrapper_path()
    local_probe_wrapper = default_local_probe_wrapper_path()
    local_stock_codes_wrapper = default_local_stock_codes_wrapper_path()
    local_raw_revenue_wrapper = default_local_raw_revenue_wrapper_path()
    log_dir = default_log_dir()
    local_venv_dir = default_local_venv_dir()
    local_venv_python = local_venv_dir / "bin/python3"
    agents = launch_agents_dir()
    findings: list[dict] = []

    if args.benchmark_preflight:
        check_benchmark_preflight(findings)
        return emit_receipt(
            receipt_type="benchmark_preflight_check",
            root=root,
            findings=findings,
            extra={
                "main_launchagent_label": LABEL_MAIN,
                "probe_launchagent_label": LABEL_PROBE,
                "expected_main_state": "unloaded",
                "process_markers": list(MAIN_CRAWLER_PROCESS_MARKERS),
            },
            output_dir=args.output_dir,
        )

    if args.benchmark_restore_check:
        check_benchmark_restore(findings, launcher)
        return emit_receipt(
            receipt_type="benchmark_restore_check",
            root=root,
            findings=findings,
            extra={
                "main_launchagent_label": LABEL_MAIN,
                "expected_launcher": str(launcher),
                "expected_mode": "run-main",
            },
            output_dir=args.output_dir,
        )

    if not root.exists():
        add_finding(findings, "FAIL", "root_missing", f"Root does not exist: {root}")
    if OLD_D_DRIVE in str(root):
        add_finding(findings, "FAIL", "root_old_d_drive", f"Root points to old D drive: {root}")
    if not launcher.exists():
        add_finding(findings, "FAIL", "launcher_missing", f"Missing local launcher: {launcher}")
    elif not os.access(launcher, os.X_OK):
        add_finding(findings, "FAIL", "launcher_not_executable", f"Local launcher is not executable: {launcher}")
    else:
        text = launcher.read_text(encoding="utf-8", errors="replace")
        if str(root) not in text:
            add_finding(findings, "FAIL", "launcher_root_mismatch", f"Launcher does not reference root: {root}")
        if str(local_venv_python) not in text:
            add_finding(
                findings,
                "FAIL",
                "launcher_local_venv_mismatch",
                f"Launcher does not reference local scheduler venv python: {local_venv_python}",
            )
        if 'export HIRING_PYTHON="$LOCAL_VENV_PYTHON"' not in text:
            add_finding(findings, "FAIL", "launcher_hiring_python_export_missing", "Launcher does not export HIRING_PYTHON")
        if 'export HIRING_SCRIPT_DIR="$HIRING_DIR"' not in text:
            add_finding(findings, "FAIL", "launcher_hiring_script_dir_export_missing", "Launcher does not export HIRING_SCRIPT_DIR")
        for wrapper_path, check_id in [
            (local_main_wrapper, "launcher_local_main_wrapper_mismatch"),
            (local_probe_wrapper, "launcher_local_probe_wrapper_mismatch"),
            (local_stock_codes_wrapper, "launcher_local_stock_codes_wrapper_mismatch"),
            (local_raw_revenue_wrapper, "launcher_local_raw_revenue_wrapper_mismatch"),
        ]:
            if str(wrapper_path) not in text:
                add_finding(findings, "FAIL", check_id, f"Launcher does not reference local wrapper: {wrapper_path}")
        if 'exec "$HIRING_DIR/run_hiring_demand.sh"' in text or 'exec "$HIRING_DIR/run_telegram_recipient_probe.sh"' in text:
            add_finding(
                findings,
                "FAIL",
                "launcher_executes_ssd_shell_wrapper",
                "Launcher must execute internal-disk wrapper copies, not SSD shell wrappers",
            )
        if OLD_D_DRIVE in text:
            add_finding(findings, "FAIL", "launcher_old_d_drive_path", "Launcher contains old D drive path")

    for wrapper_path, check_id in [
        (local_main_wrapper, "local_main_wrapper_missing"),
        (local_probe_wrapper, "local_probe_wrapper_missing"),
        (local_stock_codes_wrapper, "local_stock_codes_wrapper_missing"),
        (local_raw_revenue_wrapper, "local_raw_revenue_wrapper_missing"),
    ]:
        if not wrapper_path.exists():
            add_finding(findings, "FAIL", check_id, f"Missing local wrapper copy: {wrapper_path}")
        elif not os.access(wrapper_path, os.X_OK):
            add_finding(findings, "FAIL", f"{check_id}_not_executable", f"Local wrapper copy is not executable: {wrapper_path}")
        else:
            wrapper_text = wrapper_path.read_text(encoding="utf-8", errors="replace")
            if "HIRING_SCRIPT_DIR" not in wrapper_text:
                add_finding(findings, "FAIL", f"{check_id}_script_dir_override_missing", f"Local wrapper copy does not support HIRING_SCRIPT_DIR: {wrapper_path}")

    if not log_dir.exists():
        add_finding(findings, "WARN", "local_log_dir_missing", f"Missing local log dir: {log_dir}")

    if not local_venv_dir.exists():
        add_finding(findings, "FAIL", "local_scheduler_venv_missing", f"Missing local scheduler venv: {local_venv_dir}")
    elif not os.access(local_venv_python, os.X_OK):
        add_finding(
            findings,
            "FAIL",
            "local_scheduler_venv_python_missing",
            f"Missing local scheduler venv python: {local_venv_python}",
        )

    check_plist(
        findings,
        agents / f"{LABEL_MAIN}.plist",
        LABEL_MAIN,
        launcher,
        "run-main",
        {"Hour": 11, "Minute": 30},
    )
    check_plist(
        findings,
        agents / f"{LABEL_PROBE}.plist",
        LABEL_PROBE,
        launcher,
        "run-probe",
        None,
    )
    check_plist(
        findings,
        agents / f"{LABEL_STOCK_CODES}.plist",
        LABEL_STOCK_CODES,
        launcher,
        "run-stock-codes",
        {"Hour": 5, "Minute": 0},
    )
    check_plist(
        findings,
        agents / f"{LABEL_RAW_REVENUE_LISTED_OTC}.plist",
        LABEL_RAW_REVENUE_LISTED_OTC,
        launcher,
        "run-raw-revenue-listed-otc",
        {"Day": 5, "Hour": 10, "Minute": 10},
    )
    check_plist(
        findings,
        agents / f"{LABEL_RAW_REVENUE_EMERGING}.plist",
        LABEL_RAW_REVENUE_EMERGING,
        launcher,
        "run-raw-revenue-emerging",
        {"Day": 10, "Hour": 10, "Minute": 10},
    )
    check_plist(
        findings,
        agents / f"{LABEL_RAW_REVENUE_MISSING_RETRY}.plist",
        LABEL_RAW_REVENUE_MISSING_RETRY,
        launcher,
        "run-raw-revenue-missing-retry",
        {"Day": 15, "Hour": 10, "Minute": 10},
    )

    loaded = launchctl_labels()
    for label in [LABEL_MAIN, LABEL_PROBE, LABEL_STOCK_CODES, *RAW_REVENUE_LABELS]:
        if label not in loaded:
            add_finding(findings, "WARN", f"{label}_not_loaded", f"LaunchAgent not loaded: {label}")

    result = result_from_findings(findings)

    receipt = {
        "receipt_type": "hiring_scheduler_installation_check",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "local_launcher_path": str(launcher),
        "local_main_wrapper_path": str(local_main_wrapper),
        "local_probe_wrapper_path": str(local_probe_wrapper),
        "local_stock_codes_wrapper_path": str(local_stock_codes_wrapper),
        "local_raw_revenue_wrapper_path": str(local_raw_revenue_wrapper),
        "local_log_dir": str(log_dir),
        "local_scheduler_venv_dir": str(local_venv_dir),
        "local_scheduler_venv_python": str(local_venv_python),
        "gate_result": result,
        "finding_count": len(findings),
        "findings": findings,
    }

    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = output_dir / "hiring_scheduler_installation_receipt.json"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt["receipt_path"] = str(receipt_path)

    if args.notify_ntfy and result != "PASS":
        env = load_env(root / ".env")
        topic = env.get("NTFY_TOPIC") or os.environ.get("NTFY_TOPIC")
        if topic:
            ok, detail = notify_ntfy(
                topic,
                "Hiring Demand Scheduler",
                f"徵人需求度排程需要處理。Scheduler check {result}: {len(findings)} finding(s). Root: {root}",
            )
            receipt["ntfy"] = {"attempted": True, "ok": ok, "detail": detail}
        else:
            receipt["ntfy"] = {"attempted": False, "reason": "NTFY_TOPIC missing"}

    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
