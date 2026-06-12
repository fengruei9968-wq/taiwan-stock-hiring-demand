#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Update Taiwan stock-code CSVs for the independent hiring-demand project."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "data" / "stock_codes"
DEFAULT_RECEIPT_DIR = BASE_DIR / "data" / "runs" / "stock_codes_update"
MIN_TOTAL_COMPANIES = 2310
REQUEST_TIMEOUT_SECONDS = 60
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json,text/plain,*/*",
}

API_URLS = {
    "上市": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
    "上櫃": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
    "興櫃": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R",
}

FIELD_MAPPING = {
    "上市": {
        "code": "公司代號",
        "name": "公司名稱",
        "short_name": "公司簡稱",
    },
    "上櫃": {
        "code": "SecuritiesCompanyCode",
        "name": "CompanyName",
        "short_name": "CompanyAbbreviation",
    },
    "興櫃": {
        "code": "SecuritiesCompanyCode",
        "name": "CompanyName",
        "short_name": "CompanyAbbreviation",
    },
}

ALL_FIELDS = ["股票代碼", "公司簡稱", "公司全名", "市場類別", "資料來源", "更新時間"]
BASIC_FIELDS = ["股票代碼", "公司簡稱", "市場類別"]
CHANGE_FIELDS = ["異動類型", "股票代碼", "公司簡稱", "公司全名", "市場類別"]


@dataclass
class StockCodeWriteResult:
    basic_csv: Path
    all_csv: Path
    changes_csv: Path | None
    receipt_json: Path
    total_count: int
    is_complete: bool
    change_count: int


def parse_market_rows(market: str, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    fields = FIELD_MAPPING[market]
    parsed: list[dict[str, str]] = []
    for row in rows:
        code = str(row.get(fields["code"], "")).strip()
        if not (len(code) == 4 and code.isdigit()):
            continue
        parsed.append(
            {
                "股票代碼": code,
                "公司簡稱": str(row.get(fields["short_name"], "")).strip(),
                "公司全名": str(row.get(fields["name"], "")).strip(),
                "市場類別": market,
            }
        )
    return parsed


def fetch_market_stocks(market: str) -> list[dict[str, str]]:
    response = requests.get(
        API_URLS[market],
        headers=REQUEST_HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"{market} API did not return a list")
    return parse_market_rows(market, payload)


def fetch_all_stocks() -> list[dict[str, str]]:
    stocks: list[dict[str, str]] = []
    for market in API_URLS:
        stocks.extend(fetch_market_stocks(market))
    return sorted(stocks, key=lambda item: item["股票代碼"])


def read_stock_csv(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["股票代碼"]: row for row in csv.DictReader(handle)}


def find_latest_complete_csv(output_dir: Path) -> Path | None:
    candidates = sorted(
        path
        for path in output_dir.glob("*_stock_codes_all.csv")
        if "不完整" not in path.name
    )
    return candidates[-1] if candidates else None


def build_changes(stocks: list[dict[str, str]], previous_csv: Path | None) -> list[dict[str, str]]:
    if previous_csv is None:
        return []
    previous = read_stock_csv(previous_csv)
    current = {item["股票代碼"]: item for item in stocks}
    changes: list[dict[str, str]] = []
    for code in sorted(set(previous) - set(current)):
        row = previous[code]
        changes.append(
            {
                "異動類型": "消失",
                "股票代碼": code,
                "公司簡稱": row.get("公司簡稱", ""),
                "公司全名": row.get("公司全名", ""),
                "市場類別": row.get("市場類別", ""),
            }
        )
    for code in sorted(set(current) - set(previous)):
        row = current[code]
        changes.append(
            {
                "異動類型": "新增",
                "股票代碼": code,
                "公司簡稱": row.get("公司簡稱", ""),
                "公司全名": row.get("公司全名", ""),
                "市場類別": row.get("市場類別", ""),
            }
        )
    return changes


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_stock_code_outputs(
    stocks: list[dict[str, str]],
    output_dir: Path,
    date_key: str,
    *,
    min_total_companies: int = MIN_TOTAL_COMPANIES,
    receipt_dir: Path | None = None,
) -> StockCodeWriteResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir = receipt_dir or DEFAULT_RECEIPT_DIR
    receipt_dir.mkdir(parents=True, exist_ok=True)

    total_count = len(stocks)
    is_complete = total_count >= min_total_companies
    suffix = "" if is_complete else "_不完整"
    previous_csv = find_latest_complete_csv(output_dir)
    changes = build_changes(stocks, previous_csv)

    enriched_rows = [
        {
            **item,
            "資料來源": "official_api",
            "更新時間": datetime.strptime(date_key, "%Y%m%d").strftime("%Y-%m-%d"),
        }
        for item in stocks
    ]
    basic_csv = output_dir / f"{date_key}_stock_codes{suffix}.csv"
    all_csv = output_dir / f"{date_key}_stock_codes_all{suffix}.csv"
    write_csv(basic_csv, BASIC_FIELDS, enriched_rows)
    write_csv(all_csv, ALL_FIELDS, enriched_rows)

    changes_csv = None
    if changes:
        changes_csv = output_dir / f"{date_key}_stock_changes.csv"
        write_csv(changes_csv, CHANGE_FIELDS, changes)

    receipt_json = receipt_dir / f"stock_codes_update_receipt_{date_key}.json"
    receipt = {
        "receipt_type": "hiring_stock_codes_update",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "date_key": date_key,
        "output_dir": str(output_dir),
        "basic_csv": str(basic_csv),
        "all_csv": str(all_csv),
        "changes_csv": str(changes_csv) if changes_csv else None,
        "previous_complete_csv": str(previous_csv) if previous_csv else None,
        "total_count": total_count,
        "min_total_companies": min_total_companies,
        "is_complete": is_complete,
        "change_count": len(changes),
        "gate_result": "PASS" if is_complete else "WARN",
    }
    receipt_json.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return StockCodeWriteResult(
        basic_csv=basic_csv,
        all_csv=all_csv,
        changes_csv=changes_csv,
        receipt_json=receipt_json,
        total_count=total_count,
        is_complete=is_complete,
        change_count=len(changes),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update hiring-demand local Stock_codes CSVs from official APIs.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--receipt-dir", default=str(DEFAULT_RECEIPT_DIR))
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--min-total-companies", type=int, default=MIN_TOTAL_COMPANIES)
    parser.add_argument("--force", action="store_true", help="Regenerate even if today's complete CSV already exists.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    receipt_dir = Path(args.receipt_dir).resolve()
    today_complete = output_dir / f"{args.date}_stock_codes_all.csv"
    if today_complete.exists() and not args.force:
        print(json.dumps({"status": "skipped", "reason": "today_complete_exists", "path": str(today_complete)}, ensure_ascii=False))
        return 0

    stocks = fetch_all_stocks()
    result = write_stock_code_outputs(
        stocks,
        output_dir,
        args.date,
        min_total_companies=args.min_total_companies,
        receipt_dir=receipt_dir,
    )
    print(
        json.dumps(
            {
                "status": "updated",
                "total_count": result.total_count,
                "is_complete": result.is_complete,
                "all_csv": str(result.all_csv),
                "receipt_json": str(result.receipt_json),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.is_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
