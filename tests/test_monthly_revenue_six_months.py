#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fetch_emerging_revenue  # noqa: E402
import fetch_monthly_revenue  # noqa: E402


class MonthlyRevenueSixMonthTests(unittest.TestCase):
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
