#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dry-run report artifact cleanup planner for hiring-demand PNG/PDF outputs."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_ARCHIVE_ROOT = Path(
    "/Volumes/Extreme SSD/Python/台股子公司投資資訊擷取與展示/_archives/上市櫃公司徵人需求度"
)
REPORT_EXTENSIONS = {".png", ".pdf", ".html"}


@dataclass
class CleanupCandidate:
    path: str
    size_bytes: int
    mtime: str
    age_days: float
    archive_destination: str
    reason: str


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def archive_destination_for(path: Path, root: Path, archive_root: Path) -> Path:
    relative = path.relative_to(root)
    parts = relative.parts
    if len(parts) >= 3 and parts[0] == "data" and parts[1] == "reports":
        report_key = parts[2]
        year = report_key[:4] if len(report_key) >= 4 and report_key[:4].isdigit() else "unknown_year"
        month = report_key[4:6] if len(report_key) >= 6 and report_key[4:6].isdigit() else "unknown_month"
        return archive_root / "report_artifacts" / year / month / relative
    return archive_root / "report_artifacts" / "misc" / relative


def find_candidates(root: Path, archive_root: Path, older_than_days: int, now: float | None = None) -> list[CleanupCandidate]:
    now_ts = now if now is not None else datetime.now().timestamp()
    reports_root = root / "data" / "reports"
    if not reports_root.exists():
        return []

    candidates: list[CleanupCandidate] = []
    for path in sorted(reports_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in REPORT_EXTENSIONS:
            continue
        stat = path.stat()
        age_days = (now_ts - stat.st_mtime) / 86400
        if age_days < older_than_days:
            continue
        candidates.append(
            CleanupCandidate(
                path=rel(path, root),
                size_bytes=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                age_days=round(age_days, 2),
                archive_destination=str(archive_destination_for(path, root, archive_root)),
                reason=f"report artifact older than {older_than_days} days",
            )
        )
    return candidates


def write_review(output_dir: Path, root: Path, archive_root: Path, older_than_days: int, candidates: list[CleanupCandidate]) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "receipt_type": "hiring_report_artifacts_cleanup_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "archive_root": str(archive_root),
        "older_than_days": older_than_days,
        "dry_run_only": True,
        "action": "review_required",
        "candidate_count": len(candidates),
        "total_size_bytes": sum(item.size_bytes for item in candidates),
        "candidates": [asdict(item) for item in candidates],
    }
    (output_dir / "report_artifacts_cleanup_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Report Artifacts Cleanup Review",
        "",
        f"- Root: `{root}`",
        f"- Archive root: `{archive_root}`",
        f"- Older than days: `{older_than_days}`",
        f"- Dry run only: `true`",
        f"- Candidate count: `{len(candidates)}`",
        f"- Total size bytes: `{receipt['total_size_bytes']}`",
        "",
        "No files were moved or deleted. Review these candidates before authorizing archive or deletion.",
        "",
        "| Path | Size bytes | Age days | Proposed archive destination |",
        "|---|---:|---:|---|",
    ]
    for item in candidates:
        lines.append(f"| `{item.path}` | {item.size_bytes} | {item.age_days} | `{item.archive_destination}` |")
    (output_dir / "report_artifacts_cleanup_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a dry-run review for old hiring-demand PNG/PDF/HTML report artifacts.")
    parser.add_argument("--root", default=".", help="Hiring-demand project root.")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT), help="Repo-external archive root for proposed destinations.")
    parser.add_argument("--output-dir", default="_test_runtime/report_artifacts_cleanup_review", help="Where to write review receipt and markdown.")
    parser.add_argument("--older-than-days", type=int, default=30, help="Candidate age threshold.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    archive_root = Path(args.archive_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    candidates = find_candidates(root, archive_root, args.older_than_days)
    receipt = write_review(output_dir, root, archive_root, args.older_than_days, candidates)
    print(json.dumps({key: receipt[key] for key in ["receipt_type", "candidate_count", "total_size_bytes", "dry_run_only"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
