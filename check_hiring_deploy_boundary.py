#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only deploy-boundary check for hiring-demand web artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


DEPLOY_COPY_DIRS = ["hiring_reports", "data/hiring_reports"]
FORBIDDEN_COMMIT_PATHS = [
    "stage3_web/investment.db",
    "stage3_web/data/investment.db",
    "stage3_web/fixed_assets.db",
    "stage3_web/data/users.db",
]


@dataclass
class Finding:
    finding_type: str
    affected_file: str
    required_fix: str


def check_required_paths(hiring_dir: Path, stage3_dir: Path) -> list[Finding]:
    required_paths = [
        hiring_dir / "fetch_hiring_demand.py",
        hiring_dir / "probe_104_search_api.py",
        hiring_dir / "sync_hiring_anomaly_web_artifacts.py",
        hiring_dir / "HIRING_DEPLOY_BOUNDARY.md",
        stage3_dir / "app.py",
        stage3_dir / "templates" / "hiring_demand.html",
        stage3_dir / "static" / "css" / "style.css",
        stage3_dir / "hiring_reports",
        stage3_dir / "data" / "hiring_reports",
    ]
    findings: list[Finding] = []
    for path in required_paths:
        if not path.exists():
            findings.append(
                Finding(
                    "missing_required_boundary_path",
                    str(path),
                    "Restore the expected pipeline/web boundary path or update the boundary contract.",
                )
            )
    return findings


def check_sync_script(hiring_dir: Path) -> list[Finding]:
    script = hiring_dir / "sync_hiring_anomaly_web_artifacts.py"
    if not script.exists():
        return []
    text = script.read_text(encoding="utf-8", errors="ignore")
    findings: list[Finding] = []
    required_markers = [
        'stage3_dir / "hiring_reports"',
        'stage3_dir / "data" / "hiring_reports"',
        "latest_hiring_demand_web_data.json",
        "hiring_demand_web_data_v1",
        "shutil.copy2",
        "hiring_anomaly_web_artifact_sync",
    ]
    forbidden_markers = [
        "investment.db",
        "data/users.db",
        "fixed_assets.db",
        "git add",
        "git commit",
        "git push",
    ]
    for marker in required_markers:
        if marker not in text:
            findings.append(
                Finding(
                    "missing_sync_boundary_marker",
                    str(script),
                    f"Keep sync script constrained to deployable report copies; missing marker: {marker}",
                )
            )
    for marker in forbidden_markers:
        if marker in text:
            findings.append(
                Finding(
                    "forbidden_sync_boundary_marker",
                    str(script),
                    f"Sync script must not touch DB or git operations; remove marker: {marker}",
                )
            )
    return findings


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["finding_type", "affected_file", "required_fix"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_check(hiring_dir: Path, stage3_dir: Path, output_dir: Path) -> dict[str, object]:
    hiring_dir = hiring_dir.resolve()
    stage3_dir = stage3_dir.resolve()
    findings = check_required_paths(hiring_dir, stage3_dir)
    findings.extend(check_sync_script(hiring_dir))
    finding_rows = [asdict(item) for item in findings]
    counts = Counter(item.finding_type for item in findings)
    receipt = {
        "receipt_type": "hiring_deploy_boundary_check",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "hiring_dir": str(hiring_dir),
        "stage3_dir": str(stage3_dir),
        "gate_result": "PASS" if not findings else "FAIL",
        "deploy_copy_dirs": DEPLOY_COPY_DIRS,
        "forbidden_commit_paths": FORBIDDEN_COMMIT_PATHS,
        "typed_blocker_count": len(findings),
        "typed_blocker_counts": dict(counts),
        "outputs": {
            "receipt_json": str(output_dir / "hiring_deploy_boundary_receipt.json"),
            "typed_blockers_csv": str(output_dir / "typed_blockers.csv"),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "hiring_deploy_boundary_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(output_dir / "typed_blockers.csv", finding_rows)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check hiring-demand deploy boundary without mutating files.")
    parser.add_argument("--hiring-dir", required=True)
    parser.add_argument("--stage3-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    receipt = run_check(Path(args.hiring_dir), Path(args.stage3_dir), Path(args.output_dir))
    return 0 if receipt["gate_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
