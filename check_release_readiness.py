#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only release-readiness gate for the independent hiring-demand repo candidate."""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_FILES = [
    "AGENTS.md",
    "docs/CURRENT_EXECUTION.md",
    "docs/COMMANDS.md",
    "docs/ADR/ADR-001-governance-import-policy.md",
    "manifests/repo_manifest.yaml",
    "manifests/data_contract.yaml",
    "manifests/allowed_entrypoints.yaml",
    "run_tests.sh",
    "install_scheduler.sh",
    "cleanup_test_runtime.py",
    "scheduler_templates/com.hiring.daily.artifacts.backup.plist.template",
    "scheduler_templates/com.hiring.demand.updater.plist.template",
    "scheduler_templates/com.hiring.telegram.recipient.probe.plist.template",
    "scheduler_templates/com.hiring.test-runtime.cleanup.plist.template",
    "scheduler_templates/com.monthly.revenue.updater.plist.template",
    "scheduler_templates/com.stock.monthly.revenue.raw.emerging.updater.plist.template",
    "scheduler_templates/com.stock.monthly.revenue.raw.missing.retry.plist.template",
    "scheduler_templates/com.stock.monthly.revenue.raw.updater.plist.template",
    "tests/test_release_readiness.py",
    "tests/test_cleanup_test_runtime.py",
    "check_hiring_deploy_boundary.py",
    "check_hiring_runtime_governance.py",
    "check_release_readiness.py",
]

RUNTIME_REQUIRED_FILES = [
    "stage3_web/app.py",
    "stage3_web/templates/hiring_demand.html",
    "stage3_web/static/css/style.css",
    "stage3_web/Procfile",
    "stage3_web/requirements.txt",
]

MANIFEST_MARKERS = {
    "manifests/repo_manifest.yaml": [
        "schema_version: hiring_repo_manifest_v1",
        "railway:",
        "root_directory: stage3_web",
        "daily_publish_allowed_paths:",
        "protected_paths:",
        "check_release_readiness.py",
    ],
    "manifests/data_contract.yaml": [
        "schema_version: hiring_data_contract_v1",
        "source_of_truth:",
        "web_artifact_contract:",
        "latest_hiring_demand_web_data.json",
        "telegram_contract:",
        "protected_secrets:",
    ],
    "manifests/allowed_entrypoints.yaml": [
        "schema_version: hiring_allowed_entrypoints_v1",
        "release_readiness_check",
        "deploy_boundary_check",
        "hiring_scraper_wrapper",
        "telegram_sender",
        "forbidden_entrypoint_patterns:",
    ],
}

PROTECTED_PATHS = [
    ".env",
    ".env.*",
    "telegram_recipients.json",
    "stage3_web/investment.db",
    "stage3_web/data/investment.db",
    "stage3_web/fixed_assets.db",
    "stage3_web/data/users.db",
]

LOCAL_ONLY_PATTERNS = [
    "venv/**",
    "_local_runtime/**",
    "_test_runtime/**",
    "__pycache__/**",
    "tests/__pycache__/**",
    "stage3_web/__pycache__/**",
    "logs/**",
    "*.log",
    "Backup/**",
]

DEPLOY_JSON_FILES = [
    "stage3_web/hiring_reports/latest_hiring_demand_web_data.json",
    "stage3_web/hiring_reports/latest_hiring_revenue_batch.json",
    "stage3_web/hiring_reports/latest_hiring_revenue_amounts.json",
    "stage3_web/hiring_reports/latest_anomaly_summary.json",
    "stage3_web/hiring_reports/latest_unlimited_hiring_revenue_report_manifest.json",
    "stage3_web/hiring_reports/latest_unlimited_hiring_revenue_media_receipt.json",
]

ALLOWED_DAILY_PUBLISH_PATTERNS = [
    "stage3_web/hiring_reports/**",
    "stage3_web/data/hiring_reports/**",
]


@dataclass
class Finding:
    severity: str
    finding_type: str
    affected_file: str
    plain_description: str
    required_fix: str


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def is_ignored(root: Path, path: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", "--", path],
        cwd=root,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def git_status_for_paths(root: Path, paths: list[str]) -> tuple[str, list[str]]:
    proc = subprocess.run(
        ["git", "-C", str(root), "status", "--short", "--"] + paths,
        cwd=root,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        return "git_status_unavailable", []
    return "available", [line for line in proc.stdout.splitlines() if line.strip()]


def git_root(root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def check_required_files(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for item in REQUIRED_FILES + RUNTIME_REQUIRED_FILES:
        if not (root / item).exists():
            findings.append(
                Finding(
                    "blocker",
                    "missing_required_file",
                    item,
                    "標準治理骨架或 Railway runtime 必要檔案不存在。",
                    "補回必要檔案，或更新 manifest 後重跑 release readiness checker。",
                )
            )
    return findings


def check_manifest_markers(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for rel_path, markers in MANIFEST_MARKERS.items():
        path = root / rel_path
        if not path.exists():
            continue
        text = read_text(path)
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "blocker",
                        "missing_manifest_marker",
                        rel_path,
                        f"manifest 缺少必要標記 `{marker}`。",
                        "補齊 manifest 欄位，讓 Codex/Claude 與 checker 都能讀懂 release contract。",
                    )
                )
    return findings


def check_git_and_local_only(root: Path) -> tuple[list[Finding], dict[str, Any]]:
    findings: list[Finding] = []
    ignored = {pattern: is_ignored(root, pattern.replace("/**", "")) for pattern in LOCAL_ONLY_PATTERNS}
    for path in [".env", "telegram_recipients.json", "venv", "__pycache__", "logs"]:
        if (root / path).exists() and not is_ignored(root, path):
            findings.append(
                Finding(
                    "blocker",
                    "local_only_path_not_ignored",
                    path,
                    "本機-only 或秘密檔案存在，但沒有被 Git ignore 擋住。",
                    "更新 .gitignore，確認秘密、venv、cache、log 不會進入 release candidate。",
                )
            )

    status_state, status_lines = git_status_for_paths(root, PROTECTED_PATHS)
    for line in status_lines:
        path = line[3:].strip()
        if matches_any(path, PROTECTED_PATHS):
            findings.append(
                Finding(
                    "blocker",
                    "protected_path_dirty_or_staged",
                    path,
                    "protected path 出現在 Git status 中；目前不得納入 release candidate。",
                    "不要 stage/commit protected path；先確認是否只是本機狀態或需要人工處理。",
                )
            )

    top = git_root(root)
    git_scope = {
        "git_root": top,
        "root_is_git_root": top == str(root),
        "status_state": status_state,
        "protected_status_lines": status_lines,
        "local_only_ignore_probe": ignored,
    }
    if top and top != str(root):
        findings.append(
            Finding(
                "warning",
                "not_independent_git_root_yet",
                str(root),
                "此資料夾目前仍掛在上層 Git worktree 之下，尚未成為乾淨獨立 repo。",
                "正式初始化 GitHub repo 前，先用 dry-run manifest 決定 include/exclude，不要直接 git add。",
            )
        )
    return findings, git_scope


def check_deploy_json(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for rel_path in DEPLOY_JSON_FILES:
        path = root / rel_path
        if not path.exists():
            findings.append(
                Finding(
                    "blocker",
                    "missing_deploy_json",
                    rel_path,
                    "網頁 deploy copy 的 latest JSON 不存在。",
                    "重跑 web artifact sync，或確認該 JSON 是否不應列為 release 必要檔。",
                )
            )
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                Finding(
                    "blocker",
                    "invalid_deploy_json",
                    rel_path,
                    f"網頁 deploy JSON 無法解析：{exc}",
                    "修復 JSON 來源並重跑 web artifact sync。",
                )
            )
            continue
        if rel_path.endswith("latest_hiring_demand_web_data.json"):
            schema_version = payload.get("schema_version")
            data = payload.get("data")
            counts = payload.get("counts")
            if schema_version != "hiring_demand_web_data_v1" or not isinstance(data, list) or len(data) <= 0:
                findings.append(
                    Finding(
                        "blocker",
                        "invalid_hiring_web_data_payload",
                        rel_path,
                        "徵人需求度 web data JSON 缺 schema_version=hiring_demand_web_data_v1 或非空 data list。",
                        "確認 `sync_hiring_anomaly_web_artifacts.py` 匯出的 payload schema。",
                    )
                )
            if not isinstance(counts, dict):
                findings.append(
                    Finding(
                        "blocker",
                        "invalid_hiring_web_data_payload",
                        rel_path,
                        "徵人需求度 web data JSON 缺 counts 摘要。",
                        "確認 web data JSON 保留 counts，讓 release checker 可驗證網頁資料規模。",
                    )
                )
        if rel_path.endswith("latest_hiring_revenue_batch.json"):
            if payload.get("window_months") != 6 or int(payload.get("count", 0) or 0) <= 0:
                findings.append(
                    Finding(
                        "blocker",
                        "invalid_revenue_batch_payload",
                        rel_path,
                        "月營收 batch JSON 缺 window_months=6 或 count > 0。",
                        "重建月營收 web artifact 後重跑 checker。",
                    )
                )
        if rel_path.endswith("latest_hiring_revenue_amounts.json"):
            if payload.get("schema_version") != "hiring_revenue_amounts_v1" or int(payload.get("count", 0) or 0) <= 0:
                findings.append(
                    Finding(
                        "blocker",
                        "invalid_revenue_amounts_payload",
                        rel_path,
                        "月營收金額 snapshot JSON 缺 schema_version=hiring_revenue_amounts_v1 或 count > 0。",
                        "重建月營收金額 web artifact 後重跑 checker。",
                    )
                )
    return findings


def check_allowed_publish_surface(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for rel_path in DEPLOY_JSON_FILES:
        if not matches_any(rel_path, ALLOWED_DAILY_PUBLISH_PATTERNS):
            findings.append(
                Finding(
                    "blocker",
                    "deploy_json_outside_allowed_surface",
                    rel_path,
                    "deploy JSON 不在 allowed daily publish surface 內。",
                    "更新 allowed surface 或搬回 `stage3_web/hiring_reports/**`。",
                )
            )
    for rel_path in PROTECTED_PATHS:
        if matches_any(rel_path, ALLOWED_DAILY_PUBLISH_PATTERNS):
            findings.append(
                Finding(
                    "blocker",
                    "protected_path_allowed_for_publish",
                    rel_path,
                    "protected path 被包含進 daily publish surface。",
                    "修正 manifest，daily publish 不得包含 DB 或秘密檔。",
                )
            )
    return findings


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["severity", "finding_type", "affected_file", "plain_description", "required_fix"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_receipt(root: Path, output_dir: Path, findings: list[Finding], git_scope: dict[str, Any]) -> dict[str, Any]:
    blocker_count = sum(1 for item in findings if item.severity == "blocker")
    warning_count = sum(1 for item in findings if item.severity == "warning")
    counts = Counter(item.finding_type for item in findings)
    return {
        "receipt_type": "hiring_release_readiness_check",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "gate_result": "PASS" if blocker_count == 0 else "FAIL",
        "dry_run_only": True,
        "release_commit_authorized": False,
        "live_scrape_authorized": False,
        "telegram_send_authorized": False,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "finding_counts": dict(counts),
        "railway_root_directory": "stage3_web",
        "allowed_daily_publish_patterns": ALLOWED_DAILY_PUBLISH_PATTERNS,
        "protected_paths": PROTECTED_PATHS,
        "git_scope": git_scope,
        "outputs": {
            "receipt_json": str(output_dir / "hiring_release_readiness_receipt.json"),
            "typed_blockers_csv": str(output_dir / "typed_blockers.csv"),
        },
    }


def run_check(root: Path, output_dir: Path) -> dict[str, Any]:
    root = root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    findings: list[Finding] = []
    findings.extend(check_required_files(root))
    findings.extend(check_manifest_markers(root))
    git_findings, git_scope = check_git_and_local_only(root)
    findings.extend(git_findings)
    findings.extend(check_deploy_json(root))
    findings.extend(check_allowed_publish_surface(root))

    receipt = build_receipt(root, output_dir, findings, git_scope)
    (output_dir / "hiring_release_readiness_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(output_dir / "typed_blockers.csv", [asdict(item) for item in findings])
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run hiring-demand release readiness without mutating files.")
    parser.add_argument("--root", default=".", help="Hiring-demand repo candidate root.")
    parser.add_argument("--output-dir", required=True, help="Output directory for release-readiness receipt.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    receipt = run_check(Path(args.root), Path(args.output_dir))
    return 0 if receipt["gate_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
