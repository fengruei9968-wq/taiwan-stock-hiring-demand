#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the unlimited-hiring revenue report.

This is a local artifact generator only. It does not send Telegram messages,
render PDF/image files, deploy, commit, or push.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from hiring_anomaly_detector import build_anomaly_summary


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("HIRING_PROJECT_ROOT", BASE_DIR.parent)).resolve()
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "stage3_web" / "investment.db"))
REVENUE_MONTH_COUNT = 6


def revenue_fields() -> list[str]:
    fields: list[str] = []
    for index in range(1, REVENUE_MONTH_COUNT + 1):
        fields.extend([f"m{index}_label", f"m{index}_mom", f"m{index}_yoy"])
    return fields


REVENUE_FIELDS = revenue_fields()
REVENUE_METRIC_FIELDS = [field for field in REVENUE_FIELDS if field.endswith(("_mom", "_yoy"))]
REVENUE_SNAPSHOT_FIELDS = ["stock_code", *REVENUE_FIELDS, "updated_at"]
REPORT_FIELDS = [
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
    *REVENUE_FIELDS,
    "今日新增公司",
]


def to_int(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def to_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def month_sort_key(label: Any) -> tuple[int, int]:
    try:
        year, month = str(label).split("/", 1)
        return int(year), int(month)
    except (TypeError, ValueError):
        return 0, 0


def normalize_revenue_window(row: dict[str, Any]) -> dict[str, Any]:
    month_map: dict[str, dict[str, Any]] = {}
    for index in range(1, REVENUE_MONTH_COUNT + 1):
        label = row.get(f"m{index}_label")
        if not label:
            continue
        month_map[str(label)] = {
            "mom": row.get(f"m{index}_mom"),
            "yoy": row.get(f"m{index}_yoy"),
        }

    items = sorted(month_map.items(), key=lambda item: month_sort_key(item[0]))
    items = items[-REVENUE_MONTH_COUNT:]
    padding = [(None, {"mom": None, "yoy": None})] * (REVENUE_MONTH_COUNT - len(items))
    items = padding + items

    normalized: dict[str, Any] = {
        "stock_code": row.get("stock_code", ""),
        "updated_at": row.get("updated_at", ""),
    }
    for index, (label, values) in enumerate(items, start=1):
        normalized[f"m{index}_label"] = label
        normalized[f"m{index}_mom"] = values.get("mom")
        normalized[f"m{index}_yoy"] = values.get("yoy")
    return normalized


def revenue_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index in range(1, REVENUE_MONTH_COUNT + 1):
        label = row.get(f"m{index}_label")
        if not label:
            continue
        entries.append({
            "label": str(label),
            "mom": to_float_or_none(row.get(f"m{index}_mom")),
            "yoy": to_float_or_none(row.get(f"m{index}_yoy")),
        })
    return sorted(entries, key=lambda item: month_sort_key(item["label"]))


def monthly_revenue_columns(conn: sqlite3.Connection) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute("PRAGMA table_info(monthly_revenue_summary)")}
    except sqlite3.Error:
        return set()


def parse_csv_date(path: Path) -> tuple[str, str]:
    match = re.search(r"(\d{8})_hiring_demand\.csv$", path.name)
    if not match:
        raise ValueError(f"CSV 檔名缺少 YYYYMMDD 日期註記: {path}")
    key = match.group(1)
    return key, f"{key[:4]}-{key[4:6]}-{key[6:8]}"


def find_latest_and_previous_csv(data_dir: Path) -> tuple[Path, Path]:
    dated_files: list[tuple[str, Path]] = []
    for path in data_dir.glob("*_hiring_demand.csv"):
        try:
            date_key, _ = parse_csv_date(path)
        except ValueError:
            continue
        dated_files.append((date_key, path))
    dated_files.sort()
    if len(dated_files) < 2:
        raise FileNotFoundError("至少需要最新與前一日兩個 hiring_demand CSV。")
    return dated_files[-1][1], dated_files[-2][1]


def read_hiring_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def select_unlimited_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """不限公司定義：不限職缺數大於 0，而不是只看 999.0 特殊值。"""
    return [row for row in rows if to_int(row.get("不限職缺數")) > 0]


def load_revenue_summary(db_path: Path, stock_codes: list[str]) -> dict[str, dict[str, Any]]:
    if not stock_codes:
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        columns = monthly_revenue_columns(conn)
        if "stock_code" not in columns:
            return {}
        select_fields = ["stock_code", *[field for field in REVENUE_FIELDS if field in columns]]
        if "updated_at" in columns:
            select_fields.append("updated_at")
        placeholders = ",".join("?" for _ in stock_codes)
        sql = f"""
            SELECT {", ".join(select_fields)}
            FROM monthly_revenue_summary
            WHERE stock_code IN ({placeholders})
        """
        return {
            str(row["stock_code"]): normalize_revenue_window(dict(row))
            for row in conn.execute(sql, stock_codes)
        }
    finally:
        conn.close()


def load_all_revenue_summary_rows(db_path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        columns = monthly_revenue_columns(conn)
        if "stock_code" not in columns:
            return []
        select_fields = ["stock_code", *[field for field in REVENUE_FIELDS if field in columns]]
        if "updated_at" in columns:
            select_fields.append("updated_at")
        sql = f"""
            SELECT {", ".join(select_fields)}
            FROM monthly_revenue_summary
            ORDER BY stock_code
        """
        return [normalize_revenue_window(dict(row)) for row in conn.execute(sql)]
    finally:
        conn.close()


def normalize_revenue_snapshot_row(row: dict[str, Any]) -> dict[str, str]:
    return {field: "" if row.get(field) is None else str(row.get(field, "")) for field in REVENUE_SNAPSHOT_FIELDS}


def build_revenue_snapshot_manifest(
    *,
    report_date_key: str,
    db_path: Path,
    snapshot_csv: Path,
    snapshot_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    updated_at_values = [str(row.get("updated_at", "")) for row in snapshot_rows if row.get("updated_at") not in (None, "")]
    return {
        "schema_version": "2026-05-15",
        "artifact_type": "monthly_revenue_snapshot",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_yyyymmdd": report_date_key,
        "source_db_path": str(db_path),
        "source_table": "monthly_revenue_summary",
        "snapshot_csv_path": str(snapshot_csv),
        "row_count": len(snapshot_rows),
        "updated_at_min": min(updated_at_values) if updated_at_values else "",
        "updated_at_max": max(updated_at_values) if updated_at_values else "",
        "fields": REVENUE_SNAPSHOT_FIELDS,
    }


def build_report_rows(
    latest_rows: list[dict[str, str]],
    previous_rows: list[dict[str, str]],
    revenue_by_code: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    latest_unlimited = select_unlimited_rows(latest_rows)
    previous_unlimited = select_unlimited_rows(previous_rows)
    previous_codes = {row.get("股票代碼", "") for row in previous_unlimited}
    latest_codes = {row.get("股票代碼", "") for row in latest_unlimited}
    new_codes = latest_codes - previous_codes
    missing_revenue_set: set[str] = set()

    def merge_row(row: dict[str, str], *, today_new: bool, require_revenue: bool) -> dict[str, Any]:
        code = row.get("股票代碼", "")
        revenue = revenue_by_code.get(code)
        if not revenue:
            if require_revenue:
                missing_revenue_set.add(code)
            revenue = {}
        merged = {field: row.get(field, "") for field in REPORT_FIELDS if field in row}
        for field in REVENUE_FIELDS:
            value = revenue.get(field, "")
            merged[field] = "" if value is None else value
        merged["今日新增公司"] = "YES" if today_new else ""
        return merged

    report_rows = [merge_row(row, today_new=row.get("股票代碼", "") in new_codes, require_revenue=True) for row in latest_unlimited]
    new_rows = [row for row in report_rows if row["今日新增公司"] == "YES"]
    current_month_revenue_increase_rows = [row for row in report_rows if is_current_month_revenue_increase_row(row)]
    revenue_turnaround_rows = [row for row in report_rows if is_revenue_turnaround_row(row)]
    revenue_growth_rows = [row for row in report_rows if is_revenue_growth_row(row)]
    return report_rows, new_rows, current_month_revenue_increase_rows, revenue_turnaround_rows, revenue_growth_rows, sorted(missing_revenue_set)


def is_current_month_revenue_increase_row(row: dict[str, Any]) -> bool:
    entries = revenue_entries(row)
    if len(entries) < 2:
        return False
    previous, current = entries[-2], entries[-1]
    if None in {previous["mom"], current["mom"], previous["yoy"], current["yoy"]}:
        return False
    previous_month_has_weakness = previous["mom"] <= 0 or previous["yoy"] <= 0
    return previous_month_has_weakness and current["mom"] > previous["mom"] and current["yoy"] > previous["yoy"]


def is_revenue_turnaround_row(row: dict[str, Any]) -> bool:
    if is_current_month_revenue_increase_row(row):
        return False
    entries = revenue_entries(row)
    if len(entries) < 2:
        return False
    previous, current = entries[-2], entries[-1]
    if None in {previous["yoy"], current["mom"], current["yoy"]}:
        return False
    return previous["yoy"] <= 0 and current["yoy"] > 0 and current["mom"] > 0


def is_revenue_growth_row(row: dict[str, Any]) -> bool:
    entries = revenue_entries(row)[-3:]
    if len(entries) < 3:
        return False
    if any(entry["mom"] is None or entry["yoy"] is None for entry in entries):
        return False
    return (
        entries[0]["mom"] < entries[1]["mom"] < entries[2]["mom"]
        and entries[0]["yoy"] < entries[1]["yoy"] < entries[2]["yoy"]
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def write_html_report(
    path: Path,
    *,
    report_date: str,
    previous_date: str,
    report_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    current_month_revenue_increase_rows: list[dict[str, Any]],
    revenue_turnaround_rows: list[dict[str, Any]],
    revenue_growth_rows: list[dict[str, Any]],
    missing_revenue: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = [
        ("報表日期", report_date),
        ("前一日", previous_date),
        ("今日新增公司數", len(new_rows)),
        ("營收轉正觀察", len(revenue_turnaround_rows)),
        ("營收雙指標改善觀察", len(current_month_revenue_increase_rows)),
        ("營收強勢延續公司", len(revenue_growth_rows)),
        ("營收缺漏公司數", len(missing_revenue)),
    ]

    table_headers = ["股票代碼", "公司簡稱", "市場", "不限", "明確", "總職缺", "需求度", "近六月營收 MoM", "近六月營收 YoY", "今日新增"]

    def format_ratio(value: Any) -> str:
        number = to_float_or_none(value)
        if number is None:
            return str(value or "")
        if number == 999.0:
            return "人數不限"
        if number == 998.0:
            return "未標示"
        return f"{number:.2f}%"

    def format_percent(value: Any) -> str:
        number = to_float_or_none(value)
        if number is None:
            return ""
        return f"{number:+.1f}%"

    def render_svg_chart(row: dict[str, Any], metric: str) -> str:
        values = [to_float_or_none(row.get(f"m{index}_{metric}")) for index in range(1, REVENUE_MONTH_COUNT + 1)]
        labels = [
            "" if row.get(f"m{index}_label") in (None, "") else str(row.get(f"m{index}_label"))
            for index in range(1, REVENUE_MONTH_COUNT + 1)
        ]
        numeric_values = [abs(value) for value in values if value is not None]
        max_abs = max(numeric_values + [5.0])
        width, height = 270, 82
        base_y = 42
        bar_width = 20
        gap = 16
        start_x = 16
        baseline_end = start_x + REVENUE_MONTH_COUNT * bar_width + (REVENUE_MONTH_COUNT - 1) * gap + 4
        pieces = [
            f'<svg class="revenue-bars" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(metric.upper())} bar chart">',
            f'<line x1="12" y1="42" x2="{baseline_end}" y2="42" stroke="#CBD5E1" stroke-dasharray="3 3"/>',
        ]
        for index, value in enumerate(values):
            x = start_x + index * (bar_width + gap)
            label = labels[index].split("/")[-1] + "月" if labels[index] else "-"
            if value is None:
                pieces.append(f'<rect x="{x + 10}" y="{base_y - 3}" width="4" height="6" rx="2" fill="#94A3B8"/>')
                pieces.append(f'<text x="{x + 12}" y="70" text-anchor="middle" class="chart-month">{html.escape(label)}</text>')
                continue
            bar_h = max(3, round(abs(value) / max_abs * 30))
            is_pos = value >= 0
            y = base_y - bar_h if is_pos else base_y
            color = "#EF4444" if is_pos else "#14B8A6"
            text_y = max(9, y - 3) if is_pos else min(64, y + bar_h + 10)
            sign_value = html.escape(format_percent(value))
            pieces.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" rx="4" fill="{color}"><title>{html.escape(labels[index])}: {sign_value}</title></rect>')
            pieces.append(f'<text x="{x + bar_width / 2:.1f}" y="{text_y}" text-anchor="middle" class="chart-value">{sign_value}</text>')
            pieces.append(f'<text x="{x + bar_width / 2:.1f}" y="70" text-anchor="middle" class="chart-month">{html.escape(label)}</text>')
        pieces.append("</svg>")
        return "".join(pieces)

    def render_table(rows: list[dict[str, Any]]) -> str:
        header = "".join(f"<th>{html.escape(field)}</th>" for field in table_headers)
        body = []
        for row in rows:
            cells = [
                html.escape(format_value(row.get("股票代碼", ""))),
                html.escape(format_value(row.get("公司簡稱", ""))),
                html.escape(format_value(row.get("市場類別", ""))),
                html.escape(format_value(row.get("不限職缺數", ""))),
                html.escape(format_value(row.get("明確需求人數", ""))),
                html.escape(format_value(row.get("總職缺數", ""))),
                html.escape(format_ratio(row.get("徵人需求度", ""))),
                render_svg_chart(row, "mom"),
                render_svg_chart(row, "yoy"),
                html.escape(format_value(row.get("今日新增公司", ""))),
            ]
            body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
        if not body:
            body.append(f"<tr><td colspan=\"{len(table_headers)}\">無資料</td></tr>")
        return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"

    summary_html = "".join(
        f"<div class=\"metric\"><span>{html.escape(label)}</span><strong>{html.escape(format_value(value))}</strong></div>"
        for label, value in summary
    )
    doc = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>人數不限徵人需求度與近六月營收報表 {html.escape(report_date)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", sans-serif; margin: 24px; color: #1f2933; }}
    h1, h2 {{ margin: 0 0 12px; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0 24px; }}
    .metric {{ border: 1px solid #d6dde5; border-radius: 6px; padding: 10px 12px; min-width: 140px; }}
    .metric span {{ display: block; color: #66788a; font-size: 12px; }}
    .metric strong {{ display: block; font-size: 20px; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 28px; font-size: 13px; table-layout: fixed; }}
    th, td {{ border: 1px solid #d6dde5; padding: 6px 8px; text-align: right; vertical-align: middle; }}
    th:nth-child(1), th:nth-child(2), th:nth-child(3), td:nth-child(1), td:nth-child(2), td:nth-child(3) {{ text-align: left; }}
    th:nth-child(8), th:nth-child(9), td:nth-child(8), td:nth-child(9) {{ width: 270px; text-align: center; }}
    th {{ background: #edf2f7; }}
    tr:nth-child(even) {{ background: #f8fafc; }}
    .revenue-bars {{ width: 270px; height: 82px; display: block; margin: 0 auto; }}
    .chart-value {{ font-size: 8px; font-weight: 700; fill: #334155; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
    .chart-month {{ font-size: 9px; fill: #64748B; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
    .legend {{ color: #64748B; font-size: 12px; margin-bottom: 12px; }}
  </style>
</head>
<body>
  <h1>人數不限徵人需求度與近六月營收報表</h1>
  <div class="summary">{summary_html}</div>
  <div class="legend">紅色代表營收成長率為正，綠色代表成長率為負；每列長條以該公司該指標近六個月最大絕對值縮放，缺值以 - 呈現。</div>
  <h2>今日新增不限徵才</h2>
  {render_table(new_rows)}
  <h2>營收轉正觀察</h2>
  {render_table(revenue_turnaround_rows)}
  <h2>營收雙指標改善觀察</h2>
  {render_table(current_month_revenue_increase_rows)}
  <h2>營收強勢延續公司</h2>
  {render_table(revenue_growth_rows)}
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")


def build_manifest(
    *,
    report_date_key: str,
    report_date: str,
    previous_date: str,
    latest_csv: Path,
    previous_csv: Path,
    db_path: Path,
    output_dir: Path,
    html_report: Path,
    new_unlimited_csv: Path,
    current_month_revenue_increase_csv: Path,
    revenue_turnaround_csv: Path,
    revenue_growth_csv: Path,
    anomaly_summary_json: Path,
    revenue_snapshot_csv: Path,
    revenue_snapshot_manifest: Path,
    revenue_snapshot_payload: dict[str, Any],
    manifest_path: Path,
    report_rows: list[dict[str, Any]],
    previous_unlimited_count: int,
    new_rows: list[dict[str, Any]],
    current_month_revenue_increase_rows: list[dict[str, Any]],
    revenue_turnaround_rows: list[dict[str, Any]],
    revenue_growth_rows: list[dict[str, Any]],
    missing_revenue: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "2026-05-15",
        "report_type": "unlimited_hiring_revenue_report",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_yyyymmdd": report_date_key,
        "report_date": report_date,
        "previous_date": previous_date,
        "unlimited_filter_rule": "unlimited_job_count_gt_zero",
        "latest_csv": str(latest_csv),
        "previous_csv": str(previous_csv),
        "db_path": str(db_path),
        "latest_unlimited_count": len(report_rows),
        "previous_unlimited_count": previous_unlimited_count,
        "new_unlimited_count": len(new_rows),
        "new_unlimited_rule": "latest_unlimited_codes_minus_previous_unlimited_codes",
        "current_month_revenue_increase_rule": "latest_month_mom_gt_previous_month_mom_and_latest_month_yoy_gt_previous_month_yoy_and_previous_month_mom_or_yoy_non_positive",
        "current_month_revenue_increase_count": len(current_month_revenue_increase_rows),
        "revenue_turnaround_rule": "latest_month_yoy_turns_positive_and_latest_month_mom_positive_excluding_current_month_increase",
        "revenue_turnaround_count": len(revenue_turnaround_rows),
        "revenue_growth_rule": "latest_three_available_months_mom_and_yoy_strictly_increasing",
        "revenue_growth_count": len(revenue_growth_rows),
        "revenue_covered_count": len(report_rows) - len(missing_revenue),
        "revenue_missing_count": len(missing_revenue),
        "revenue_missing_codes": missing_revenue,
        "revenue_snapshot_row_count": revenue_snapshot_payload["row_count"],
        "telegram": {
            "enabled": False,
            "send_attempted": False,
            "reason": "Telegram sendDocument is handled by run_hiring_demand.sh only when HIRING_TELEGRAM_SEND_MODE=enabled.",
        },
        "outputs": {
            "output_dir": str(output_dir),
            "html_report": str(html_report),
            "new_unlimited_csv": str(new_unlimited_csv),
            "current_month_revenue_increase_csv": str(current_month_revenue_increase_csv),
            "revenue_turnaround_csv": str(revenue_turnaround_csv),
            "revenue_growth_csv": str(revenue_growth_csv),
            "anomaly_summary_json": str(anomaly_summary_json),
            "revenue_snapshot_csv": str(revenue_snapshot_csv),
            "revenue_snapshot_manifest": str(revenue_snapshot_manifest),
            "manifest": str(manifest_path),
        },
        "revenue_snapshot": {
            "source_db_path": revenue_snapshot_payload["source_db_path"],
            "source_table": revenue_snapshot_payload["source_table"],
            "snapshot_csv_path": revenue_snapshot_payload["snapshot_csv_path"],
            "snapshot_manifest_path": str(revenue_snapshot_manifest),
            "row_count": revenue_snapshot_payload["row_count"],
            "updated_at_min": revenue_snapshot_payload["updated_at_min"],
            "updated_at_max": revenue_snapshot_payload["updated_at_max"],
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_report(args: argparse.Namespace) -> dict[str, Any]:
    data_dir = Path(args.data_dir)
    db_path = Path(args.db_path)
    latest_csv = Path(args.latest_csv) if args.latest_csv else None
    previous_csv = Path(args.previous_csv) if args.previous_csv else None
    if not latest_csv or not previous_csv:
        latest_csv, previous_csv = find_latest_and_previous_csv(data_dir)

    report_date_key, report_date = parse_csv_date(latest_csv)
    _, previous_date = parse_csv_date(previous_csv)
    output_dir = Path(args.output_dir) if args.output_dir else data_dir / "reports" / report_date_key
    html_report = output_dir / f"unlimited_hiring_revenue_report_{report_date_key}.html"
    new_unlimited_csv = output_dir / f"new_unlimited_companies_{report_date_key}.csv"
    current_month_revenue_increase_csv = output_dir / f"current_month_revenue_increase_companies_{report_date_key}.csv"
    revenue_turnaround_csv = output_dir / f"revenue_turnaround_companies_{report_date_key}.csv"
    revenue_growth_csv = output_dir / f"revenue_growth_companies_{report_date_key}.csv"
    anomaly_summary_json = output_dir / f"anomaly_summary_{report_date_key}.json"
    revenue_snapshot_dir = Path(args.revenue_snapshot_dir) if args.revenue_snapshot_dir else data_dir / "revenue_snapshots"
    revenue_snapshot_csv = revenue_snapshot_dir / f"monthly_revenue_summary_{report_date_key}.csv"
    revenue_snapshot_manifest = revenue_snapshot_dir / f"monthly_revenue_snapshot_manifest_{report_date_key}.json"
    manifest_path = output_dir / f"unlimited_hiring_revenue_report_manifest_{report_date_key}.json"
    obsolete_previous_unlimited_csv = output_dir / f"previous_unlimited_companies_{report_date_key}.csv"
    if obsolete_previous_unlimited_csv.exists():
        obsolete_previous_unlimited_csv.unlink()

    latest_rows = read_hiring_rows(latest_csv)
    previous_rows = read_hiring_rows(previous_csv)
    latest_unlimited = select_unlimited_rows(latest_rows)
    previous_unlimited = select_unlimited_rows(previous_rows)
    stock_codes = sorted({row.get("股票代碼", "") for row in latest_unlimited if row.get("股票代碼", "")})
    revenue_snapshot_rows = load_all_revenue_summary_rows(db_path)
    revenue_by_code = {str(row.get("stock_code", "")): row for row in revenue_snapshot_rows if str(row.get("stock_code", "")) in stock_codes}
    report_rows, new_rows, current_month_revenue_increase_rows, revenue_turnaround_rows, revenue_growth_rows, missing_revenue = build_report_rows(latest_rows, previous_rows, revenue_by_code)

    write_csv(revenue_snapshot_csv, [normalize_revenue_snapshot_row(row) for row in revenue_snapshot_rows], REVENUE_SNAPSHOT_FIELDS)
    revenue_snapshot_payload = build_revenue_snapshot_manifest(
        report_date_key=report_date_key,
        db_path=db_path,
        snapshot_csv=revenue_snapshot_csv,
        snapshot_rows=revenue_snapshot_rows,
    )
    write_json(revenue_snapshot_manifest, revenue_snapshot_payload)
    write_csv(new_unlimited_csv, new_rows, REPORT_FIELDS)
    write_csv(current_month_revenue_increase_csv, current_month_revenue_increase_rows, REPORT_FIELDS)
    write_csv(revenue_turnaround_csv, revenue_turnaround_rows, REPORT_FIELDS)
    write_csv(revenue_growth_csv, revenue_growth_rows, REPORT_FIELDS)
    anomaly_summary = build_anomaly_summary(
        report_date=report_date,
        previous_date=previous_date,
        latest_unlimited_count=len(report_rows),
        previous_unlimited_count=len(previous_unlimited),
        revenue_covered_count=len(report_rows) - len(missing_revenue),
        new_rows=new_rows,
        current_month_revenue_increase_rows=current_month_revenue_increase_rows,
        revenue_turnaround_rows=revenue_turnaround_rows,
        revenue_growth_rows=revenue_growth_rows,
    )
    write_json(anomaly_summary_json, anomaly_summary)
    write_html_report(
        html_report,
        report_date=report_date,
        previous_date=previous_date,
        report_rows=report_rows,
        new_rows=new_rows,
        current_month_revenue_increase_rows=current_month_revenue_increase_rows,
        revenue_turnaround_rows=revenue_turnaround_rows,
        revenue_growth_rows=revenue_growth_rows,
        missing_revenue=missing_revenue,
    )
    manifest = build_manifest(
        report_date_key=report_date_key,
        report_date=report_date,
        previous_date=previous_date,
        latest_csv=latest_csv,
        previous_csv=previous_csv,
        db_path=db_path,
        output_dir=output_dir,
        html_report=html_report,
        new_unlimited_csv=new_unlimited_csv,
        current_month_revenue_increase_csv=current_month_revenue_increase_csv,
        revenue_turnaround_csv=revenue_turnaround_csv,
        revenue_growth_csv=revenue_growth_csv,
        anomaly_summary_json=anomaly_summary_json,
        revenue_snapshot_csv=revenue_snapshot_csv,
        revenue_snapshot_manifest=revenue_snapshot_manifest,
        revenue_snapshot_payload=revenue_snapshot_payload,
        manifest_path=manifest_path,
        report_rows=report_rows,
        previous_unlimited_count=len(previous_unlimited),
        new_rows=new_rows,
        current_month_revenue_increase_rows=current_month_revenue_increase_rows,
        revenue_turnaround_rows=revenue_turnaround_rows,
        revenue_growth_rows=revenue_growth_rows,
        missing_revenue=missing_revenue,
    )
    write_json(manifest_path, manifest)
    if args.latest_manifest_path:
        latest_manifest_path = Path(args.latest_manifest_path)
    elif args.output_dir:
        latest_manifest_path = output_dir / "latest_unlimited_hiring_revenue_report_manifest.json"
    else:
        latest_manifest_path = output_dir.parent / "latest_unlimited_hiring_revenue_report_manifest.json"
    shutil.copyfile(manifest_path, latest_manifest_path)
    manifest["outputs"]["latest_manifest"] = str(latest_manifest_path)
    write_json(manifest_path, manifest)
    write_json(latest_manifest_path, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate local unlimited-hiring revenue report artifacts.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Directory containing *_hiring_demand.csv files.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite DB containing monthly_revenue_summary.")
    parser.add_argument("--output-dir", default="", help="Output directory. Defaults to data/reports/YYYYMMDD.")
    parser.add_argument("--latest-csv", default="", help="Optional latest hiring demand CSV path.")
    parser.add_argument("--previous-csv", default="", help="Optional previous hiring demand CSV path.")
    parser.add_argument("--latest-manifest-path", default="", help="Optional latest manifest copy path.")
    parser.add_argument("--revenue-snapshot-dir", default="", help="Optional directory for monthly_revenue_summary CSV snapshots.")
    return parser


def main() -> int:
    manifest = generate_report(build_parser().parse_args())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
