#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only checker for unlimited-hiring revenue report artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from generate_unlimited_hiring_revenue_report import (
    REPORT_FIELDS,
    REVENUE_SNAPSHOT_FIELDS,
    build_report_rows,
    load_all_revenue_summary_rows,
    load_revenue_summary,
    normalize_revenue_snapshot_row,
    read_hiring_rows,
    select_unlimited_rows,
)


@dataclass
class Finding:
    finding_type: str
    plain_description: str
    affected_file: str
    affected_key: str
    required_fix: str


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_csv_rows_and_fieldnames(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def required_path(manifest: dict[str, Any], key: str, findings: list[Finding]) -> Path:
    output_keys = {
        "html_report",
        "new_unlimited_csv",
        "current_month_revenue_increase_csv",
        "revenue_turnaround_csv",
        "revenue_growth_csv",
        "anomaly_summary_json",
        "revenue_snapshot_csv",
        "revenue_snapshot_manifest",
    }
    raw_path = manifest.get("outputs", {}).get(key) if key in output_keys else manifest.get(key, "")
    path = Path(str(raw_path))
    if not path.exists():
        findings.append(
            Finding(
                "missing_report_artifact",
                "報表 manifest 指向的必要 artifact 不存在。",
                str(path),
                key,
                "重新產生 unlimited hiring revenue report 後重跑 checker。",
            )
        )
    return path


def validate_revenue_snapshot(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    db_path: Path,
    snapshot_csv: Path,
    snapshot_manifest_path: Path,
    findings: list[Finding],
) -> int:
    db_rows = [normalize_revenue_snapshot_row(row) for row in load_all_revenue_summary_rows(db_path)]
    snapshot_rows, snapshot_fields = read_csv_rows_and_fieldnames(snapshot_csv)
    snapshot_payload = read_json(snapshot_manifest_path)

    if snapshot_fields != REVENUE_SNAPSHOT_FIELDS:
        findings.append(
            Finding(
                "revenue_snapshot_schema_mismatch",
                "月營收快照 CSV 欄位與 monthly_revenue_summary contract 不一致。",
                str(snapshot_csv),
                "csv_header",
                "重新產生 monthly_revenue_summary 快照 CSV 後重跑 checker。",
            )
        )
    if snapshot_payload.get("artifact_type") != "monthly_revenue_snapshot":
        findings.append(
            Finding(
                "invalid_revenue_snapshot_manifest_schema",
                "月營收快照 manifest 缺少正確 artifact_type。",
                str(snapshot_manifest_path),
                str(snapshot_payload.get("artifact_type", "")),
                "重新產生 monthly_revenue_snapshot_manifest 後重跑 checker。",
            )
        )

    expected_manifest_values = {
        "source_db_path": str(db_path),
        "source_table": "monthly_revenue_summary",
        "snapshot_csv_path": str(snapshot_csv),
        "row_count": len(db_rows),
    }
    for key, expected in expected_manifest_values.items():
        if snapshot_payload.get(key) != expected:
            findings.append(
                Finding(
                    "revenue_snapshot_manifest_mismatch",
                    "月營收快照 manifest 與本輪 DB / CSV artifact 不一致。",
                    str(snapshot_manifest_path),
                    key,
                    "重新產生報表與月營收快照後重跑 checker。",
                )
            )

    manifest_snapshot = manifest.get("revenue_snapshot", {})
    if manifest_snapshot.get("snapshot_csv_path") != str(snapshot_csv) or manifest_snapshot.get("snapshot_manifest_path") != str(snapshot_manifest_path):
        findings.append(
            Finding(
                "revenue_snapshot_manifest_mismatch",
                "報表 manifest 未正確指向月營收快照 CSV / manifest。",
                str(manifest_path),
                "revenue_snapshot",
                "重新產生 report manifest 後重跑 checker。",
            )
        )

    if len(snapshot_rows) != len(db_rows):
        findings.append(
            Finding(
                "revenue_snapshot_row_count_mismatch",
                "月營收快照 CSV row count 與 DB monthly_revenue_summary 不一致。",
                str(snapshot_csv),
                "row_count",
                "重新產生 monthly_revenue_summary 快照 CSV 後重跑 checker。",
            )
        )
        return len(db_rows)

    db_by_code = {row["stock_code"]: row for row in db_rows}
    csv_by_code = {row.get("stock_code", ""): {field: row.get(field, "") for field in REVENUE_SNAPSHOT_FIELDS} for row in snapshot_rows}
    if set(csv_by_code) != set(db_by_code):
        findings.append(
            Finding(
                "revenue_snapshot_db_mismatch",
                "月營收快照 CSV 的 stock_code 集合與 DB 不一致。",
                str(snapshot_csv),
                "stock_code",
                "重新產生 monthly_revenue_summary 快照 CSV 後重跑 checker。",
            )
        )
        return len(db_rows)

    for code, expected_row in db_by_code.items():
        if csv_by_code[code] != expected_row:
            findings.append(
                Finding(
                    "revenue_snapshot_db_mismatch",
                    "月營收快照 CSV 的 MoM / YoY / 月份欄位與 DB 不一致。",
                    str(snapshot_csv),
                    code,
                    "重新產生 monthly_revenue_summary 快照 CSV 後重跑 checker。",
                )
            )
            break
    return len(db_rows)


def default_media_receipt_path(manifest: dict[str, Any]) -> Path:
    output_dir = Path(str(manifest.get("outputs", {}).get("output_dir", "")))
    report_key = str(manifest.get("report_yyyymmdd", ""))
    return output_dir / f"unlimited_hiring_revenue_media_receipt_{report_key}.json"


def validate_media_receipt(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    media_receipt_path: Path,
    findings: list[Finding],
) -> dict[str, Any]:
    media_summary = {
        "required": True,
        "media_receipt_path": str(media_receipt_path),
        "media_receipt_exists": media_receipt_path.exists(),
        "png_path": "",
        "png_exists": False,
        "pdf_path": "",
        "pdf_exists": False,
        "png_scale": None,
        "png_dpi": None,
    }
    if not media_receipt_path.exists():
        findings.append(
            Finding(
                "missing_media_receipt",
                "已要求 PNG/PDF media gate，但找不到 media render receipt。",
                str(media_receipt_path),
                "media_receipt",
                "先執行 render_unlimited_hiring_revenue_media.py，再以 --require-media 重跑 checker。",
            )
        )
        return media_summary

    media_receipt = read_json(media_receipt_path)
    png_path = Path(str(media_receipt.get("png_path", "")))
    pdf_path = Path(str(media_receipt.get("pdf_path", "")))
    media_summary.update(
        {
            "png_path": str(png_path),
            "png_exists": png_path.exists(),
            "pdf_path": str(pdf_path),
            "pdf_exists": pdf_path.exists(),
            "png_scale": media_receipt.get("png_scale"),
            "png_dpi": media_receipt.get("png_dpi"),
            "png_pixel_width": media_receipt.get("png_pixel_width"),
            "png_pixel_height": media_receipt.get("png_pixel_height"),
            "png_font_profile": media_receipt.get("png_font_profile"),
        }
    )

    expected_pairs = {
        "receipt_type": "unlimited_hiring_revenue_media_render",
        "manifest_path": str(manifest_path),
        "report_date": manifest.get("report_date", ""),
        "anomaly_summary_path": manifest.get("outputs", {}).get("anomaly_summary_json", ""),
        "png_mode": "anomaly_detection_summary",
        "revenue_window_months": 6,
        "png_chart_bar_count": 6,
        "pdf_chart_bar_count": 6,
    }
    for key, expected in expected_pairs.items():
        if media_receipt.get(key) != expected:
            findings.append(
                Finding(
                    "media_receipt_manifest_mismatch",
                    "media receipt 與本輪 report manifest 或近六月圖表 contract 不一致。",
                    str(media_receipt_path),
                    key,
                    "重新以本輪 manifest render PNG/PDF，並重跑 --require-media checker。",
                )
            )

    if not png_path.exists():
        findings.append(
            Finding(
                "missing_media_artifact",
                "media receipt 指向的 PNG 不存在。",
                str(png_path),
                "png_path",
                "重新 render PNG 後重跑 media checker。",
            )
        )
    if not pdf_path.exists():
        findings.append(
            Finding(
                "missing_media_artifact",
                "media receipt 指向的 PDF 不存在。",
                str(pdf_path),
                "pdf_path",
                "重新 render PDF 後重跑 media checker。",
            )
        )
    return media_summary


def validate_report(
    manifest_path: Path,
    *,
    require_media: bool = False,
    media_receipt_path: Path | None = None,
) -> tuple[dict[str, Any], list[Finding], dict[str, int], dict[str, Any]]:
    findings: list[Finding] = []
    media_summary = {"required": require_media, "media_receipt_exists": False}
    if not manifest_path.exists():
        receipt_counts = {
            "latest_unlimited_count": 0,
            "previous_unlimited_count": 0,
            "new_unlimited_count": 0,
            "current_month_revenue_increase_count": 0,
            "revenue_turnaround_count": 0,
            "revenue_growth_count": 0,
            "revenue_snapshot_row_count": 0,
        }
        return {}, [
            Finding(
                "missing_manifest",
                "找不到 unlimited hiring revenue report manifest。",
                str(manifest_path),
                "manifest",
                "先執行 generate_unlimited_hiring_revenue_report.py。",
            )
        ], receipt_counts, media_summary

    manifest = read_json(manifest_path)
    if manifest.get("unlimited_filter_rule") != "unlimited_job_count_gt_zero":
        findings.append(
            Finding(
                "invalid_unlimited_filter_rule",
                "人數不限公司必須以 不限職缺數 > 0 判斷。",
                str(manifest_path),
                str(manifest.get("unlimited_filter_rule", "")),
                "修正報表產生器的不限公司定義後重跑。",
            )
        )

    latest_csv = required_path(manifest, "latest_csv", findings)
    previous_csv = required_path(manifest, "previous_csv", findings)
    db_path = required_path(manifest, "db_path", findings)
    html_report = required_path(manifest, "html_report", findings)
    new_unlimited_csv = required_path(manifest, "new_unlimited_csv", findings)
    current_month_revenue_increase_csv = required_path(manifest, "current_month_revenue_increase_csv", findings)
    revenue_turnaround_csv = required_path(manifest, "revenue_turnaround_csv", findings)
    revenue_growth_csv = required_path(manifest, "revenue_growth_csv", findings)
    anomaly_summary_json = required_path(manifest, "anomaly_summary_json", findings)
    revenue_snapshot_csv = required_path(manifest, "revenue_snapshot_csv", findings)
    revenue_snapshot_manifest = required_path(manifest, "revenue_snapshot_manifest", findings)

    if findings:
        return manifest, findings, {
            "latest_unlimited_count": 0,
            "previous_unlimited_count": 0,
            "new_unlimited_count": 0,
            "current_month_revenue_increase_count": 0,
            "revenue_turnaround_count": 0,
            "revenue_growth_count": 0,
            "revenue_snapshot_row_count": 0,
        }, media_summary

    latest_rows = read_hiring_rows(latest_csv)
    previous_rows = read_hiring_rows(previous_csv)
    latest_unlimited = select_unlimited_rows(latest_rows)
    previous_unlimited = select_unlimited_rows(previous_rows)
    stock_codes = sorted({row.get("股票代碼", "") for row in latest_unlimited if row.get("股票代碼", "")})
    revenue_by_code = load_revenue_summary(db_path, stock_codes)
    report_rows, expected_new_rows, expected_current_month_rows, expected_turnaround_rows, expected_growth_rows, missing_revenue = build_report_rows(latest_rows, previous_rows, revenue_by_code)
    revenue_snapshot_row_count = validate_revenue_snapshot(
        manifest=manifest,
        manifest_path=manifest_path,
        db_path=db_path,
        snapshot_csv=revenue_snapshot_csv,
        snapshot_manifest_path=revenue_snapshot_manifest,
        findings=findings,
    )

    expected_counts = {
        "latest_unlimited_count": len(report_rows),
        "previous_unlimited_count": len(previous_unlimited),
        "new_unlimited_count": len(expected_new_rows),
        "current_month_revenue_increase_count": len(expected_current_month_rows),
        "revenue_turnaround_count": len(expected_turnaround_rows),
        "revenue_growth_count": len(expected_growth_rows),
        "revenue_snapshot_row_count": revenue_snapshot_row_count,
    }
    for key, expected in expected_counts.items():
        if int(manifest.get(key, -1)) != expected:
            findings.append(
                Finding(
                    "manifest_count_mismatch",
                    f"{key} 應為 {expected}，但 manifest 記錄為 {manifest.get(key)}。",
                    str(manifest_path),
                    key,
                    "重新產生 report manifest 後重跑 checker。",
                )
            )

    for code in missing_revenue:
        findings.append(
            Finding(
                "missing_revenue_summary",
                "人數不限公司缺少 monthly_revenue_summary 近六月營收資料。",
                str(db_path),
                code,
                "先補齊或更新 monthly_revenue_summary，再重新產生報表。",
            )
        )

    actual_new_rows = read_csv_rows(new_unlimited_csv)
    actual_new_codes = {row.get("股票代碼", "") for row in actual_new_rows}
    expected_new_codes = {row.get("股票代碼", "") for row in expected_new_rows}
    if actual_new_codes != expected_new_codes:
        findings.append(
            Finding(
                "new_unlimited_companies_mismatch",
                "今日新增公司 CSV 與最新/前一日 unlimited set 比對結果不一致。",
                str(new_unlimited_csv),
                "股票代碼",
                "重新產生 new_unlimited_companies CSV 後重跑 checker。",
            )
        )
    if any(row.get("今日新增公司") != "YES" for row in actual_new_rows):
        findings.append(
            Finding(
                "missing_today_new_marker",
                "今日新增公司 CSV 必須逐列標示 今日新增公司=YES。",
                str(new_unlimited_csv),
                "今日新增公司",
                "修正 CSV 輸出欄位後重跑 checker。",
            )
        )

    actual_current_month_rows = read_csv_rows(current_month_revenue_increase_csv)
    actual_current_month_codes = {row.get("股票代碼", "") for row in actual_current_month_rows}
    expected_current_month_codes = {row.get("股票代碼", "") for row in expected_current_month_rows}
    if actual_current_month_codes != expected_current_month_codes:
        findings.append(
            Finding(
                "current_month_revenue_increase_companies_mismatch",
                    "營收雙指標改善觀察 CSV 與 checker 重算結果不一致。",
                str(current_month_revenue_increase_csv),
                "股票代碼",
                "重新產生 current_month_revenue_increase_companies CSV 後重跑 checker。",
            )
        )

    actual_turnaround_rows = read_csv_rows(revenue_turnaround_csv)
    actual_turnaround_codes = {row.get("股票代碼", "") for row in actual_turnaround_rows}
    expected_turnaround_codes = {row.get("股票代碼", "") for row in expected_turnaround_rows}
    if actual_turnaround_codes != expected_turnaround_codes:
        findings.append(
            Finding(
                "revenue_turnaround_companies_mismatch",
                "營收轉正觀察 CSV 與 checker 重算結果不一致。",
                str(revenue_turnaround_csv),
                "股票代碼",
                "重新產生 revenue_turnaround_companies CSV 後重跑 checker。",
            )
        )

    actual_growth_rows = read_csv_rows(revenue_growth_csv)
    actual_growth_codes = {row.get("股票代碼", "") for row in actual_growth_rows}
    expected_growth_codes = {row.get("股票代碼", "") for row in expected_growth_rows}
    if actual_growth_codes != expected_growth_codes:
        findings.append(
            Finding(
                "revenue_growth_companies_mismatch",
                "營收強勢延續公司 CSV 與 checker 重算結果不一致。",
                str(revenue_growth_csv),
                "股票代碼",
                "重新產生 revenue_growth_companies CSV 後重跑 checker。",
            )
        )

    anomaly_summary = read_json(anomaly_summary_json)
    if anomaly_summary.get("summary_type") != "hiring_demand_anomaly_summary":
        findings.append(
            Finding(
                "invalid_anomaly_summary_schema",
                "anomaly_summary.json 缺少正確 summary_type。",
                str(anomaly_summary_json),
                str(anomaly_summary.get("summary_type", "")),
                "重新產生 anomaly_summary.json 後重跑 checker。",
            )
        )
    if anomaly_summary.get("alert_policy", {}).get("revenue_change_direction") != "increase_only":
        findings.append(
            Finding(
                "invalid_anomaly_revenue_policy",
                "營收改變告警目前只允許 increase_only。",
                str(anomaly_summary_json),
                "alert_policy.revenue_change_direction",
                "修正 anomaly detector 的營收告警方向後重跑 checker。",
            )
        )
    expected_summary_counts = {
        "today_new_unlimited": len(expected_new_rows),
        "current_month_revenue_increase": len(expected_current_month_rows),
        "revenue_turnaround": len(expected_turnaround_rows),
        "three_month_revenue_growth": len(expected_growth_rows),
    }
    mismatch_count = 0
    for event_key, expected in expected_summary_counts.items():
        actual = int(anomaly_summary.get("events", {}).get(event_key, {}).get("count", -1))
        if actual != expected:
            mismatch_count += 1
            findings.append(
                Finding(
                    "anomaly_summary_count_mismatch",
                    f"{event_key} 應為 {expected}，但 anomaly_summary 記錄為 {actual}。",
                    str(anomaly_summary_json),
                    event_key,
                    "重新產生 anomaly_summary.json 後重跑 checker。",
                )
            )
    expected_alert_required = any(value > 0 for value in expected_summary_counts.values())
    if bool(anomaly_summary.get("alert_required")) != expected_alert_required:
        findings.append(
            Finding(
                "anomaly_summary_alert_mismatch",
                "anomaly_summary alert_required 與三類事件 count 不一致。",
                str(anomaly_summary_json),
                "alert_required",
                "重新產生 anomaly_summary.json 後重跑 checker。",
            )
        )

    html_text = html_report.read_text(encoding="utf-8")
    if manifest.get("report_date", "") not in html_text or "人數不限徵人需求度" not in html_text:
        findings.append(
            Finding(
                "html_report_content_mismatch",
                "HTML 報表缺少報表日期或人數不限報表標題。",
                str(html_report),
                "html",
                "重新產生 HTML 報表後重跑 checker。",
            )
        )
    for required_text in ["今日新增不限徵才", "營收雙指標改善觀察", "營收轉正觀察", "營收強勢延續公司", "revenue-bars"]:
        if required_text not in html_text:
            findings.append(
                Finding(
                    "html_report_content_mismatch",
                    "HTML 報表缺少必要章節或營收長條圖。",
                    str(html_report),
                    required_text,
                    "重新產生 HTML 報表後重跑 checker。",
                )
            )
    for forbidden_text in ["昨日人數不限公司", "全部人數不限公司"]:
        if forbidden_text in html_text:
            findings.append(
                Finding(
                    "html_report_content_too_broad",
                    "HTML 報表仍包含已移除的大量資料章節。",
                    str(html_report),
                    forbidden_text,
                    "移除昨日全表或全部不限公司表，只保留三個指定表格。",
                )
            )

    if require_media:
        media_summary = validate_media_receipt(
            manifest=manifest,
            manifest_path=manifest_path,
            media_receipt_path=media_receipt_path or default_media_receipt_path(manifest),
            findings=findings,
        )

    return manifest, findings, expected_counts, media_summary


def build_receipt(
    manifest_path: Path,
    output_dir: Path,
    manifest: dict[str, Any],
    blockers: list[Finding],
    counts: dict[str, int],
    media: dict[str, Any],
) -> dict[str, Any]:
    blocker_counts = Counter(item.finding_type for item in blockers)
    gate_result = "PASS" if not blockers else "FAIL"
    return {
        "receipt_type": "unlimited_hiring_revenue_report_check",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_path": str(manifest_path),
        "report_date": manifest.get("report_date", ""),
        "gate_result": gate_result,
        "closeout_allowed": gate_result == "PASS",
        "telegram_sent": False,
        "telegram_send_authorized": False,
        "unlimited_filter_rule": manifest.get("unlimited_filter_rule", ""),
        "latest_unlimited_count": counts.get("latest_unlimited_count", 0),
        "previous_unlimited_count": counts.get("previous_unlimited_count", 0),
        "new_unlimited_count": counts.get("new_unlimited_count", 0),
        "current_month_revenue_increase_count": counts.get("current_month_revenue_increase_count", 0),
        "revenue_turnaround_count": counts.get("revenue_turnaround_count", 0),
        "revenue_growth_count": counts.get("revenue_growth_count", 0),
        "revenue_snapshot_row_count": counts.get("revenue_snapshot_row_count", 0),
        "media": media,
        "typed_blocker_count": len(blockers),
        "typed_blocker_counts": dict(blocker_counts),
        "outputs": {
            "receipt_json": str(output_dir / "unlimited_hiring_revenue_report_check_receipt.json"),
            "receipt_md": str(output_dir / "unlimited_hiring_revenue_report_check_receipt.md"),
            "typed_blockers_csv": str(output_dir / "typed_blockers.csv"),
        },
    }


def write_receipt_md(path: Path, receipt: dict[str, Any], blockers: list[Finding]) -> None:
    plain = (
        "可以收口：今日新增、營收改善、營收轉正與強勢延續名單都和來源資料一致。"
        if receipt["gate_result"] == "PASS"
        else "不能收口：報表仍有缺營收、錯新增名單、錯營收篩選或 artifact 缺漏。"
    )
    lines = [
        "# 人數不限徵人需求度與營收報表 Checker Receipt",
        "",
        "## 白話結論",
        "",
        plain,
        "",
        "## 工程化佐證",
        "",
        f"- gate_result: `{receipt['gate_result']}`",
        f"- report_date: `{receipt['report_date']}`",
        f"- unlimited_filter_rule: `{receipt['unlimited_filter_rule']}`",
        f"- latest_unlimited_count: `{receipt['latest_unlimited_count']}`",
        f"- previous_unlimited_count: `{receipt['previous_unlimited_count']}`",
        f"- new_unlimited_count: `{receipt['new_unlimited_count']}`",
        f"- current_month_revenue_increase_count: `{receipt['current_month_revenue_increase_count']}`",
        f"- revenue_turnaround_count: `{receipt['revenue_turnaround_count']}`",
        f"- revenue_growth_count: `{receipt['revenue_growth_count']}`",
        f"- revenue_snapshot_row_count: `{receipt['revenue_snapshot_row_count']}`",
        f"- telegram_sent: `{receipt['telegram_sent']}`",
        f"- typed_blocker_count: `{receipt['typed_blocker_count']}`",
        "",
        "## Typed Blockers",
        "",
    ]
    if blockers:
        lines.extend(f"- `{item.finding_type}` {item.affected_key}: {item.plain_description}" for item in blockers)
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_report(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    media_receipt_path = Path(args.media_receipt) if args.media_receipt else None
    manifest, blockers, counts, media = validate_report(
        manifest_path,
        require_media=args.require_media,
        media_receipt_path=media_receipt_path,
    )
    receipt = build_receipt(manifest_path, output_dir, manifest, blockers, counts, media)
    (output_dir / "unlimited_hiring_revenue_report_check_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_receipt_md(output_dir / "unlimited_hiring_revenue_report_check_receipt.md", receipt, blockers)
    write_csv(
        output_dir / "typed_blockers.csv",
        [asdict(item) for item in blockers],
        ["finding_type", "plain_description", "affected_file", "affected_key", "required_fix"],
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["gate_result"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check unlimited-hiring revenue report artifacts.")
    parser.add_argument("--manifest", required=True, help="Path to unlimited_hiring_revenue_report_manifest_YYYYMMDD.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for checker receipt.")
    parser.add_argument("--require-media", action="store_true", help="Require PNG/PDF media receipt and artifact sync.")
    parser.add_argument("--media-receipt", default="", help="Optional explicit unlimited_hiring_revenue_media_receipt_YYYYMMDD.json path.")
    return parser


def main() -> int:
    return check_report(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
