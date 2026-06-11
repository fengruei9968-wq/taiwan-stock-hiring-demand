#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fetch_emerging_revenue  # noqa: E402
import fetch_monthly_revenue  # noqa: E402
import fetch_stock_monthly_revenue_raw as raw_revenue  # noqa: E402


class MonthlyRevenueSixMonthTests(unittest.TestCase):
    def test_emerging_mops_rotc_parser_computes_mom_yoy_from_amounts(self) -> None:
        html = """
        <html>
          <head><title>興櫃公司115年4月份(累計與當月)營業收入統計表</title></head>
          <body>
            <table>
              <tr>
                <th>公司 代號</th><th>公司名稱</th><th>當月營收</th><th>上月營收</th>
                <th>去年當月營收</th><th>上月比較 增減(%)</th><th>去年同月 增減(%)</th>
              </tr>
              <tr>
                <td>1260</td><td>富味鄉</td><td>120,000</td><td>100,000</td>
                <td>80,000</td><td>0.00</td><td>0.00</td>
              </tr>
              <tr>
                <td>合計</td><td></td><td>120,000</td><td>100,000</td><td>80,000</td>
              </tr>
            </table>
          </body>
        </html>
        """

        label, data = fetch_emerging_revenue.parse_mops_rotc_page(html.encode("big5"))

        self.assertEqual(label, "2026/4")
        self.assertEqual(data["1260"], {"mom": 20.0, "yoy": 50.0})
        self.assertNotIn("合計", data)

    def test_emerging_mops_rotc_url_uses_twse_rotc_monthly_page(self) -> None:
        url = fetch_emerging_revenue.build_mops_rotc_url(2026, 4)

        self.assertEqual(
            url,
            "https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_115_4_0.html",
        )

    def test_monthly_revenue_mops_fallback_returns_finmind_shaped_records(self) -> None:
        meta = {
            "2211": raw_revenue.StockMeta(
                stock_code="2211",
                short_name="長榮鋼",
                market_type="上市",
            )
        }
        mops_record = raw_revenue.RevenueRecord(
            stock_code="2211",
            revenue_year=2026,
            revenue_month=5,
            revenue_amount=123456,
            revenue_unit="thousand_twd",
            source="mops_sii",
            source_url="https://mops.example/t21sc03_115_5.csv",
            market_type_at_fetch="上市",
            company_short_name="長榮鋼",
            company_full_name="",
            fetched_at="2026-06-12T00:00:00",
            run_id="unit",
        )

        with patch("fetch_stock_monthly_revenue_raw.latest_stock_codes_csv", return_value=Path("stock_codes.csv")), \
             patch("fetch_stock_monthly_revenue_raw.load_stock_codes", return_value=meta), \
             patch("fetch_stock_monthly_revenue_raw.iter_months", return_value=[(2026, 5)]), \
             patch("fetch_stock_monthly_revenue_raw.fetch_mops_market_month_records", return_value=([mops_record], {"status": "ok"})):
            records = fetch_monthly_revenue.fetch_mops_official_revenue(
                requested_codes=["2211"],
                start_month=(2026, 5),
                end_month=(2026, 5),
            )

        self.assertEqual(records, [
            {
                "stock_id": "2211",
                "revenue_year": 2026,
                "revenue_month": 5,
                "revenue": 123456,
            }
        ])

    def test_finmind_summary_outputs_latest_six_months_old_to_new(self) -> None:
        records = []
        for year, month, revenue in [
            (2025, 1, 100.0),
            (2025, 2, 100.0),
            (2025, 3, 100.0),
            (2025, 4, 100.0),
            (2025, 5, 100.0),
            (2025, 6, 100.0),
            (2025, 12, 100.0),
            (2026, 1, 110.0),
            (2026, 2, 121.0),
            (2026, 3, 133.1),
            (2026, 4, 146.41),
            (2026, 5, 161.051),
            (2026, 6, 177.1561),
        ]:
            records.append(
                {
                    "stock_id": "1234",
                    "revenue_year": year,
                    "revenue_month": month,
                    "revenue": revenue,
                }
            )

        summary = fetch_monthly_revenue.compute_summaries(records)["1234"]

        self.assertEqual([summary[f"m{i}"]["label"] for i in range(1, 7)], [
            "2026/1",
            "2026/2",
            "2026/3",
            "2026/4",
            "2026/5",
            "2026/6",
        ])
        self.assertEqual([summary[f"m{i}"]["mom"] for i in range(1, 7)], [10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
        self.assertEqual(summary["m1"]["yoy"], 10.0)
        self.assertEqual(summary["m6"]["yoy"], 77.16)

    def test_ensure_table_migrates_legacy_three_month_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "investment.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE monthly_revenue_summary (
                    stock_code TEXT PRIMARY KEY,
                    m1_label TEXT,
                    m1_mom REAL,
                    m1_yoy REAL,
                    m2_label TEXT,
                    m2_mom REAL,
                    m2_yoy REAL,
                    m3_label TEXT,
                    m3_mom REAL,
                    m3_yoy REAL,
                    updated_at TEXT
                )
                """
            )

            fetch_monthly_revenue.ensure_table(conn)

            columns = {row[1] for row in conn.execute("PRAGMA table_info(monthly_revenue_summary)")}
            conn.close()
        for i in range(1, 7):
            self.assertIn(f"m{i}_label", columns)
            self.assertIn(f"m{i}_mom", columns)
            self.assertIn(f"m{i}_yoy", columns)

    def test_emerging_merge_left_pads_missing_months_and_keeps_latest_six(self) -> None:
        merged = fetch_emerging_revenue.merge_6months(
            None,
            {
                "2026/4": {"mom": 8.6, "yoy": 20.57},
                "2026/5": {"mom": 18.74, "yoy": 10.98},
            },
        )

        self.assertEqual([merged[f"m{i}_label"] for i in range(1, 7)], [
            None,
            None,
            None,
            None,
            "2026/4",
            "2026/5",
        ])
        self.assertEqual(merged["m5_mom"], 8.6)
        self.assertEqual(merged["m6_yoy"], 10.98)

    def test_emerging_merge_overwrites_existing_month_and_drops_oldest(self) -> None:
        existing = {
            "m1_label": "2025/12",
            "m1_mom": -5.0,
            "m1_yoy": -2.0,
            "m2_label": "2026/1",
            "m2_mom": 1.0,
            "m2_yoy": 2.0,
            "m3_label": "2026/2",
            "m3_mom": 3.0,
            "m3_yoy": 4.0,
            "m4_label": "2026/3",
            "m4_mom": 5.0,
            "m4_yoy": 6.0,
            "m5_label": "2026/4",
            "m5_mom": 7.0,
            "m5_yoy": 8.0,
            "m6_label": "2026/5",
            "m6_mom": 9.0,
            "m6_yoy": 10.0,
        }

        merged = fetch_emerging_revenue.merge_6months(
            existing,
            {
                "2026/5": {"mom": 99.0, "yoy": 88.0},
                "2026/6": {"mom": 11.0, "yoy": 12.0},
            },
        )

        self.assertEqual([merged[f"m{i}_label"] for i in range(1, 7)], [
            "2026/1",
            "2026/2",
            "2026/3",
            "2026/4",
            "2026/5",
            "2026/6",
        ])
        self.assertEqual(merged["m5_mom"], 99.0)
        self.assertEqual(merged["m5_yoy"], 88.0)
        self.assertEqual(merged["m6_mom"], 11.0)


if __name__ == "__main__":
    unittest.main()
