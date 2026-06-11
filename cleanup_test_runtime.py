#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clean old test-runtime files under the repo-local _test_runtime folder."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_TARGET = "_test_runtime/tmp"
DEFAULT_RECEIPT_DIR = "_test_runtime/cleanup_receipts"
DEFAULT_REVIEW_FILE = "_test_runtime/cleanup_review_required.md"


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve()


def _assert_safe_target(root: Path, target: Path) -> tuple[Path, Path, Path]:
    root = _resolve(root)
    test_runtime_root = _resolve(root / "_test_runtime")
    target = _resolve(target)
    if target == test_runtime_root:
        raise ValueError("refuse_to_clean_test_runtime_root_directly")
    try:
        target.relative_to(test_runtime_root)
    except ValueError as exc:
        raise ValueError(f"target_outside_test_runtime: {target}") from exc
    return root, test_runtime_root, target


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _last_used_timestamp(path: Path) -> float:
    if path.is_symlink() or path.is_file():
        stat = path.lstat()
        return max(stat.st_atime, stat.st_mtime)
    latest = max(path.stat().st_atime, path.stat().st_mtime)
    for child in path.rglob("*"):
        stat = child.lstat()
        latest = max(latest, stat.st_atime, stat.st_mtime)
    return latest


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def cleanup(root: Path, target: Path, *, older_than_days: int = 7, delete: bool = False) -> dict[str, Any]:
    root, _test_runtime_root, target = _assert_safe_target(root, target)
    now = datetime.now()
    cutoff = now - timedelta(days=older_than_days)
    target.mkdir(parents=True, exist_ok=True)

    candidates: list[dict[str, Any]] = []
    deleted: list[str] = []
    for entry in sorted(target.iterdir(), key=lambda item: item.name):
        last_used = datetime.fromtimestamp(_last_used_timestamp(entry))
        if last_used >= cutoff:
            continue
        record = {
            "path": _relative(entry, root),
            "last_used_at": last_used.isoformat(timespec="seconds"),
            "age_days": round((now - last_used).total_seconds() / 86400, 2),
            "kind": "directory" if entry.is_dir() and not entry.is_symlink() else "file",
        }
        candidates.append(record)
        if delete:
            _remove(entry)
            deleted.append(record["path"])

    user_confirmation_required = bool(candidates and not delete)
    return {
        "receipt_type": "hiring_test_runtime_cleanup",
        "generated_at": now.isoformat(timespec="seconds"),
        "root": str(root),
        "target": _relative(target, root),
        "older_than_days": older_than_days,
        "dry_run_only": not delete,
        "delete_authorized": delete,
        "user_confirmation_required": user_confirmation_required,
        "candidate_count": len(candidates),
        "deleted_count": len(deleted),
        "candidates": candidates,
        "deleted_paths": deleted,
        "suggested_delete_command": f"venv/bin/python3 cleanup_test_runtime.py --older-than-days {older_than_days} --delete",
    }


def write_review_file(receipt: dict[str, Any], review_file: Path) -> None:
    review_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 測試暫存清理確認",
        "",
        f"產生時間：{receipt.get('generated_at', '')}",
        f"掃描目標：`{receipt.get('target', '')}`",
        f"門檻：超過 {receipt.get('older_than_days', '')} 天未使用",
        "",
    ]
    if receipt.get("user_confirmation_required"):
        lines.extend(
            [
                "## 需要使用者確認",
                "",
                "自動掃描發現下列測試暫存項目已超過一週未使用。此掃描沒有刪除任何檔案。",
                "",
            ]
        )
        for item in receipt.get("candidates", []):
            lines.append(f"- `{item.get('path')}`，約 {item.get('age_days')} 天")
        lines.extend(
            [
                "",
                "若確認要刪除，請明確授權後再執行：",
                "",
                "```bash",
                str(receipt.get("suggested_delete_command", "")),
                "```",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## 不需要清理",
                "",
                "本次沒有發現需要詢問刪除的測試暫存項目。",
                "",
            ]
        )
    review_file.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean old repo-local test runtime files.")
    parser.add_argument("--root", default=".", help="Repo root. Defaults to current directory.")
    parser.add_argument("--target", default=DEFAULT_TARGET, help=f"Target under _test_runtime. Default: {DEFAULT_TARGET}")
    parser.add_argument("--older-than-days", type=int, default=7, help="Delete/report entries older than this many days.")
    parser.add_argument("--delete", action="store_true", help="Actually delete candidates. Omit for dry-run.")
    parser.add_argument("--receipt", default=None, help="Optional receipt JSON path.")
    parser.add_argument("--review-file", default=DEFAULT_REVIEW_FILE, help="Markdown review file for user confirmation.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    target = Path(args.target)
    if not target.is_absolute():
        target = root / target
    receipt = cleanup(root, target, older_than_days=args.older_than_days, delete=args.delete)

    receipt_path = Path(args.receipt) if args.receipt else Path(root) / DEFAULT_RECEIPT_DIR / (
        f"test_runtime_cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    if not receipt_path.is_absolute():
        receipt_path = Path(root) / receipt_path
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review_path = Path(args.review_file)
    if not review_path.is_absolute():
        review_path = Path(root) / review_path
    if receipt["dry_run_only"]:
        write_review_file(receipt, review_path)
    print(json.dumps({**receipt, "receipt_json": receipt_path.as_posix(), "review_file": review_path.as_posix()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
