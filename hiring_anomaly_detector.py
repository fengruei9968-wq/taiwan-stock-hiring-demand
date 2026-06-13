#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build local anomaly summaries for hiring-demand notifications.

This module only creates local JSON-ready payloads. It does not send Telegram
messages, deploy, or modify the web app.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


HIRING_DEMAND_WEB_URL = "https://financial-report-data-processing.up.railway.app/hiring-demand"
REVENUE_MONTH_COUNT = 6


def compact_company(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "stock_code": str(row.get("股票代碼", "")),
        "company_short_name": str(row.get("公司簡稱", "")),
        "market": str(row.get("市場類別", "")),
        "unlimited_job_count": row.get("不限職缺數", ""),
        "explicit_headcount": row.get("明確需求人數", ""),
        "demand_ratio": row.get("徵人需求度", ""),
        "today_new": row.get("今日新增公司", ""),
    }
    for index in range(1, REVENUE_MONTH_COUNT + 1):
        payload[f"m{index}_label"] = row.get(f"m{index}_label", "")
        payload[f"m{index}_mom"] = row.get(f"m{index}_mom", "")
        payload[f"m{index}_yoy"] = row.get(f"m{index}_yoy", "")
    return payload


def build_anomaly_event(rule_id: str, plain_label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "plain_label": plain_label,
        "count": len(rows),
        "stock_codes": [str(row.get("股票代碼", "")) for row in rows],
        "companies": [compact_company(row) for row in rows],
    }


def build_anomaly_summary(
    *,
    report_date: str,
    previous_date: str,
    latest_unlimited_count: int,
    previous_unlimited_count: int,
    revenue_covered_count: int,
    new_rows: list[dict[str, Any]],
    current_month_revenue_increase_rows: list[dict[str, Any]],
    revenue_turnaround_rows: list[dict[str, Any]],
    revenue_growth_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    events = {
        "today_new_unlimited": build_anomaly_event(
            "latest_unlimited_codes_minus_previous_unlimited_codes",
            "今日新增不限徵才",
            new_rows,
        ),
        "revenue_turnaround": build_anomaly_event(
            "latest_month_yoy_turns_positive_and_latest_month_mom_positive_excluding_current_month_increase",
            "營收轉正觀察",
            revenue_turnaround_rows,
        ),
        "current_month_revenue_increase": build_anomaly_event(
            "latest_month_mom_gt_previous_month_mom_and_latest_month_yoy_gt_previous_month_yoy_and_previous_month_mom_or_yoy_non_positive",
            "營收雙指標改善觀察",
            current_month_revenue_increase_rows,
        ),
        "three_month_revenue_growth": build_anomaly_event(
            "latest_three_available_months_mom_and_yoy_strictly_increasing",
            "營收強勢延續公司",
            revenue_growth_rows,
        ),
    }
    return {
        "schema_version": "2026-05-15",
        "summary_type": "hiring_demand_anomaly_summary",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_date": report_date,
        "previous_date": previous_date,
        "notification_title": f"{report_date}_異常偵測摘要",
        "alert_required": any(event["count"] > 0 for event in events.values()),
        "alert_policy": {
            "revenue_change_direction": "increase_only",
            "telegram_send_default": "disabled_until_HIRING_TELEGRAM_SEND_MODE_enabled",
            "web_button_status": "implemented_as_structured_summary_modal",
        },
        "web": {
            "hiring_demand_url": HIRING_DEMAND_WEB_URL,
            "web_button_proposal": "日期_異常偵測摘要",
            "web_button_implementation_status": "implemented",
        },
        "counts": {
            "latest_unlimited_count": latest_unlimited_count,
            "previous_unlimited_count": previous_unlimited_count,
            "revenue_covered_count": revenue_covered_count,
            "today_new_unlimited_count": events["today_new_unlimited"]["count"],
            "current_month_revenue_increase_count": events["current_month_revenue_increase"]["count"],
            "revenue_turnaround_count": events["revenue_turnaround"]["count"],
            "three_month_revenue_growth_count": events["three_month_revenue_growth"]["count"],
        },
        "events": events,
    }
