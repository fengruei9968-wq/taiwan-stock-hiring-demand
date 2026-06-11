#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone web runtime for 上市櫃公司徵人需求度.

This service intentionally serves only the hiring-demand page and JSON
artifacts owned by this folder. It does not depend on the parent project's
stage3_web, users.db, fixed_assets.db, inventory routes, or daily-memo routes.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, redirect, render_template, request
from flask_cors import CORS


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "investment.db")).expanduser()
INVESTMENT_HOME_URL = os.environ.get(
    "INVESTMENT_HOME_URL",
    "https://financial-report-data-processing.up.railway.app/",
)
HIRING_REVENUE_WINDOW_MONTHS = 6
HIRING_WEB_DATA_FILENAME = "latest_hiring_demand_web_data.json"
HIRING_REVENUE_BATCH_FILENAME = "latest_hiring_revenue_batch.json"
HIRING_REVENUE_AMOUNTS_FILENAME = "latest_hiring_revenue_amounts.json"
FAVORITES_PATH = Path(os.environ.get("HIRING_FAVORITES_PATH", BASE_DIR / "data" / "hiring_favorites.json"))
FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"

HIRING_ANOMALY_SECTION_ORDER = [
    "today_new_unlimited",
    "revenue_turnaround",
    "current_month_revenue_increase",
    "three_month_revenue_growth",
]
HIRING_ANOMALY_SECTION_LABELS = {
    "today_new_unlimited": "今日新增不限徵才",
    "current_month_revenue_increase": "營收雙指標改善觀察",
    "revenue_turnaround": "營收轉正觀察",
    "three_month_revenue_growth": "營收強勢延續公司",
}
HIRING_ANOMALY_SECTION_DESCRIPTIONS = {
    "today_new_unlimited": "今日新進入不限職缺名單的公司，用來和昨日名單比對。",
    "current_month_revenue_increase": "不限徵才公司中，最新月 MoM 與 YoY 都比上月走升。",
    "revenue_turnaround": "不限徵才公司中，最新月 YoY 由負轉正，且最新月 MoM 仍為正。",
    "three_month_revenue_growth": "不限徵才公司中，近三個有效月份的 MoM 與 YoY 連續走升。",
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.secret_key = os.environ.get("SECRET_KEY", "hiring-demand-standalone-dev")
CORS(app)


def _report_dirs() -> list[Path]:
    env_value = os.environ.get("HIRING_ANOMALY_REPORTS_DIR", "")
    if env_value:
        dirs = [Path(part).expanduser() for part in env_value.split(os.pathsep) if part.strip()]
    else:
        dirs = [BASE_DIR / "hiring_reports", BASE_DIR / "data" / "hiring_reports"]
    unique: list[Path] = []
    seen: set[str] = set()
    for directory in dirs:
        key = str(directory)
        if key not in seen:
            unique.append(directory)
            seen.add(key)
    return unique


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("failed to read JSON %s: %s", path, exc)
        return None


def _read_hiring_web_data_payload() -> dict[str, Any] | None:
    for directory in _report_dirs():
        payload = _load_json(directory / HIRING_WEB_DATA_FILENAME)
        if payload and payload.get("schema_version") == "hiring_demand_web_data_v1" and isinstance(payload.get("data"), list):
            return payload
    return None


def _read_hiring_revenue_batch_payload() -> dict[str, Any] | None:
    for directory in _report_dirs():
        payload = _load_json(directory / HIRING_REVENUE_BATCH_FILENAME)
        if payload and payload.get("schema_version") == "hiring_revenue_batch_v1" and isinstance(payload.get("data"), dict):
            return payload
    return None


def _read_hiring_revenue_amounts_payload() -> dict[str, Any] | None:
    for directory in _report_dirs():
        payload = _load_json(directory / HIRING_REVENUE_AMOUNTS_FILENAME)
        if payload and payload.get("schema_version") == "hiring_revenue_amounts_v1" and isinstance(payload.get("data"), dict):
            return payload
    return None


def _fetch_datetime_from_payload(payload: dict[str, Any]) -> str | None:
    latest_created_at = payload.get("latest_created_at_utc")
    if latest_created_at:
        try:
            dt_utc = datetime.strptime(str(latest_created_at), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return dt_utc.astimezone(timezone(timedelta(hours=8))).strftime("%Y/%m/%d %H:%M:%S")
        except (TypeError, ValueError):
            logger.warning("bad latest_created_at_utc: %s", latest_created_at)
    fetch_date = payload.get("fetch_date")
    return str(fetch_date).replace("-", "/") if fetch_date else None


def _normalize_hiring_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        normalized.append(
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
    return normalized


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _load_favorites() -> list[str]:
    payload = _load_json(FAVORITES_PATH) or {}
    favorites = payload.get("favorites", [])
    return sorted({str(code) for code in favorites if str(code).isdigit() and len(str(code)) == 4})


def _save_favorites(favorites: list[str]) -> None:
    FAVORITES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "hiring_favorites_standalone_v1",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "favorites": sorted({str(code) for code in favorites}),
    }
    FAVORITES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _report_key(value: str | None) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return text
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text.replace("-", "")
    return ""


def _report_date_from_key(report_key: str | None) -> str | None:
    key = _report_key(report_key)
    if not key:
        return None
    return f"{key[:4]}-{key[4:6]}-{key[6:8]}"


def _anomaly_filename(report_date: str) -> str:
    return f"{report_date}_徵人需求度每日異常偵測摘要.png"


def _read_anomaly_summary(path: Path) -> dict[str, Any] | None:
    payload = _load_json(path)
    if not payload:
        return None
    report_date = payload.get("report_date")
    if not report_date:
        report_date = _report_date_from_key(path.stem.replace("anomaly_summary_", ""))
    key = _report_key(report_date)
    if not report_date or not key:
        return None
    return {
        "path": path,
        "payload": payload,
        "report_date": str(report_date),
        "report_key": key,
        "generated_at": payload.get("generated_at") or payload.get("created_at"),
    }


def _find_anomaly_summaries() -> list[dict[str, Any]]:
    latest_by_key: dict[str, dict[str, Any]] = {}
    for directory in _report_dirs():
        if not directory.exists():
            continue
        for path in sorted(directory.glob("**/anomaly_summary_*.json")):
            summary = _read_anomaly_summary(path)
            if summary:
                latest_by_key[summary["report_key"]] = summary
        latest = directory / "latest_anomaly_summary.json"
        summary = _read_anomaly_summary(latest)
        if summary:
            latest_by_key[summary["report_key"]] = summary
    return sorted(latest_by_key.values(), key=lambda item: item["report_key"], reverse=True)


def _coerce_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_anomaly_company(company: dict[str, Any]) -> dict[str, Any]:
    months = []
    mom = []
    yoy = []
    for index in range(1, HIRING_REVENUE_WINDOW_MONTHS + 1):
        label = company.get(f"m{index}_label")
        months.append(str(label) if label not in (None, "") else None)
        mom.append(_coerce_optional_float(company.get(f"m{index}_mom")))
        yoy.append(_coerce_optional_float(company.get(f"m{index}_yoy")))
    return {
        "stock_code": str(company.get("stock_code") or ""),
        "company_short_name": str(company.get("company_short_name") or company.get("公司簡稱") or ""),
        "market": str(company.get("market") or company.get("市場類別") or ""),
        "unlimited_job_count": company.get("unlimited_job_count") or company.get("不限職缺數") or "",
        "explicit_headcount": company.get("explicit_headcount") or company.get("明確需求人數") or "",
        "demand_ratio": company.get("demand_ratio") or company.get("徵人需求度") or "",
        "today_new": company.get("today_new") or company.get("今日新增公司") or "",
        "revenue": {"months": months, "mom": mom, "yoy": yoy},
    }


def _serialize_anomaly_list_item(summary: dict[str, Any]) -> dict[str, Any]:
    payload = summary["payload"]
    report_date = summary["report_date"]
    report_key = summary["report_key"]
    return {
        "report_key": report_key,
        "report_date": report_date,
        "filename": _anomaly_filename(report_date),
        "title": payload.get("notification_title") or f"{report_date}_異常偵測摘要",
        "generated_at": summary["generated_at"] or None,
        "alert_required": bool(payload.get("alert_required")),
        "counts": payload.get("counts") or {},
        "detail_url": f"/api/hiring-demand/anomaly-summaries/{report_key}",
    }


def _serialize_anomaly_detail(summary: dict[str, Any]) -> dict[str, Any]:
    payload = summary["payload"]
    events = payload.get("events") or {}
    sections = []
    for key in HIRING_ANOMALY_SECTION_ORDER:
        event = events.get(key) or {}
        sections.append(
            {
                "key": key,
                "title": event.get("plain_label") or HIRING_ANOMALY_SECTION_LABELS.get(key, key),
                "rule_id": event.get("rule_id") or "",
                "description": HIRING_ANOMALY_SECTION_DESCRIPTIONS.get(key, ""),
                "count": event.get("count", 0),
                "stock_codes": event.get("stock_codes") or [],
                "companies": [_normalize_anomaly_company(company) for company in event.get("companies") or []],
            }
        )
    report_date = summary["report_date"]
    return {
        "report_key": summary["report_key"],
        "report_date": report_date,
        "filename": _anomaly_filename(report_date),
        "title": payload.get("notification_title") or f"{report_date}_異常偵測摘要",
        "generated_at": summary["generated_at"] or None,
        "previous_date": payload.get("previous_date"),
        "alert_required": bool(payload.get("alert_required")),
        "counts": payload.get("counts") or {},
        "sections": sections,
        "revenue_window_months": HIRING_REVENUE_WINDOW_MONTHS,
    }


@app.after_request
def add_no_store_headers(response):
    if request.path.startswith("/api/") or request.path == "/hiring-demand":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    return redirect("/hiring-demand")


@app.route("/logout")
def logout():
    return redirect("/hiring-demand")


@app.route("/hiring-demand")
def hiring_demand():
    return render_template("hiring_demand.html", user=None, investment_home_url=INVESTMENT_HOME_URL)


@app.route("/api/health")
def health():
    demand_payload = _read_hiring_web_data_payload()
    revenue_payload = _read_hiring_revenue_batch_payload()
    return jsonify(
        {
            "service": "hiring-demand-standalone",
            "db_path": str(DB_PATH),
            "db_exists": DB_PATH.exists(),
            "hiring_reports_dirs": [str(path) for path in _report_dirs()],
            "hiring_fetch_date": demand_payload.get("fetch_date") if demand_payload else None,
            "hiring_count": len(demand_payload.get("data", [])) if demand_payload else 0,
            "revenue_report_date": revenue_payload.get("report_date") if revenue_payload else None,
            "revenue_count": revenue_payload.get("count") if revenue_payload else 0,
        }
    )


@app.route("/api/hiring-demand")
def get_hiring_demand():
    payload = _read_hiring_web_data_payload()
    if payload:
        return jsonify(
            {
                "data": _normalize_hiring_rows(payload.get("data", [])),
                "fetch_date": payload.get("fetch_date"),
                "fetch_datetime": _fetch_datetime_from_payload(payload),
                "data_source": "hiring_reports",
            }
        )
    return jsonify({"data": [], "fetch_date": None, "fetch_datetime": None, "data_source": "missing_hiring_reports"})


@app.route("/api/hiring-demand/jobs/<stock_code>")
def get_hiring_demand_jobs(stock_code: str):
    payload = _read_hiring_web_data_payload()
    if payload:
        jobs = (payload.get("jobs_by_stock_code") or {}).get(str(stock_code), [])
        return jsonify({"jobs": jobs, "data_source": "hiring_reports"})
    return jsonify({"jobs": [], "data_source": "missing_hiring_reports"})


@app.route("/api/hiring-demand/revenue-batch")
def get_hiring_revenue_batch():
    payload = _read_hiring_revenue_batch_payload()
    if payload:
        return jsonify(
            {
                "data": payload.get("data") or {},
                "count": payload.get("count", 0),
                "updated_at": payload.get("updated_at"),
                "report_date": payload.get("report_date"),
                "window_months": payload.get("window_months", HIRING_REVENUE_WINDOW_MONTHS),
                "data_source": "hiring_reports",
            }
        )
    return jsonify({"data": {}, "count": 0, "window_months": HIRING_REVENUE_WINDOW_MONTHS, "data_source": "missing_hiring_reports"})


@app.route("/api/hiring-demand/favorites")
def get_hiring_favorites():
    favorites = _load_favorites()
    return jsonify({"favorites": favorites, "count": len(favorites)})


@app.route("/api/hiring-demand/favorites/<stock_code>", methods=["POST", "DELETE"])
def update_hiring_favorite(stock_code: str):
    normalized = str(stock_code or "").strip()
    if not normalized.isdigit() or len(normalized) != 4:
        return jsonify({"error": "invalid_stock_code", "message": "股票代碼格式不正確"}), 400
    favorites = set(_load_favorites())
    if request.method == "POST":
        favorites.add(normalized)
        is_favorite = True
    else:
        favorites.discard(normalized)
        is_favorite = False
    _save_favorites(sorted(favorites))
    return jsonify({"stock_code": normalized, "is_favorite": is_favorite})


@app.route("/api/hiring-demand/anomaly-summaries")
def get_hiring_anomaly_summaries():
    summaries = [_serialize_anomaly_list_item(summary) for summary in _find_anomaly_summaries()]
    return jsonify({"summaries": summaries, "count": len(summaries), "revenue_window_months": HIRING_REVENUE_WINDOW_MONTHS})


@app.route("/api/hiring-demand/anomaly-summaries/<report_key>")
def get_hiring_anomaly_summary_detail(report_key: str):
    normalized_date = _report_date_from_key(report_key)
    if not normalized_date:
        return jsonify({"error": "invalid_report_date"}), 400
    for summary in _find_anomaly_summaries():
        if summary["report_date"] == normalized_date:
            return jsonify(_serialize_anomaly_detail(summary))
    return jsonify({"error": "not_found"}), 404


@app.route("/api/hiring-demand/anomaly-summaries/<report_key>", methods=["DELETE"])
def delete_hiring_anomaly_summary(report_key: str):
    normalized_key = _report_key(report_key)
    if not normalized_key:
        return jsonify({"error": "invalid_report_date"}), 400
    deleted = []
    for directory in _report_dirs():
        if not directory.exists():
            continue
        for path in sorted(directory.glob(f"**/anomaly_summary_{normalized_key}.json")):
            try:
                path.unlink()
                deleted.append(str(path))
            except FileNotFoundError:
                pass
    return jsonify({"report_key": normalized_key, "deleted_count": len(deleted), "deleted_files": deleted})


@app.route("/api/stock-price/<stock_code>")
def get_stock_price(stock_code: str):
    token = os.environ.get("FINMIND_TOKEN")
    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_code,
            "start_date": start_date,
            "end_date": end_date,
        }
        if token:
            params["token"] = token
        response = requests.get(
            FINMIND_API_URL,
            params=params,
            timeout=15,
        )
        result = response.json()
        data = [
            {
                "date": item.get("date"),
                "open": item.get("open"),
                "high": item.get("max"),
                "low": item.get("min"),
                "close": item.get("close"),
                "volume": item.get("Trading_Volume"),
                "spread": item.get("spread"),
            }
            for item in result.get("data", [])
        ]
        return jsonify({"data": data})
    except requests.Timeout:
        return jsonify({"error": "FinMind API 逾時"}), 504
    except Exception as exc:
        logger.warning("stock price failed for %s: %s", stock_code, exc)
        return jsonify({"data": [], "error": str(exc)[:100]})


@app.route("/api/stock-revenue/<stock_code>")
def get_stock_revenue(stock_code: str):
    def snapshot_response(source: str) -> Any:
        payload = _read_hiring_revenue_amounts_payload()
        if not payload:
            return jsonify({"data": [], "source": source})
        rows = list((payload.get("data") or {}).get(str(stock_code), []))
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        if start_date:
            rows = [row for row in rows if str(row.get("date", "")) >= start_date[:10]]
        if end_date:
            rows = [row for row in rows if str(row.get("date", "")) <= end_date[:10]]
        return jsonify({"data": rows, "source": "hiring_revenue_amounts", "snapshot_report_date": payload.get("report_date")})

    if not DB_PATH.exists():
        return snapshot_response("missing_db")
    try:
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        start_dt = datetime.strptime(start_date[:10], "%Y-%m-%d") if start_date else None
        end_dt = datetime.strptime(end_date[:10], "%Y-%m-%d") if end_date else None
        with _connect_db() as conn:
            table_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_monthly_revenue'"
            ).fetchone()
            if not table_exists:
                return snapshot_response("missing_stock_monthly_revenue")
            rows = conn.execute(
                """
                SELECT stock_code, revenue_year, revenue_month, revenue_amount, revenue_unit,
                       source, source_url, market_type_at_fetch, fetched_at, run_id
                FROM stock_monthly_revenue
                WHERE stock_code = ?
                ORDER BY revenue_year, revenue_month,
                    CASE source
                        WHEN 'mops_sii' THEN 1
                        WHEN 'mops_otc' THEN 1
                        WHEN 'mops_rotc' THEN 1
                        WHEN 'finmind' THEN 2
                        WHEN 'moneydj_emerging_table' THEN 3
                        WHEN 'moneydj_news' THEN 4
                        WHEN 'wantgoo' THEN 5
                        ELSE 9
                    END
                """,
                (stock_code,),
            ).fetchall()
        best_by_month: dict[tuple[int, int], sqlite3.Row] = {}
        source_counts: dict[str, int] = {}
        for row in rows:
            month_dt = datetime(int(row["revenue_year"]), int(row["revenue_month"]), 1)
            if start_dt and month_dt < datetime(start_dt.year, start_dt.month, 1):
                continue
            if end_dt and month_dt > datetime(end_dt.year, end_dt.month, 1):
                continue
            key = (int(row["revenue_year"]), int(row["revenue_month"]))
            if key in best_by_month:
                continue
            best_by_month[key] = row
            source = row["source"] or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1
        data = []
        for (year, month), row in sorted(best_by_month.items()):
            amount = int(row["revenue_amount"])
            revenue = amount * 1000 if row["revenue_unit"] == "thousand_twd" else amount
            data.append(
                {
                    "date": f"{year:04d}-{month:02d}-01",
                    "revenue": revenue,
                    "revenue_thousand": amount if row["revenue_unit"] == "thousand_twd" else round(amount / 1000),
                    "revenue_unit": row["revenue_unit"],
                    "revenue_month": month,
                    "revenue_year": year,
                    "source": row["source"],
                    "source_url": row["source_url"],
                    "market_type_at_fetch": row["market_type_at_fetch"],
                    "fetched_at": row["fetched_at"],
                    "run_id": row["run_id"],
                }
            )
        if data:
            return jsonify({"data": data, "source": "stock_monthly_revenue", "source_counts": source_counts})
        return snapshot_response("empty_stock_monthly_revenue")
    except Exception as exc:
        logger.warning("stock revenue failed for %s: %s", stock_code, exc)
        return snapshot_response(f"db_error:{str(exc)[:80]}")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5055")), debug=True)
