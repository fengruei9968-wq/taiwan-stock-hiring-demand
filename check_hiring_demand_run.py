#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only gate for hiring-demand CSV and DB outputs."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


EXPECTED_HEADER = [
    "股票代碼",
    "公司簡稱",
    "公司全名",
    "市場類別",
    "員工人數",
    "明確需求人數",
    "不限職缺數",
    "未標示職缺數",
    "總職缺數",
    "徵人需求度",
    "更新時間",
]
VALID_RUN_MODES = {"scrape-only", "write-db", "deploy"}


@dataclass
class Finding:
    finding_type: str
    plain_description: str
    affected_file: str
    affected_key: str
    required_fix: str


def read_csv_rows(path: Path) -> tuple[list[str] | None, list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_int(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def to_float(value: Any) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def db_scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def load_db_rows(db_path: Path, fetch_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[Finding]]:
    findings: list[Finding] = []
    if not db_path.exists():
        return [], [], [
            Finding(
                "missing_db",
                "manifest 指向的 investment.db 不存在。",
                str(db_path),
                fetch_date,
                "確認 db_path 或先完成 write-db run。",
            )
        ]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        demand_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT stock_code, company_short_name, company_full_name, market_type,
                       employee_count, explicit_need, unlimited_job_count,
                       unspecified_job_count, total_job_count, demand_ratio, fetch_date
                FROM hiring_demand
                WHERE fetch_date = ?
                """,
                (fetch_date,),
            )
        ]
        job_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT stock_code, job_name, link_job_id, need_emp_raw, need_emp,
                       is_unlimited, is_unspecified, fetch_date
                FROM hiring_demand_jobs
                WHERE fetch_date = ?
                """,
                (fetch_date,),
            )
        ]
        return demand_rows, job_rows, findings
    except sqlite3.Error as exc:
        findings.append(
            Finding(
                "db_schema_error",
                f"資料庫 schema 或查詢失敗: {exc}",
                str(db_path),
                fetch_date,
                "確認 hiring_demand / hiring_demand_jobs schema 後重跑 checker。",
            )
        )
        return [], [], findings
    finally:
        conn.close()


def validate_special_values(rows: list[dict[str, str]], csv_path: Path) -> list[Finding]:
    findings: list[Finding] = []
    for row in rows:
        code = row.get("股票代碼", "")
        emp_count = to_int(row.get("員工人數"))
        explicit = to_int(row.get("明確需求人數"))
        unlimited = to_int(row.get("不限職缺數"))
        unspecified = to_int(row.get("未標示職缺數"))
        ratio = to_float(row.get("徵人需求度"))

        if ratio == 999.0 and not (explicit == 0 and unlimited > 0):
            findings.append(
                Finding(
                    "invalid_unlimited_ratio",
                    "徵人需求度為 999.0 時，明確需求人數必須為 0 且不限職缺數必須大於 0。",
                    str(csv_path),
                    code,
                    "修正 parse_need_emp / aggregate_company_data 後重跑。",
                )
            )
        elif ratio == 998.0 and not (explicit == 0 and unlimited == 0 and unspecified > 0):
            findings.append(
                Finding(
                    "invalid_unspecified_ratio",
                    "徵人需求度為 998.0 時，必須是只有未標示職缺。",
                    str(csv_path),
                    code,
                    "修正 needEmp 空值分類後重跑。",
                )
            )
        elif 0.0 <= ratio < 998.0 and explicit > 0 and emp_count > 0:
            expected = round((explicit / emp_count) * 100, 2)
            if abs(expected - ratio) > 0.01:
                findings.append(
                    Finding(
                        "demand_ratio_mismatch",
                        f"徵人需求度應為 {expected}，但 CSV 為 {ratio}。",
                        str(csv_path),
                        code,
                        "修正需求度計算或來源數值後重跑。",
                    )
                )
        elif ratio < 0 or ratio > 999.0:
            findings.append(
                Finding(
                    "invalid_demand_ratio_range",
                    "徵人需求度只能是 0..999 之間的數值。",
                    str(csv_path),
                    code,
                    "修正輸出 normalization 後重跑。",
                )
            )
    return findings


def validate_csv_db_alignment(
    csv_rows: list[dict[str, str]],
    db_rows: list[dict[str, Any]],
    job_rows: list[dict[str, Any]],
    csv_path: Path,
    db_path: Path,
) -> list[Finding]:
    findings: list[Finding] = []
    if len(csv_rows) != len(db_rows):
        findings.append(
            Finding(
                "db_csv_row_count_mismatch",
                f"CSV row count {len(csv_rows)} 與 hiring_demand DB row count {len(db_rows)} 不一致。",
                str(db_path),
                "row_count",
                "確認 fetch_date、CSV path、DB path 是否同一輪，必要時重跑 write-db。",
            )
        )

    csv_by_code = {row.get("股票代碼", ""): row for row in csv_rows}
    db_by_code = {str(row.get("stock_code", "")): row for row in db_rows}
    if len(csv_by_code) != len(csv_rows):
        findings.append(
            Finding(
                "duplicate_stock_code",
                "CSV 同一天輸出含重複股票代碼。",
                str(csv_path),
                "股票代碼",
                "修正 company matching 或 aggregation 後重跑。",
            )
        )

    for code, csv_row in csv_by_code.items():
        db_row = db_by_code.get(code)
        if not db_row:
            findings.append(
                Finding(
                    "missing_db_row",
                    "CSV 公司在 hiring_demand DB 當日資料中不存在。",
                    str(db_path),
                    code,
                    "確認 DB 寫入與 fetch_date 後重跑 checker。",
                )
            )
            continue
        comparisons = [
            ("公司簡稱", "company_short_name", str),
            ("公司全名", "company_full_name", str),
            ("市場類別", "market_type", str),
            ("員工人數", "employee_count", to_int),
            ("明確需求人數", "explicit_need", to_int),
            ("不限職缺數", "unlimited_job_count", to_int),
            ("未標示職缺數", "unspecified_job_count", to_int),
            ("總職缺數", "total_job_count", to_int),
            ("徵人需求度", "demand_ratio", to_float),
        ]
        for csv_field, db_field, converter in comparisons:
            csv_value = converter(csv_row.get(csv_field, ""))
            db_value = converter(db_row.get(db_field, ""))
            if isinstance(csv_value, float):
                mismatch = abs(csv_value - db_value) > 0.01
            else:
                mismatch = csv_value != db_value
            if mismatch:
                findings.append(
                    Finding(
                        "db_csv_value_mismatch",
                        f"{csv_field} CSV={csv_value} DB={db_value}。",
                        str(db_path),
                        code,
                        "確認 CSV 與 DB 是否來自同一輪輸出。",
                    )
                )

    job_count_by_code: Counter[str] = Counter(str(row.get("stock_code", "")) for row in job_rows)
    for code, csv_row in csv_by_code.items():
        expected_jobs = to_int(csv_row.get("總職缺數"))
        actual_jobs = job_count_by_code.get(code, 0)
        if expected_jobs != actual_jobs:
            findings.append(
                Finding(
                    "job_detail_coverage_mismatch",
                    f"CSV 總職缺數 {expected_jobs} 與 hiring_demand_jobs 明細數 {actual_jobs} 不一致。",
                    str(db_path),
                    code,
                    "確認 save_jobs_to_database 或 job aggregation 後重跑。",
                )
            )
    return findings


def validate_manifest(manifest: dict[str, Any], manifest_path: Path, require_deploy_mode: bool) -> list[Finding]:
    findings: list[Finding] = []
    required_fields = ["run_id", "run_mode", "status", "fetch_date", "csv_path", "db_path", "api_source_summary"]
    for field in required_fields:
        if not manifest.get(field):
            findings.append(
                Finding(
                    "manifest_required_field_missing",
                    f"manifest 缺必要欄位: {field}",
                    str(manifest_path),
                    field,
                    "修正 fetch_hiring_demand.py manifest 寫入邏輯後重跑。",
                )
            )
    run_mode = str(manifest.get("run_mode", ""))
    if run_mode not in VALID_RUN_MODES:
        findings.append(
            Finding(
                "invalid_run_mode",
                f"run_mode 必須是 {sorted(VALID_RUN_MODES)}，目前是 {run_mode}。",
                str(manifest_path),
                "run_mode",
                "將 run_mode 修正為 scrape-only / write-db / deploy。",
            )
        )
    if require_deploy_mode and run_mode != "deploy":
        findings.append(
            Finding(
                "deploy_mode_not_explicit",
                "要求部署時，manifest.run_mode 必須明確為 deploy。",
                str(manifest_path),
                "run_mode",
                "以 HIRING_DEMAND_RUN_MODE=deploy 重新執行，或不要啟動 deploy。",
            )
        )
    if manifest.get("status") != "success":
        findings.append(
            Finding(
                "manifest_status_not_success",
                f"manifest.status 非 success: {manifest.get('status')}",
                str(manifest_path),
                "status",
                "先完成成功 run，再執行 checker。",
            )
        )
    stock_file = manifest.get("input_stock_codes_file")
    if stock_file and not Path(stock_file).exists():
        findings.append(
            Finding(
                "missing_stock_codes_file",
                "manifest 指向的股票代碼來源檔不存在。",
                str(manifest_path),
                "input_stock_codes_file",
                "確認 stock_codes_dir 與 latest stock code CSV。",
            )
        )
    return findings


def build_receipt(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    csv_path: Path,
    db_path: Path,
    csv_rows: list[dict[str, str]],
    db_rows: list[dict[str, Any]],
    job_rows: list[dict[str, Any]],
    blockers: list[Finding],
    warnings: list[Finding],
    output_dir: Path,
) -> dict[str, Any]:
    blocker_counts = Counter(item.finding_type for item in blockers)
    warning_counts = Counter(item.finding_type for item in warnings)
    gate_result = "PASS" if not blockers else "FAIL"
    run_mode = manifest.get("run_mode", "")
    db_check_status = "skipped_scrape_only" if run_mode == "scrape-only" else "checked"
    return {
        "receipt_type": "hiring_demand_run_check",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_path": str(manifest_path),
        "run_id": manifest.get("run_id", ""),
        "run_mode": run_mode,
        "fetch_date": manifest.get("fetch_date", ""),
        "gate_result": gate_result,
        "closeout_allowed": gate_result == "PASS",
        "deploy_allowed": gate_result == "PASS" and manifest.get("run_mode") == "deploy",
        "csv_path": str(csv_path),
        "db_path": str(db_path),
        "db_check_status": db_check_status,
        "csv_row_count": len(csv_rows),
        "db_hiring_demand_count": len(db_rows),
        "db_hiring_demand_jobs_count": len(job_rows),
        "typed_blocker_count": len(blockers),
        "typed_blocker_counts": dict(blocker_counts),
        "warning_count": len(warnings),
        "warning_counts": dict(warning_counts),
        "api_source_summary": manifest.get("api_source_summary", {}),
        "outputs": {
            "receipt_json": str(output_dir / "hiring_run_check_receipt.json"),
            "receipt_md": str(output_dir / "hiring_run_check_receipt.md"),
            "typed_blockers_csv": str(output_dir / "typed_blockers.csv"),
            "warnings_csv": str(output_dir / "warnings.csv"),
        },
    }


def write_receipt_md(path: Path, receipt: dict[str, Any], blockers: list[Finding], warnings: list[Finding]) -> None:
    if receipt["gate_result"] == "PASS":
        if receipt["run_mode"] == "scrape-only":
            plain = "可以收口：CSV 與 manifest 已通過；DB 檢查因 scrape-only 模式略過，不能部署。"
        else:
            plain = "可以收口：CSV、DB 彙總與職缺明細已對齊。"
    else:
        plain = "不能收口：CSV、DB、manifest 或部署邊界仍有 blocker。"
    lines = [
        "# 徵人需求度 Run Check Receipt",
        "",
        "## 白話結論",
        "",
        plain,
        "",
        "## 工程化佐證",
        "",
        f"- run_id: `{receipt['run_id']}`",
        f"- run_mode: `{receipt['run_mode']}`",
        f"- fetch_date: `{receipt['fetch_date']}`",
        f"- gate_result: `{receipt['gate_result']}`",
        f"- closeout_allowed: `{receipt['closeout_allowed']}`",
        f"- deploy_allowed: `{receipt['deploy_allowed']}`",
        f"- db_check_status: `{receipt['db_check_status']}`",
        f"- csv_row_count: `{receipt['csv_row_count']}`",
        f"- db_hiring_demand_count: `{receipt['db_hiring_demand_count']}`",
        f"- db_hiring_demand_jobs_count: `{receipt['db_hiring_demand_jobs_count']}`",
        f"- typed_blocker_count: `{receipt['typed_blocker_count']}`",
        f"- warning_count: `{receipt['warning_count']}`",
        "",
        "## Typed Blockers",
        "",
    ]
    if blockers:
        for blocker in blockers[:50]:
            lines.append(f"- `{blocker.finding_type}` {blocker.affected_key}: {blocker.plain_description}")
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    if warnings:
        for warning in warnings[:50]:
            lines.append(f"- `{warning.finding_type}` {warning.affected_key}: {warning.plain_description}")
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest)
    blockers: list[Finding] = []
    warnings: list[Finding] = []

    if not manifest_path.exists():
        manifest: dict[str, Any] = {}
        blockers.append(
            Finding(
                "missing_manifest",
                "找不到 hiring_run_manifest.json。",
                str(manifest_path),
                "manifest",
                "先完成 fetch_hiring_demand.py run，或指定正確 manifest。",
            )
        )
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        blockers.extend(validate_manifest(manifest, manifest_path, args.require_deploy_mode))

    csv_path = Path(manifest.get("csv_path", ""))
    db_path = Path(manifest.get("db_path", ""))
    fetch_date = str(manifest.get("fetch_date", ""))
    csv_header: list[str] | None = None
    csv_rows: list[dict[str, str]] = []
    db_rows: list[dict[str, Any]] = []
    job_rows: list[dict[str, Any]] = []

    if csv_path and csv_path.exists():
        csv_header, csv_rows = read_csv_rows(csv_path)
        if csv_header != EXPECTED_HEADER:
            blockers.append(
                Finding(
                    "csv_header_mismatch",
                    f"CSV header 不符: {csv_header}",
                    str(csv_path),
                    "header",
                    "確認輸出 schema 後重跑。",
                )
            )
        if not csv_rows:
            blockers.append(
                Finding(
                    "zero_csv_rows",
                    "CSV 沒有任何公司資料，不能判定為成功。",
                    str(csv_path),
                    "row_count",
                    "確認 104 搜尋 / 公司匹配是否成功後重跑。",
                )
            )
        blockers.extend(validate_special_values(csv_rows, csv_path))
        for row in csv_rows:
            if to_int(row.get("員工人數")) <= 0 and to_int(row.get("總職缺數")) > 0:
                warnings.append(
                    Finding(
                        "employee_count_unresolved",
                        "公司有職缺但員工人數未取得，徵人需求度可能只能保守顯示。",
                        str(csv_path),
                        row.get("股票代碼", ""),
                        "後續可補官方員工人數來源或人工覆核。",
                    )
                )
    else:
        blockers.append(
            Finding(
                "missing_csv",
                "manifest 指向的 CSV 不存在。",
                str(csv_path),
                "csv_path",
                "確認 output_dir 或重新執行 scrape。",
            )
        )

    run_mode = str(manifest.get("run_mode", ""))
    if run_mode == "scrape-only":
        pass
    elif db_path and fetch_date:
        db_rows, job_rows, db_findings = load_db_rows(db_path, fetch_date)
        blockers.extend(db_findings)
        if not db_findings:
            blockers.extend(validate_csv_db_alignment(csv_rows, db_rows, job_rows, csv_path, db_path))
    else:
        blockers.append(
            Finding(
                "missing_db_context",
                "manifest 缺 db_path 或 fetch_date，無法驗 DB。",
                str(manifest_path),
                "db_path/fetch_date",
                "修正 manifest 後重跑 checker。",
            )
        )

    receipt = build_receipt(
        manifest=manifest,
        manifest_path=manifest_path,
        csv_path=csv_path,
        db_path=db_path,
        csv_rows=csv_rows,
        db_rows=db_rows,
        job_rows=job_rows,
        blockers=blockers,
        warnings=warnings,
        output_dir=output_dir,
    )
    (output_dir / "hiring_run_check_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_receipt_md(output_dir / "hiring_run_check_receipt.md", receipt, blockers, warnings)
    write_csv(
        output_dir / "typed_blockers.csv",
        [asdict(item) for item in blockers],
        ["finding_type", "plain_description", "affected_file", "affected_key", "required_fix"],
    )
    write_csv(
        output_dir / "warnings.csv",
        [asdict(item) for item in warnings],
        ["finding_type", "plain_description", "affected_file", "affected_key", "required_fix"],
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["gate_result"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check hiring-demand CSV/DB outputs before closeout or deploy.")
    parser.add_argument("--manifest", required=True, help="Path to hiring_run_manifest.json")
    parser.add_argument("--output-dir", required=True, help="Directory for checker receipt and blockers")
    parser.add_argument(
        "--require-deploy-mode",
        action="store_true",
        help="Fail unless manifest.run_mode is deploy. Wrapper uses this before git push.",
    )
    return parser


def main() -> int:
    return check_run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
