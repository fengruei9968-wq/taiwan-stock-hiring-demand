#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync hiring anomaly summary artifacts into the deployable stage3_web tree."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_manifest_path(manifest_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate
    manifest_candidate = manifest_path.parent / path
    if manifest_candidate.exists():
        return manifest_candidate
    return cwd_candidate


def copy_artifact(source: Path, target: Path, blockers: list[dict[str, str]]) -> bool:
    if not source.exists():
        blockers.append(
            {
                "finding_type": "missing_web_sync_source",
                "affected_file": str(source),
                "required_fix": "先重新產生 report/media artifact，再同步到 stage3_web。",
            }
        )
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def _sqlite_rows(conn: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def build_hiring_web_data(manifest: dict[str, Any]) -> dict[str, Any]:
    db_path = Path(str(manifest.get("db_path", ""))).expanduser()
    report_date = str(manifest.get("report_date", "")).strip()
    report_key = str(manifest.get("report_yyyymmdd", "")).strip()
    if not db_path.exists():
        raise FileNotFoundError(f"missing hiring demand db: {db_path}")
    if not report_date:
        raise ValueError("manifest.report_date is required for web data export")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        latest_created_at_row = conn.execute(
            """
            SELECT MAX(created_at) AS latest_created_at
            FROM hiring_demand
            WHERE fetch_date = ?
            """,
            (report_date,),
        ).fetchone()
        latest_created_at = latest_created_at_row[0] if latest_created_at_row else None
        demand_rows = _sqlite_rows(
            conn,
            """
            SELECT stock_code, company_short_name, company_full_name, market_type,
                   employee_count, explicit_need, unlimited_job_count,
                   unspecified_job_count, total_job_count, demand_ratio, fetch_date
            FROM hiring_demand
            WHERE fetch_date = ?
            ORDER BY demand_ratio DESC
            """,
            (report_date,),
        )
        job_rows = _sqlite_rows(
            conn,
            """
            SELECT stock_code, job_name, link_job_id, need_emp_raw, need_emp,
                   is_unlimited, is_unspecified, fetch_date
            FROM hiring_demand_jobs
            WHERE fetch_date = ?
            ORDER BY stock_code, is_unlimited DESC, need_emp DESC, job_name
            """,
            (report_date,),
        )
    finally:
        conn.close()

    data: list[dict[str, Any]] = []
    for row in demand_rows:
        data.append(
            {
                "stock_code": row.get("stock_code"),
                "company_short_name": row.get("company_short_name"),
                "company_full_name": row.get("company_full_name"),
                "market_type": row.get("market_type"),
                "employee_count": row.get("employee_count") or 0,
                "explicit_need": row.get("explicit_need") or 0,
                "unlimited_job_count": row.get("unlimited_job_count") or 0,
                "unspecified_job_count": row.get("unspecified_job_count") or 0,
                "total_job_count": row.get("total_job_count") or 0,
                "demand_ratio": round(row.get("demand_ratio") or 0, 2),
            }
        )

    jobs_by_stock_code: dict[str, list[dict[str, Any]]] = {}
    for row in job_rows:
        stock_code = str(row.get("stock_code") or "")
        link_job_id = row.get("link_job_id") or ""
        if row.get("is_unlimited"):
            need_display = "不限"
        elif row.get("is_unspecified"):
            need_display = "未標示"
        else:
            need_display = row.get("need_emp_raw") or str(row.get("need_emp") or 0)
        jobs_by_stock_code.setdefault(stock_code, []).append(
            {
                "job_name": row.get("job_name"),
                "job_url": f"https://www.104.com.tw/job/{link_job_id}" if link_job_id else "",
                "need_display": need_display,
                "is_unlimited": bool(row.get("is_unlimited")),
                "is_unspecified": bool(row.get("is_unspecified")),
            }
        )

    return {
        "schema_version": "hiring_demand_web_data_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_manifest_report_key": report_key,
        "source_manifest_generated_at": manifest.get("generated_at", ""),
        "fetch_date": report_date,
        "latest_created_at_utc": latest_created_at,
        "data": data,
        "jobs_by_stock_code": jobs_by_stock_code,
        "counts": {
            "company_count": len(data),
            "job_count": len(job_rows),
        },
    }


def write_hiring_web_data(manifest: dict[str, Any], target_roots: dict[str, Path], blockers: list[dict[str, str]]) -> dict[str, str]:
    copied: dict[str, str] = {}
    report_key = str(manifest.get("report_yyyymmdd", "")).strip()
    try:
        payload = build_hiring_web_data(manifest)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        blockers.append(
            {
                "finding_type": "hiring_web_data_export_failed",
                "affected_file": str(manifest.get("db_path", "")),
                "required_fix": f"修復 hiring_demand web data export：{exc}",
            }
        )
        return copied

    for root_label, target_root in target_roots.items():
        target_dir = target_root / report_key
        target_dir.mkdir(parents=True, exist_ok=True)
        dated_path = target_dir / f"hiring_demand_web_data_{report_key}.json"
        latest_path = target_root / "latest_hiring_demand_web_data.json"
        for label, path in {
            f"{root_label}_hiring_web_data": dated_path,
            f"{root_label}_latest_hiring_web_data": latest_path,
        }.items():
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            copied[label] = str(path)
    return copied


def _revenue_month_sort_key(label: Any) -> tuple[int, int]:
    try:
        year, month = str(label).split("/", 1)
        return int(year), int(month)
    except (TypeError, ValueError):
        return 0, 0


def normalize_hiring_revenue_row(row: dict[str, Any], window_months: int = 6) -> dict[str, Any]:
    month_map: dict[str, dict[str, Any]] = {}
    for index in range(1, window_months + 1):
        label = row.get(f"m{index}_label")
        if not label:
            continue
        month_map[str(label)] = {
            "mom": row.get(f"m{index}_mom"),
            "yoy": row.get(f"m{index}_yoy"),
        }

    items = sorted(month_map.items(), key=lambda item: _revenue_month_sort_key(item[0]))
    items = items[-window_months:]
    padding = [(None, {"mom": None, "yoy": None})] * (window_months - len(items))
    items = padding + items
    return {
        "months": [label for label, _ in items],
        "mom": [values.get("mom") for _, values in items],
        "yoy": [values.get("yoy") for _, values in items],
        "window_months": window_months,
    }


def build_hiring_revenue_batch(manifest: dict[str, Any]) -> dict[str, Any]:
    db_path = Path(str(manifest.get("db_path", ""))).expanduser()
    report_key = str(manifest.get("report_yyyymmdd", "")).strip()
    report_date = str(manifest.get("report_date", "")).strip()
    if not db_path.exists():
        raise FileNotFoundError(f"missing hiring demand db: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = _sqlite_rows(conn, "SELECT * FROM monthly_revenue_summary", ())
    finally:
        conn.close()

    data = {str(row.get("stock_code")): normalize_hiring_revenue_row(row) for row in rows if row.get("stock_code")}
    updated_values = [row.get("updated_at") for row in rows if row.get("updated_at")]
    return {
        "schema_version": "hiring_revenue_batch_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_manifest_report_key": report_key,
        "source_manifest_generated_at": manifest.get("generated_at", ""),
        "report_date": report_date,
        "data": data,
        "count": len(data),
        "updated_at": max(updated_values) if updated_values else None,
        "window_months": 6,
    }


def write_hiring_revenue_batch(manifest: dict[str, Any], target_roots: dict[str, Path], blockers: list[dict[str, str]]) -> dict[str, str]:
    copied: dict[str, str] = {}
    report_key = str(manifest.get("report_yyyymmdd", "")).strip()
    try:
        payload = build_hiring_revenue_batch(manifest)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        blockers.append(
            {
                "finding_type": "hiring_revenue_batch_export_failed",
                "affected_file": str(manifest.get("db_path", "")),
                "required_fix": f"修復 hiring revenue batch export：{exc}",
            }
        )
        return copied

    for root_label, target_root in target_roots.items():
        target_dir = target_root / report_key
        target_dir.mkdir(parents=True, exist_ok=True)
        dated_path = target_dir / f"hiring_revenue_batch_{report_key}.json"
        latest_path = target_root / "latest_hiring_revenue_batch.json"
        for label, path in {
            f"{root_label}_hiring_revenue_batch": dated_path,
            f"{root_label}_latest_hiring_revenue_batch": latest_path,
        }.items():
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            copied[label] = str(path)
    return copied


def sync_artifacts(manifest_path: Path, stage3_dir: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    report_key = str(manifest.get("report_yyyymmdd", ""))
    output_dir = resolve_manifest_path(manifest_path, str(manifest.get("outputs", {}).get("output_dir", "")))
    anomaly_summary = resolve_manifest_path(manifest_path, str(manifest.get("outputs", {}).get("anomaly_summary_json", "")))
    canonical_manifest = resolve_manifest_path(manifest_path, str(manifest.get("outputs", {}).get("manifest", manifest_path)))
    media_receipt = output_dir / f"unlimited_hiring_revenue_media_receipt_{report_key}.json"

    primary_target_root = stage3_dir / "hiring_reports"
    legacy_data_target_root = stage3_dir / "data" / "hiring_reports"
    target_roots = {
        "deploy": primary_target_root,
        "legacy_data": legacy_data_target_root,
    }
    blockers: list[dict[str, str]] = []
    copied: dict[str, str] = {}
    target_dirs: dict[str, str] = {}

    for root_label, target_root in target_roots.items():
        target_dir = target_root / report_key
        target_dirs[root_label] = str(target_dir)
        targets = {
            "anomaly_summary": (anomaly_summary, target_dir / f"anomaly_summary_{report_key}.json"),
            "report_manifest": (canonical_manifest, target_dir / f"unlimited_hiring_revenue_report_manifest_{report_key}.json"),
            "media_receipt": (media_receipt, target_dir / f"unlimited_hiring_revenue_media_receipt_{report_key}.json"),
        }
        for key, (source, target) in targets.items():
            if copy_artifact(source, target, blockers):
                copied[f"{root_label}_{key}"] = str(target)

        latest_targets = {
            "latest_anomaly_summary": (target_dir / f"anomaly_summary_{report_key}.json", target_root / "latest_anomaly_summary.json"),
            "latest_report_manifest": (
                target_dir / f"unlimited_hiring_revenue_report_manifest_{report_key}.json",
                target_root / "latest_unlimited_hiring_revenue_report_manifest.json",
            ),
            "latest_media_receipt": (
                target_dir / f"unlimited_hiring_revenue_media_receipt_{report_key}.json",
                target_root / "latest_unlimited_hiring_revenue_media_receipt.json",
            ),
        }
        for key, (source, target) in latest_targets.items():
            if copy_artifact(source, target, blockers):
                copied[f"{root_label}_{key}"] = str(target)

    copied.update(write_hiring_web_data(manifest, target_roots, blockers))
    copied.update(write_hiring_revenue_batch(manifest, target_roots, blockers))

    receipt = {
        "receipt_type": "hiring_anomaly_web_artifact_sync",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_path": str(manifest_path),
        "stage3_dir": str(stage3_dir),
        "target_dir": str(primary_target_root / report_key),
        "target_dirs": target_dirs,
        "report_yyyymmdd": report_key,
        "report_date": manifest.get("report_date", ""),
        "copied": copied,
        "typed_blockers": blockers,
        "gate_result": "PASS" if not blockers else "FAIL",
    }
    for target_dir_text in target_dirs.values():
        target_dir = Path(target_dir_text)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / f"hiring_anomaly_web_sync_receipt_{report_key}.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync hiring anomaly JSON artifacts to deployable stage3_web/hiring_reports.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--stage3-dir", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    receipt = sync_artifacts(Path(args.manifest), Path(args.stage3_dir))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["gate_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
