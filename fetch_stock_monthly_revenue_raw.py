#!/usr/bin/env python3
"""
Fetch stock monthly revenue raw amounts into stage3_web/investment.db.

This is separate from fetch_monthly_revenue.py:
- fetch_monthly_revenue.py stores the six-month MoM/YoY summary for hiring reports.
- this script stores raw monthly revenue amounts for charts such as inventory detail.
- official MOPS monthly revenue CSV is the primary source.
- listed / OTC companies can fall back to FinMind for missing months.
- emerging companies use MOPS rotc CSV first, then MOPS rotc HTML as fallback.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("HIRING_PROJECT_ROOT", BASE_DIR.parent)).resolve()
STAGE3_DIR = Path(os.environ.get("HIRING_STAGE3_DIR", BASE_DIR / "stage3_web")).resolve()
DB_PATH = Path(os.environ.get("DB_PATH", STAGE3_DIR / "investment.db"))
STOCK_CODES_DIR = Path(
    os.environ.get(
        "STOCK_CODES_DIR",
        BASE_DIR / "data" / "stock_codes",
    )
)
OUTPUT_ROOT = BASE_DIR / "data" / "stock_monthly_revenue_raw"
FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"
DEFAULT_START_MONTH = "2021-01"
DEFAULT_END_MONTH = datetime.now().strftime("%Y-%m")
WANTGOO_URL_TEMPLATE = "https://www.wantgoo.com/stock/{code}/financial-statements/monthly-revenue"
MOPS_CSV_URL_TEMPLATE = "https://mopsov.twse.com.tw/nas/t21/{folder}/t21sc03_{roc_year}_{month}.csv"
MOPS_EMERGING_HTML_URL_TEMPLATE = "https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_{roc_year}_{month}_0.html"
MOPS_MARKET_FOLDERS = {
    "上市": "sii",
    "上櫃": "otc",
    "興櫃": "rotc",
}
SOURCE_PRIORITY = {
    "mops_sii": 10,
    "mops_otc": 10,
    "mops_rotc": 10,
    "finmind": 20,
    "moneydj_emerging_table": 20,
    "moneydj_news": 30,
    "wantgoo": 40,
}


@dataclass(frozen=True)
class StockMeta:
    stock_code: str
    short_name: str = ""
    full_name: str = ""
    market_type: str = ""


@dataclass(frozen=True)
class RevenueRecord:
    stock_code: str
    revenue_year: int
    revenue_month: int
    revenue_amount: int
    revenue_unit: str
    source: str
    source_url: str
    market_type_at_fetch: str
    company_short_name: str
    company_full_name: str
    fetched_at: str
    run_id: str

    @property
    def period(self) -> str:
        return f"{self.revenue_year:04d}-{self.revenue_month:02d}"

    def csv_row(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "revenue_year": self.revenue_year,
            "revenue_month": self.revenue_month,
            "revenue_amount": self.revenue_amount,
            "revenue_unit": self.revenue_unit,
            "source": self.source,
            "source_url": self.source_url,
            "market_type_at_fetch": self.market_type_at_fetch,
            "company_short_name": self.company_short_name,
            "company_full_name": self.company_full_name,
            "fetched_at": self.fetched_at,
            "run_id": self.run_id,
        }


def parse_month(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})", value.strip())
    if not match:
        raise ValueError(f"invalid month: {value!r}; expected YYYY-MM")
    year = int(match.group(1))
    month = int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid month number: {value!r}")
    return year, month


def month_key(year: int, month: int) -> int:
    return year * 12 + month


def month_in_range(year: int, month: int, start: tuple[int, int], end: tuple[int, int]) -> bool:
    key = month_key(year, month)
    return month_key(*start) <= key <= month_key(*end)


def add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def iter_months(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start
    while month_key(year, month) <= month_key(*end):
        months.append((year, month))
        year, month = add_months(year, month, 1)
    return months


def month_keys_in_range(start: tuple[int, int], end: tuple[int, int]) -> set[tuple[int, int]]:
    return set(iter_months(start, end))


def record_month_keys(records: list[RevenueRecord]) -> set[tuple[int, int]]:
    return {(record.revenue_year, record.revenue_month) for record in records}


def missing_month_keys(
    records: list[RevenueRecord],
    start_month: tuple[int, int],
    end_month: tuple[int, int],
) -> set[tuple[int, int]]:
    return month_keys_in_range(start_month, end_month) - record_month_keys(records)


def month_to_date(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-01"


def roc_year(year: int) -> int:
    return year - 1911


def mops_month_source_url(year: int, month: int, market_type: str, *, fallback: bool = False) -> str:
    folder = MOPS_MARKET_FOLDERS[market_type]
    if fallback and folder == "rotc":
        return MOPS_EMERGING_HTML_URL_TEMPLATE.format(roc_year=roc_year(year), month=month)
    return MOPS_CSV_URL_TEMPLATE.format(folder=folder, roc_year=roc_year(year), month=month)


def latest_stock_codes_csv(stock_codes_dir: Path) -> Path:
    candidates = []
    for path in stock_codes_dir.glob("*stock_codes*.csv"):
        name = path.name
        if "不完整" in name:
            continue
        match = re.match(r"(\d{8})_stock_codes(_all)?\.csv$", name)
        if not match:
            continue
        date_key = match.group(1)
        all_rank = 1 if match.group(2) else 0
        candidates.append((date_key, all_rank, path))
    if not candidates:
        raise FileNotFoundError(f"no complete stock_codes csv found under {stock_codes_dir}")
    candidates.sort()
    return candidates[-1][2]


def load_stock_codes(
    path: Path,
    requested_codes: list[str] | None,
    market_types: set[str] | None = None,
    exclude_dr: bool = True,
) -> dict[str, StockMeta]:
    requested = set(requested_codes or [])
    records: dict[str, StockMeta] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = (row.get("股票代碼") or "").strip()
            if not code:
                continue
            if requested and code not in requested:
                continue
            market_type = (row.get("市場類別") or "").strip()
            if market_types and market_type not in market_types:
                continue
            short_name = (row.get("公司簡稱") or "").strip()
            full_name = (row.get("公司全名") or "").strip()
            if exclude_dr and is_dr_stock(code, short_name, full_name):
                continue
            records[code] = StockMeta(
                stock_code=code,
                short_name=short_name,
                full_name=full_name,
                market_type=market_type,
            )
    missing = sorted(requested - set(records))
    if missing:
        raise ValueError(f"requested codes not found in {path.name}: {', '.join(missing)}")
    return records


def is_dr_stock(code: str, short_name: str, full_name: str) -> bool:
    return short_name.endswith("-DR") or full_name.endswith("-DR")


def list_excluded_dr_stocks(path: Path, market_types: set[str] | None = None) -> list[dict[str, str]]:
    excluded: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = (row.get("股票代碼") or "").strip()
            market_type = (row.get("市場類別") or "").strip()
            short_name = (row.get("公司簡稱") or "").strip()
            full_name = (row.get("公司全名") or "").strip()
            if market_types and market_type not in market_types:
                continue
            if is_dr_stock(code, short_name, full_name):
                excluded.append(
                    {
                        "stock_code": code,
                        "market_type": market_type,
                        "company_short_name": short_name,
                        "company_full_name": full_name,
                    }
                )
    return excluded


def load_finmind_token() -> str:
    token = os.environ.get("FINMIND_TOKEN", "").strip()
    if token:
        return token
    for env_path in [BASE_DIR / ".env", STAGE3_DIR / ".env", PROJECT_ROOT / ".env"]:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("FINMIND_TOKEN="):
                token = line.split("=", 1)[1].strip().strip("\"'")
                if token:
                    return token
    return ""


def ensure_raw_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_monthly_revenue (
            stock_code TEXT NOT NULL,
            revenue_year INTEGER NOT NULL,
            revenue_month INTEGER NOT NULL,
            revenue_amount INTEGER NOT NULL,
            revenue_unit TEXT NOT NULL DEFAULT 'thousand_twd',
            source TEXT NOT NULL,
            source_url TEXT,
            market_type_at_fetch TEXT,
            company_short_name TEXT,
            company_full_name TEXT,
            fetched_at TEXT NOT NULL,
            run_id TEXT NOT NULL,
            PRIMARY KEY (stock_code, revenue_year, revenue_month, source)
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(stock_monthly_revenue)")}
    expected_columns = {
        "source_url": "TEXT",
        "market_type_at_fetch": "TEXT",
        "company_short_name": "TEXT",
        "company_full_name": "TEXT",
        "run_id": "TEXT",
    }
    for column, column_type in expected_columns.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE stock_monthly_revenue ADD COLUMN {column} {column_type}")
    conn.commit()


def save_records(conn: sqlite3.Connection, records: list[RevenueRecord]) -> int:
    if not records:
        return 0
    conn.executemany(
        """
        INSERT OR REPLACE INTO stock_monthly_revenue (
            stock_code, revenue_year, revenue_month, revenue_amount, revenue_unit,
            source, source_url, market_type_at_fetch, company_short_name, company_full_name,
            fetched_at, run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                record.stock_code,
                record.revenue_year,
                record.revenue_month,
                record.revenue_amount,
                record.revenue_unit,
                record.source,
                record.source_url,
                record.market_type_at_fetch,
                record.company_short_name,
                record.company_full_name,
                record.fetched_at,
                record.run_id,
            )
            for record in records
        ],
    )
    conn.commit()
    return len(records)


def filter_missing_stock_meta(
    conn: sqlite3.Connection,
    stock_meta: dict[str, StockMeta],
    *,
    start_month: tuple[int, int],
    end_month: tuple[int, int],
) -> dict[str, StockMeta]:
    """Keep only companies missing at least one target month in the raw table."""
    if not stock_meta:
        return {}
    ensure_raw_table(conn)
    target_months = month_keys_in_range(start_month, end_month)
    filtered: dict[str, StockMeta] = {}
    for code, meta in stock_meta.items():
        rows = conn.execute(
            """
            SELECT revenue_year, revenue_month
            FROM stock_monthly_revenue
            WHERE stock_code = ?
              AND (revenue_year * 12 + revenue_month) BETWEEN ? AND ?
            GROUP BY revenue_year, revenue_month
            """,
            (code, month_key(*start_month), month_key(*end_month)),
        ).fetchall()
        existing_months = {(int(row[0]), int(row[1])) for row in rows}
        if target_months - existing_months:
            filtered[code] = meta
    return filtered


def fetch_finmind_records(
    *,
    code: str,
    meta: StockMeta,
    token: str,
    start_month: tuple[int, int],
    end_month: tuple[int, int],
    fetched_at: str,
    run_id: str,
) -> list[RevenueRecord]:
    request_start = month_to_date(*start_month)
    end_plus_one = add_months(*end_month, 1)
    request_end = f"{end_plus_one[0]:04d}-{end_plus_one[1]:02d}-28"
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": code,
        "start_date": request_start,
        "end_date": request_end,
        "token": token,
    }
    resp = requests.get(FINMIND_API_URL, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != 200 and "data" not in payload:
        raise RuntimeError(payload.get("msg") or f"FinMind status {payload.get('status')}")

    records = []
    for item in payload.get("data") or []:
        year = item.get("revenue_year")
        month = item.get("revenue_month")
        revenue = item.get("revenue")
        if year is None or month is None or revenue is None:
            continue
        year = int(year)
        month = int(month)
        if not month_in_range(year, month, start_month, end_month):
            continue
        records.append(
            RevenueRecord(
                stock_code=code,
                revenue_year=year,
                revenue_month=month,
                revenue_amount=int(round(float(revenue) / 1000)),
                revenue_unit="thousand_twd",
                source="finmind",
                source_url=FINMIND_API_URL,
                market_type_at_fetch=meta.market_type,
                company_short_name=meta.short_name,
                company_full_name=meta.full_name,
                fetched_at=fetched_at,
                run_id=run_id,
            )
        )
    return records


def fetch_finmind_missing_month_records(
    *,
    code: str,
    meta: StockMeta,
    current_records: list[RevenueRecord],
    token: str,
    start_month: tuple[int, int],
    end_month: tuple[int, int],
    fetched_at: str,
    run_id: str,
) -> tuple[list[RevenueRecord], list[str]]:
    missing_months = missing_month_keys(current_records, start_month, end_month)
    if not missing_months:
        return [], []
    if meta.market_type not in {"上市", "上櫃"}:
        return [], []
    if not token:
        return [], ["finmind_fallback_token_missing_for_mops_gap"]
    try:
        finmind_records = fetch_finmind_records(
            code=code,
            meta=meta,
            token=token,
            start_month=start_month,
            end_month=end_month,
            fetched_at=fetched_at,
            run_id=run_id,
        )
    except Exception as exc:
        return [], [f"finmind_fallback_error: {type(exc).__name__}: {exc}"]
    fallback_records = [
        record
        for record in finmind_records
        if (record.revenue_year, record.revenue_month) in missing_months
    ]
    if not fallback_records:
        return [], ["finmind_fallback_no_rows_for_mops_gap"]
    return fallback_records, []


def parse_int(value: str) -> int | None:
    cleaned = value.strip().replace(",", "").replace("$", "")
    if cleaned in {"", "-", "－", "--"}:
        return None
    try:
        return int(round(float(cleaned)))
    except ValueError:
        return None


def decode_mops_payload(content: bytes, source_url: str) -> str:
    if source_url.endswith(".html"):
        return content.decode("cp950", errors="replace")
    return content.decode("utf-8-sig")


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def parse_mops_html_rows(text: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(text, "html.parser")
    parsed_rows: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    current_header: list[str] = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
            if not cells:
                continue
            normalized_cells = [normalize_header(cell) for cell in cells]
            if any("公司代號" in cell or "營業收入-當月營收" in cell for cell in normalized_cells):
                current_header = normalized_cells
                continue

            code_index = next((idx for idx, cell in enumerate(normalized_cells) if re.fullmatch(r"\d{4}[A-Z]?", cell)), None)
            if code_index is None:
                continue

            row: dict[str, str] = {}
            if current_header and len(current_header) == len(cells):
                row = dict(zip(current_header, cells))
            else:
                revenue_index = code_index + 2 if code_index == 0 else code_index + 3
                if revenue_index >= len(cells):
                    continue
                row = {
                    "公司代號": cells[code_index],
                    "營業收入-當月營收": cells[revenue_index],
                }
            code = normalize_header(row.get("公司代號", ""))
            if code in seen_codes:
                continue
            seen_codes.add(code)
            parsed_rows.append(row)
    return parsed_rows


def fetch_mops_source_rows(source_url: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    resp = requests.get(source_url, timeout=20)
    resp.raise_for_status()
    text = decode_mops_payload(resp.content, source_url)
    if source_url.endswith(".html"):
        return parse_mops_html_rows(text), {"source_format": "html"}
    return list(csv.DictReader(text.splitlines())), {"source_format": "csv"}


def parse_wantgoo_table_text(
    *,
    text: str,
    code: str,
    meta: StockMeta,
    start_month: tuple[int, int],
    end_month: tuple[int, int],
    fetched_at: str,
    run_id: str,
    source_url: str,
) -> list[RevenueRecord]:
    records: list[RevenueRecord] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < 2:
            continue
        match = re.fullmatch(r"(\d{4})/(\d{1,2})", parts[0])
        if not match:
            continue
        year = int(match.group(1))
        month = int(match.group(2))
        if not month_in_range(year, month, start_month, end_month):
            continue
        revenue = parse_int(parts[1])
        if revenue is None:
            continue
        records.append(
            RevenueRecord(
                stock_code=code,
                revenue_year=year,
                revenue_month=month,
                revenue_amount=revenue,
                revenue_unit="thousand_twd",
                source="wantgoo",
                source_url=source_url,
                market_type_at_fetch=meta.market_type,
                company_short_name=meta.short_name,
                company_full_name=meta.full_name,
                fetched_at=fetched_at,
                run_id=run_id,
            )
        )
    return records


def fetch_wantgoo_records(
    *,
    code: str,
    meta: StockMeta,
    start_month: tuple[int, int],
    end_month: tuple[int, int],
    fetched_at: str,
    run_id: str,
) -> tuple[list[RevenueRecord], str | None]:
    """
    Try the non-browser path first. WantGoo may return Cloudflare challenge for
    plain requests; in that case we record a typed blocker and keep FinMind data.
    """
    url = WANTGOO_URL_TEMPLATE.format(code=code)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
    except Exception as exc:
        return [], f"wantgoo_request_error: {type(exc).__name__}: {exc}"
    if resp.status_code == 403 or "Just a moment" in resp.text or "cf-mitigated" in str(resp.headers).lower():
        return [], "wantgoo_cloudflare_challenge"
    if resp.status_code >= 400:
        return [], f"wantgoo_http_{resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")
    table_texts = []
    for table in soup.find_all("table"):
        table_texts.append(table.get_text("\t", strip=True))
    if not table_texts:
        table_texts.append(soup.get_text("\n", strip=True))
    records: list[RevenueRecord] = []
    for table_text in table_texts:
        records.extend(
            parse_wantgoo_table_text(
                text=table_text,
                code=code,
                meta=meta,
                start_month=start_month,
                end_month=end_month,
                fetched_at=fetched_at,
                run_id=run_id,
                source_url=url,
            )
        )
    unique: dict[tuple[int, int], RevenueRecord] = {}
    for record in records:
        unique[(record.revenue_year, record.revenue_month)] = record
    return list(unique.values()), None if unique else "wantgoo_no_rows"


def fetch_mops_market_month_records(
    *,
    year: int,
    month: int,
    market_type: str,
    stock_meta: dict[str, StockMeta],
    fetched_at: str,
    run_id: str,
) -> tuple[list[RevenueRecord], dict[str, Any]]:
    folder = MOPS_MARKET_FOLDERS[market_type]
    source_url = mops_month_source_url(year, month, market_type)
    fallback_source_url = mops_month_source_url(year, month, market_type, fallback=True) if folder == "rotc" else None
    status: dict[str, Any] = {
        "year": year,
        "month": month,
        "market_type": market_type,
        "folder": folder,
        "source_url": source_url,
        "primary_source_url": source_url,
        "fallback_source_url": fallback_source_url,
        "fallback_used": False,
        "raw_row_count": 0,
        "matched_row_count": 0,
        "status": "unknown",
    }
    try:
        rows, source_meta = fetch_mops_source_rows(source_url)
    except Exception as exc:
        status["primary_status"] = "request_error"
        status["primary_error"] = f"{type(exc).__name__}: {exc}"
        if not fallback_source_url:
            status["status"] = "request_error"
            status["error"] = status["primary_error"]
            return [], status
        try:
            rows, source_meta = fetch_mops_source_rows(fallback_source_url)
            source_url = fallback_source_url
            status["source_url"] = fallback_source_url
            status["fallback_used"] = True
        except Exception as fallback_exc:
            status["status"] = "request_error"
            status["fallback_status"] = "request_error"
            status["fallback_error"] = f"{type(fallback_exc).__name__}: {fallback_exc}"
            status["error"] = status["fallback_error"]
            return [], status

    records: list[RevenueRecord] = []
    for row in rows:
        status["raw_row_count"] += 1
        code = (row.get("公司代號") or "").strip()
        if code not in stock_meta:
            continue
        revenue = parse_int(row.get("營業收入-當月營收") or "")
        if revenue is None:
            continue
        meta = stock_meta[code]
        records.append(
            RevenueRecord(
                stock_code=code,
                revenue_year=year,
                revenue_month=month,
                revenue_amount=revenue,
                revenue_unit="thousand_twd",
                source=f"mops_{folder}",
                source_url=source_url,
                market_type_at_fetch=meta.market_type,
                company_short_name=meta.short_name,
                company_full_name=meta.full_name,
                fetched_at=fetched_at,
                run_id=run_id,
            )
        )
    if folder == "rotc" and not records and fallback_source_url and source_url != fallback_source_url:
        status["primary_status"] = "no_matched_records"
        try:
            rows, source_meta = fetch_mops_source_rows(fallback_source_url)
            source_url = fallback_source_url
            status["source_url"] = fallback_source_url
            status["fallback_used"] = True
            status["raw_row_count"] = 0
            records = []
            for row in rows:
                status["raw_row_count"] += 1
                code = (row.get("公司代號") or "").strip()
                if code not in stock_meta:
                    continue
                revenue = parse_int(row.get("營業收入-當月營收") or "")
                if revenue is None:
                    continue
                meta = stock_meta[code]
                records.append(
                    RevenueRecord(
                        stock_code=code,
                        revenue_year=year,
                        revenue_month=month,
                        revenue_amount=revenue,
                        revenue_unit="thousand_twd",
                        source=f"mops_{folder}",
                        source_url=source_url,
                        market_type_at_fetch=meta.market_type,
                        company_short_name=meta.short_name,
                        company_full_name=meta.full_name,
                        fetched_at=fetched_at,
                        run_id=run_id,
                    )
                )
        except Exception as fallback_exc:
            status["fallback_status"] = "request_error"
            status["fallback_error"] = f"{type(fallback_exc).__name__}: {fallback_exc}"
    status.update(source_meta)
    status["matched_row_count"] = len(records)
    if status["raw_row_count"] == 0:
        now = datetime.now()
        status["status"] = "empty_current_month_expected" if (year, month) >= (now.year, now.month) else "empty"
    else:
        status["status"] = "ok"
    return records, status


def selected_best_records(records: list[RevenueRecord]) -> list[RevenueRecord]:
    best: dict[tuple[str, int, int], RevenueRecord] = {}
    for record in records:
        key = (record.stock_code, record.revenue_year, record.revenue_month)
        current = best.get(key)
        if current is None or SOURCE_PRIORITY.get(record.source, 999) < SOURCE_PRIORITY.get(current.source, 999):
            best[key] = record
    return sorted(best.values(), key=lambda r: (r.stock_code, r.revenue_year, r.revenue_month))


def write_outputs(
    *,
    output_dir: Path,
    run_id: str,
    records: list[RevenueRecord],
    receipt: dict[str, Any],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"stock_monthly_revenue_raw_{run_id}.csv"
    receipt_path = output_dir / f"stock_monthly_revenue_raw_receipt_{run_id}.json"
    fieldnames = [
        "stock_code",
        "revenue_year",
        "revenue_month",
        "revenue_amount",
        "revenue_unit",
        "source",
        "source_url",
        "market_type_at_fetch",
        "company_short_name",
        "company_full_name",
        "fetched_at",
        "run_id",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in selected_best_records(records):
            writer.writerow(record.csv_row())
    receipt["csv_path"] = str(csv_path)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return csv_path, receipt_path


def git_commit_and_push(updated_at: str, *, skip_git: bool) -> None:
    if skip_git or os.environ.get("RAW_MONTHLY_REVENUE_SKIP_GIT", "").lower() in {"1", "true", "yes"}:
        print("skip git enabled; stock monthly revenue raw DB was not committed")
        return
    if not (STAGE3_DIR / ".git").exists():
        print(f"inner stage3_web is not a git repo; stock monthly revenue raw DB was not committed: {STAGE3_DIR}")
        return
    subprocess.run(["git", "add", "investment.db"], cwd=STAGE3_DIR, check=True, capture_output=True)
    msg = f"chore: 更新月營收 raw 資料 {updated_at[:10]}"
    result = subprocess.run(["git", "commit", "-m", msg], cwd=STAGE3_DIR, capture_output=True, text=True)
    if result.returncode != 0 and "nothing to commit" in result.stdout + result.stderr:
        print("investment.db unchanged; skip commit")
        return
    result.check_returncode()
    subprocess.run(["git", "push", "origin", "main"], cwd=STAGE3_DIR, check=True, capture_output=True)
    print("git commit + push completed")


def should_skip_git(args: argparse.Namespace) -> bool:
    if args.skip_git:
        return True
    if os.environ.get("RAW_MONTHLY_REVENUE_SKIP_GIT", "").lower() in {"1", "true", "yes"}:
        return True
    return not args.commit_and_push


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch raw stock monthly revenue amounts.")
    parser.add_argument("--codes", default="", help="Comma-separated stock codes. Empty means latest stock_codes CSV all companies.")
    parser.add_argument("--market-types", default="", help="Comma-separated market types, e.g. 上市,上櫃. Empty means no market filter.")
    parser.add_argument("--include-dr", action="store_true", help="Include DR stocks. Default excludes company short names ending with -DR.")
    parser.add_argument("--start-month", default=DEFAULT_START_MONTH, help="Inclusive revenue month, YYYY-MM.")
    parser.add_argument("--end-month", default=DEFAULT_END_MONTH, help="Inclusive revenue month, YYYY-MM.")
    parser.add_argument("--stock-codes-csv", default="", help="Override stock codes CSV path.")
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT), help="Output root for CSV/receipt.")
    parser.add_argument("--db-path", default=str(DB_PATH), help="SQLite DB path.")
    parser.add_argument("--min-months-before-wantgoo", type=int, default=12)
    parser.add_argument("--disable-wantgoo", action="store_true", help="Do not attempt WantGoo fallback.")
    parser.add_argument("--commit-and-push", action="store_true", help="Explicitly commit/push stage3_web/investment.db after updating raw revenue.")
    parser.add_argument("--skip-git", action="store_true", help="Do not commit/push stage3_web/investment.db.")
    parser.add_argument("--missing-only", action="store_true", help="Only fetch companies missing at least one target month in the raw table.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between FinMind company requests.")
    return parser


def parse_codes(value: str) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for raw in value.replace("\n", ",").split(","):
        code = raw.strip()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def parse_market_types(value: str) -> set[str]:
    return {part.strip() for part in value.replace("\n", ",").split(",") if part.strip()}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start_month = parse_month(args.start_month)
    end_month = parse_month(args.end_month)
    if month_key(*end_month) < month_key(*start_month):
        raise ValueError(f"end month {args.end_month} is earlier than start month {args.start_month}")

    run_id = datetime.now().strftime("%Y%m%d")
    fetched_at = datetime.now().isoformat(timespec="seconds")
    requested_codes = parse_codes(args.codes)
    market_types = parse_market_types(args.market_types)
    stock_codes_csv = Path(args.stock_codes_csv) if args.stock_codes_csv else latest_stock_codes_csv(STOCK_CODES_DIR)
    stock_meta = load_stock_codes(
        stock_codes_csv,
        requested_codes or None,
        market_types or None,
        exclude_dr=not args.include_dr,
    )
    db_path = Path(args.db_path)
    if args.missing_only:
        conn = sqlite3.connect(db_path)
        try:
            stock_meta = filter_missing_stock_meta(
                conn,
                stock_meta,
                start_month=start_month,
                end_month=end_month,
            )
        finally:
            conn.close()
    excluded_dr_companies = [] if args.include_dr else list_excluded_dr_stocks(stock_codes_csv, market_types or None)
    mops_meta = {code: meta for code, meta in stock_meta.items() if meta.market_type in MOPS_MARKET_FOLDERS}
    finmind_meta = {code: meta for code, meta in stock_meta.items() if meta.market_type not in MOPS_MARKET_FOLDERS}
    token = load_finmind_token()
    if finmind_meta and not token:
        raise RuntimeError("FINMIND_TOKEN not found")

    output_dir = Path(args.output_root) / run_id
    all_records: list[RevenueRecord] = []
    typed_blockers: list[dict[str, Any]] = []
    per_code: dict[str, Any] = {}
    mops_month_statuses: list[dict[str, Any]] = []
    mops_records_by_code: dict[str, list[RevenueRecord]] = {code: [] for code in mops_meta}

    for current_market_type in sorted({meta.market_type for meta in mops_meta.values()}):
        market_meta = {code: meta for code, meta in mops_meta.items() if meta.market_type == current_market_type}
        for year, month in iter_months(start_month, end_month):
            month_records, month_status = fetch_mops_market_month_records(
                year=year,
                month=month,
                market_type=current_market_type,
                stock_meta=market_meta,
                fetched_at=fetched_at,
                run_id=run_id,
            )
            mops_month_statuses.append(month_status)
            for record in month_records:
                mops_records_by_code.setdefault(record.stock_code, []).append(record)
            if month_status["status"] in {"request_error", "empty"}:
                typed_blockers.append(
                    {
                        "stock_code": None,
                        "finding_type": "mops_month_source_blocker",
                        "plain_description": (
                            f"{year:04d}-{month:02d} {current_market_type} "
                            f"MOPS source status={month_status['status']}"
                        ),
                        "source_url": month_status.get("source_url"),
                        "required_fix": "確認 MOPS 月營收 CSV 是否存在或改用人工核對匯入。",
                    }
                )

    for index, (code, meta) in enumerate(stock_meta.items(), start=1):
        code_records: list[RevenueRecord] = []
        code_blockers: list[str] = []
        finmind_records: list[RevenueRecord] = []
        wantgoo_records: list[RevenueRecord] = []
        if meta.market_type in MOPS_MARKET_FOLDERS:
            code_records.extend(mops_records_by_code.get(code, []))
            finmind_records, finmind_blockers = fetch_finmind_missing_month_records(
                code=code,
                meta=meta,
                current_records=code_records,
                token=token,
                start_month=start_month,
                end_month=end_month,
                fetched_at=fetched_at,
                run_id=run_id,
            )
            code_records.extend(finmind_records)
            code_blockers.extend(finmind_blockers)
        else:
            try:
                finmind_records = fetch_finmind_records(
                    code=code,
                    meta=meta,
                    token=token,
                    start_month=start_month,
                    end_month=end_month,
                    fetched_at=fetched_at,
                    run_id=run_id,
                )
                code_records.extend(finmind_records)
            except Exception as exc:
                finmind_records = []
                code_blockers.append(f"finmind_error: {type(exc).__name__}: {exc}")

        if meta.market_type not in MOPS_MARKET_FOLDERS:
            unique_finmind_months = {(r.revenue_year, r.revenue_month) for r in finmind_records}
        else:
            unique_finmind_months = {(r.revenue_year, r.revenue_month) for r in finmind_records}

        if (
            meta.market_type not in MOPS_MARKET_FOLDERS
            and
            not args.disable_wantgoo
            and len(unique_finmind_months) < args.min_months_before_wantgoo
        ):
            wantgoo_records, wantgoo_blocker = fetch_wantgoo_records(
                code=code,
                meta=meta,
                start_month=start_month,
                end_month=end_month,
                fetched_at=fetched_at,
                run_id=run_id,
            )
            code_records.extend(wantgoo_records)
            if wantgoo_blocker:
                code_blockers.append(wantgoo_blocker)

        all_records.extend(code_records)
        selected = selected_best_records(code_records)
        per_code[code] = {
            "market_type": meta.market_type,
            "company_short_name": meta.short_name,
            "finmind_month_count": len(unique_finmind_months),
            "mops_month_count": len({(r.revenue_year, r.revenue_month) for r in code_records if r.source.startswith("mops_")}),
            "wantgoo_month_count": len({(r.revenue_year, r.revenue_month) for r in wantgoo_records}),
            "selected_month_count": len({(r.revenue_year, r.revenue_month) for r in selected}),
            "first_selected_month": selected[0].period if selected else None,
            "last_selected_month": selected[-1].period if selected else None,
            "blockers": code_blockers,
        }
        for blocker in code_blockers:
            typed_blockers.append(
                {
                    "stock_code": code,
                    "finding_type": "monthly_revenue_raw_source_blocker",
                    "plain_description": blocker,
                    "required_fix": "確認來源可用性；WantGoo 若遇 Cloudflare 需改用 browser-assisted collector 或人工核對匯入。",
                }
            )
        if index % 50 == 0:
            print(f"progress {index}/{len(stock_meta)} records={len(all_records)}")
        time.sleep(args.sleep)

    conn = sqlite3.connect(db_path)
    try:
        ensure_raw_table(conn)
        saved = save_records(conn, all_records)
    finally:
        conn.close()

    receipt = {
        "schema_version": "stock_monthly_revenue_raw_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "start_month": args.start_month,
        "end_month": args.end_month,
        "stock_codes_csv": str(stock_codes_csv),
        "requested_codes": requested_codes,
        "market_types": sorted(market_types),
        "missing_only": args.missing_only,
        "exclude_dr": not args.include_dr,
        "excluded_dr_company_count": len(excluded_dr_companies),
        "excluded_dr_companies": excluded_dr_companies,
        "company_count": len(stock_meta),
        "mops_company_count": len(mops_meta),
        "finmind_fallback_company_count": len(finmind_meta),
        "raw_record_count": len(all_records),
        "saved_record_count": saved,
        "db_path": str(db_path),
        "source_priority": SOURCE_PRIORITY,
        "mops_month_statuses": mops_month_statuses,
        "per_code": per_code,
        "zero_record_company_count": sum(1 for info in per_code.values() if info["selected_month_count"] == 0),
        "zero_record_companies": [
            {"stock_code": code, "market_type": info["market_type"], "company_short_name": info["company_short_name"]}
            for code, info in per_code.items()
            if info["selected_month_count"] == 0
        ],
        "partial_record_company_count": sum(1 for info in per_code.values() if 0 < info["selected_month_count"] < len(iter_months(start_month, end_month)) - 1),
        "typed_blockers": typed_blockers,
        "gate_result": "PASS" if not typed_blockers else "WARN",
    }
    csv_path, receipt_path = write_outputs(
        output_dir=output_dir,
        run_id=run_id,
        records=all_records,
        receipt=receipt,
    )
    print(json.dumps({"csv_path": str(csv_path), "receipt_path": str(receipt_path), "saved": saved}, ensure_ascii=False))
    git_commit_and_push(fetched_at, skip_git=should_skip_git(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
