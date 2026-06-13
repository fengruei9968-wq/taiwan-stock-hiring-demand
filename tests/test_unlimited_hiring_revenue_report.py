#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GENERATOR = ROOT / "generate_unlimited_hiring_revenue_report.py"
CHECKER = ROOT / "check_unlimited_hiring_revenue_report.py"
RENDERER = ROOT / "render_unlimited_hiring_revenue_media.py"
SYNC_WEB_ARTIFACTS = ROOT / "sync_hiring_anomaly_web_artifacts.py"
from generate_unlimited_hiring_revenue_report import (
    is_current_month_revenue_increase_row,
    is_revenue_growth_row,
    is_revenue_turnaround_row,
    read_hiring_rows,
)
FIELDS = [
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


def write_hiring_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def seed_revenue_db(path: Path, stock_codes: list[str], overrides: dict[str, tuple[float, float, float, float, float, float]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
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
            m4_label TEXT,
            m4_mom REAL,
            m4_yoy REAL,
            m5_label TEXT,
            m5_mom REAL,
            m5_yoy REAL,
            m6_label TEXT,
            m6_mom REAL,
            m6_yoy REAL,
            updated_at TEXT
        )
        """
    )
    overrides = overrides or {}
    for index, code in enumerate(stock_codes, start=1):
        values = overrides.get(
            code,
            (
                3.0 * index,
                30.0 * index,
                2.0 * index,
                20.0 * index,
                1.0 * index,
                10.0 * index,
            ),
        )
        cur.execute(
            """
            INSERT INTO monthly_revenue_summary (
                stock_code, m1_label, m1_mom, m1_yoy,
                m2_label, m2_mom, m2_yoy,
                m3_label, m3_mom, m3_yoy,
                m4_label, m4_mom, m4_yoy,
                m5_label, m5_mom, m5_yoy,
                m6_label, m6_mom, m6_yoy,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                "2025/11",
                -6.0 * index,
                6.0 * index,
                "2025/12",
                -4.0 * index,
                7.0 * index,
                "2026/1",
                -2.0 * index,
                8.0 * index,
                "2026/2",
                values[0],
                values[1],
                "2026/3",
                values[2],
                values[3],
                "2026/4",
                values[4],
                values[5],
                "2026-05-15",
            ),
        )
    conn.commit()
    conn.close()


def seed_hiring_web_data_tables(path: Path) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE hiring_demand (
            stock_code TEXT,
            company_short_name TEXT,
            company_full_name TEXT,
            market_type TEXT,
            employee_count INTEGER,
            explicit_need INTEGER,
            unlimited_job_count INTEGER,
            unspecified_job_count INTEGER,
            total_job_count INTEGER,
            demand_ratio REAL,
            fetch_date TEXT,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE hiring_demand_jobs (
            stock_code TEXT,
            job_name TEXT,
            link_job_id TEXT,
            need_emp_raw TEXT,
            need_emp INTEGER,
            is_unlimited INTEGER,
            is_unspecified INTEGER,
            fetch_date TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO hiring_demand VALUES (
            '4770', '上品', '上品綜合工業股份有限公司', '上市',
            446, 0, 1, 0, 1, 999.0, '2026-05-14', '2026-05-14 04:18:58'
        )
        """
    )
    cur.execute(
        """
        INSERT INTO hiring_demand_jobs VALUES (
            '4770', '機械設備技術員【彰濱廠】', '8ztax', '不限',
            0, 1, 0, '2026-05-14'
        )
        """
    )
    conn.commit()
    conn.close()


def seed_stock_monthly_revenue(path: Path) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE stock_monthly_revenue (
            stock_code TEXT,
            revenue_year INTEGER,
            revenue_month INTEGER,
            revenue_amount INTEGER,
            revenue_unit TEXT,
            source TEXT,
            source_url TEXT,
            market_type_at_fetch TEXT,
            fetched_at TEXT,
            run_id TEXT
        )
        """
    )
    rows = [
        ("3333", 2026, 2, 100000, "thousand_twd", "mops_sii", "https://example.test/3333/202602", "上市", "2026-05-14 01:00:00", "unit"),
        ("3333", 2026, 3, 110000, "thousand_twd", "mops_sii", "https://example.test/3333/202603", "上市", "2026-05-14 01:00:00", "unit"),
        ("3333", 2026, 4, 120000, "thousand_twd", "mops_sii", "https://example.test/3333/202604", "上市", "2026-05-14 01:00:00", "unit"),
        ("4444", 2026, 4, 250000000, "twd", "finmind", "https://example.test/4444/202604", "上櫃", "2026-05-14 01:00:00", "unit"),
    ]
    cur.executemany("INSERT INTO stock_monthly_revenue VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


class UnlimitedHiringRevenueReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_dir = self.root / "data"
        self.output_dir = self.root / "reports"
        self.db_path = self.root / "investment.db"
        previous_rows = [
            {
                "股票代碼": "1111",
                "公司簡稱": "普通",
                "公司全名": "普通股份有限公司",
                "市場類別": "上市",
                "員工人數": 100,
                "明確需求人數": 5,
                "不限職缺數": 0,
                "未標示職缺數": 0,
                "總職缺數": 1,
                "徵人需求度": 5.0,
                "更新時間": "2026-05-13",
            },
            {
                "股票代碼": "2222",
                "公司簡稱": "既有不限",
                "公司全名": "既有不限股份有限公司",
                "市場類別": "上櫃",
                "員工人數": 200,
                "明確需求人數": 0,
                "不限職缺數": 1,
                "未標示職缺數": 0,
                "總職缺數": 1,
                "徵人需求度": 999.0,
                "更新時間": "2026-05-13",
            },
        ]
        latest_rows = [
            previous_rows[0],
            previous_rows[1] | {"更新時間": "2026-05-14"},
            {
                "股票代碼": "3333",
                "公司簡稱": "混合不限",
                "公司全名": "混合不限股份有限公司",
                "市場類別": "上市",
                "員工人數": 1000,
                "明確需求人數": 5,
                "不限職缺數": 1,
                "未標示職缺數": 0,
                "總職缺數": 2,
                "徵人需求度": 0.5,
                "更新時間": "2026-05-14",
            },
            {
                "股票代碼": "4444",
                "公司簡稱": "今日新增",
                "公司全名": "今日新增股份有限公司",
                "市場類別": "上櫃",
                "員工人數": 300,
                "明確需求人數": 0,
                "不限職缺數": 1,
                "未標示職缺數": 0,
                "總職缺數": 1,
                "徵人需求度": 999.0,
                "更新時間": "2026-05-14",
            },
        ]
        write_hiring_csv(self.data_dir / "20260513_hiring_demand.csv", previous_rows)
        write_hiring_csv(self.data_dir / "20260514_hiring_demand.csv", latest_rows)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_generator(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                "--data-dir",
                str(self.data_dir),
                "--db-path",
                str(self.db_path),
                "--output-dir",
                str(self.output_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def run_checker(self, manifest_path: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
        args = [
                sys.executable,
                str(CHECKER),
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(self.output_dir / "check"),
            ]
        if extra_args:
            args.extend(extra_args)
        return subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def run_renderer(self, manifest_path: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
        args = [
            sys.executable,
            str(RENDERER),
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(self.output_dir),
        ]
        if extra_args:
            args.extend(extra_args)
        return subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def test_generator_outputs_only_new_current_month_and_three_month_growth_tables(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (-2.0, -10.0, -1.0, -5.0, 3.0, 30.0),
                "4444": (10.0, 10.0, -1.0, 20.0, 5.0, 30.0),
            },
        )
        proc = self.run_generator()
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)

        manifest = json.loads((self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["unlimited_filter_rule"], "unlimited_job_count_gt_zero")
        self.assertEqual(manifest["latest_unlimited_count"], 3)
        self.assertEqual(manifest["previous_unlimited_count"], 1)
        self.assertEqual(manifest["new_unlimited_count"], 2)
        self.assertEqual(manifest["current_month_revenue_increase_count"], 2)
        self.assertEqual(manifest["revenue_growth_count"], 1)
        self.assertEqual(manifest["revenue_missing_count"], 0)
        self.assertIn("anomaly_summary_json", manifest["outputs"])
        self.assertIn("revenue_snapshot_csv", manifest["outputs"])
        self.assertIn("revenue_snapshot_manifest", manifest["outputs"])

        anomaly_summary = json.loads(Path(manifest["outputs"]["anomaly_summary_json"]).read_text(encoding="utf-8"))
        self.assertEqual(anomaly_summary["summary_type"], "hiring_demand_anomaly_summary")
        self.assertEqual(anomaly_summary["notification_title"], "2026-05-14_異常偵測摘要")
        self.assertTrue(anomaly_summary["alert_required"])
        self.assertEqual(anomaly_summary["alert_policy"]["revenue_change_direction"], "increase_only")
        self.assertEqual(anomaly_summary["events"]["today_new_unlimited"]["count"], 2)
        self.assertEqual(anomaly_summary["events"]["current_month_revenue_increase"]["count"], 2)
        self.assertEqual(anomaly_summary["events"]["three_month_revenue_growth"]["count"], 1)
        self.assertEqual(anomaly_summary["web"]["hiring_demand_url"], "https://financial-report-data-processing.up.railway.app/hiring-demand")

        html = Path(manifest["outputs"]["html_report"]).read_text(encoding="utf-8")
        self.assertIn("今日新增不限徵才", html)
        self.assertIn("營收雙指標改善觀察", html)
        self.assertIn("營收強勢延續公司", html)
        self.assertNotIn("昨日人數不限公司", html)
        self.assertNotIn("全部人數不限公司", html)
        self.assertIn("revenue-bars", html)

        with Path(manifest["outputs"]["new_unlimited_csv"]).open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual({row["股票代碼"] for row in rows}, {"3333", "4444"})
        self.assertTrue(all(row["今日新增公司"] == "YES" for row in rows))

        with Path(manifest["outputs"]["current_month_revenue_increase_csv"]).open(encoding="utf-8-sig", newline="") as handle:
            current_month_rows = list(csv.DictReader(handle))
        self.assertEqual({row["股票代碼"] for row in current_month_rows}, {"3333", "4444"})

        with Path(manifest["outputs"]["revenue_growth_csv"]).open(encoding="utf-8-sig", newline="") as handle:
            growth_rows = list(csv.DictReader(handle))
        self.assertEqual([row["股票代碼"] for row in growth_rows], ["3333"])

        snapshot_csv = Path(manifest["outputs"]["revenue_snapshot_csv"])
        snapshot_manifest_path = Path(manifest["outputs"]["revenue_snapshot_manifest"])
        self.assertEqual(snapshot_csv.parent, self.data_dir / "revenue_snapshots")
        self.assertEqual(snapshot_csv.name, "monthly_revenue_summary_20260514.csv")
        self.assertEqual(snapshot_manifest_path.name, "monthly_revenue_snapshot_manifest_20260514.json")
        with snapshot_csv.open(encoding="utf-8-sig", newline="") as handle:
            snapshot_rows = list(csv.DictReader(handle))
        self.assertEqual({row["stock_code"] for row in snapshot_rows}, {"2222", "3333", "4444"})
        snapshot_manifest = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(snapshot_manifest["artifact_type"], "monthly_revenue_snapshot")
        self.assertEqual(snapshot_manifest["source_table"], "monthly_revenue_summary")
        self.assertEqual(snapshot_manifest["source_db_path"], str(self.db_path))
        self.assertEqual(snapshot_manifest["row_count"], 3)
        self.assertEqual(snapshot_manifest["snapshot_csv_path"], str(snapshot_csv))

    def test_current_month_signal_requires_mom_yoy_growth_and_prior_weakness(self) -> None:
        mom_only = {
            "m4_label": "2026/2",
            "m4_mom": 0.0,
            "m4_yoy": 0.0,
            "m5_label": "2026/3",
            "m5_mom": 1.0,
            "m5_yoy": 20.0,
            "m6_label": "2026/4",
            "m6_mom": 2.0,
            "m6_yoy": 10.0,
        }
        yoy_only = mom_only | {"m6_mom": 0.5, "m6_yoy": 30.0}
        both_latest_month = mom_only | {"m5_yoy": -5.0, "m6_mom": 2.0, "m6_yoy": 30.0}
        both_three_months = mom_only | {"m4_mom": 0.0, "m4_yoy": 5.0, "m5_mom": 1.0, "m5_yoy": 10.0, "m6_mom": 2.0, "m6_yoy": 15.0}
        already_strong_previous_month = mom_only | {
            "m5_mom": 35.33,
            "m5_yoy": 79.14,
            "m6_mom": 46.05,
            "m6_yoy": 172.05,
        }

        self.assertFalse(is_current_month_revenue_increase_row(mom_only))
        self.assertFalse(is_current_month_revenue_increase_row(yoy_only))
        self.assertTrue(is_current_month_revenue_increase_row(both_latest_month))
        self.assertFalse(is_current_month_revenue_increase_row(already_strong_previous_month))
        self.assertFalse(is_revenue_growth_row(mom_only))
        self.assertTrue(is_revenue_growth_row(both_three_months))

    def test_revenue_turnaround_signal_requires_yoy_turn_positive_mom_and_not_current_month_increase(self) -> None:
        turnaround = {
            "m5_label": "2026/3",
            "m5_mom": 9.87,
            "m5_yoy": -0.96,
            "m6_label": "2026/4",
            "m6_mom": 5.01,
            "m6_yoy": 1.65,
        }
        yoy_turn_but_negative_mom = turnaround | {"m6_mom": -1.0}
        already_positive_yoy = turnaround | {"m5_yoy": 0.5}
        also_current_month_increase = turnaround | {"m5_mom": 1.0}

        self.assertTrue(is_revenue_turnaround_row(turnaround))
        self.assertFalse(is_current_month_revenue_increase_row(turnaround))
        self.assertFalse(is_revenue_turnaround_row(yoy_turn_but_negative_mom))
        self.assertFalse(is_revenue_turnaround_row(already_positive_yoy))
        self.assertFalse(is_revenue_turnaround_row(also_current_month_increase))

    def test_generator_outputs_revenue_turnaround_event_without_monthly_new_section(self) -> None:
        monthly_base_rows = [
            {
                "股票代碼": "2222",
                "公司簡稱": "既有不限",
                "公司全名": "既有不限股份有限公司",
                "市場類別": "上櫃",
                "員工人數": 200,
                "明確需求人數": 0,
                "不限職缺數": 1,
                "未標示職缺數": 0,
                "總職缺數": 1,
                "徵人需求度": 999.0,
                "更新時間": "2026-04-30",
            }
        ]
        write_hiring_csv(self.data_dir / "20260430_hiring_demand.csv", monthly_base_rows)
        write_hiring_csv(
            self.data_dir / "20260501_hiring_demand.csv",
            monthly_base_rows
            + [
                {
                    "股票代碼": "5555",
                    "公司簡稱": "月初新增",
                    "公司全名": "月初新增股份有限公司",
                    "市場類別": "上市",
                    "員工人數": 500,
                    "明確需求人數": 0,
                    "不限職缺數": 1,
                    "未標示職缺數": 0,
                    "總職缺數": 1,
                    "徵人需求度": 999.0,
                    "更新時間": "2026-05-01",
                }
            ],
        )
        latest_rows = read_hiring_rows(self.data_dir / "20260514_hiring_demand.csv")
        latest_rows.append(
            {
                "股票代碼": "5555",
                "公司簡稱": "月初新增",
                "公司全名": "月初新增股份有限公司",
                "市場類別": "上市",
                "員工人數": 500,
                "明確需求人數": 0,
                "不限職缺數": 1,
                "未標示職缺數": 0,
                "總職缺數": 1,
                "徵人需求度": 999.0,
                "更新時間": "2026-05-14",
            }
        )
        write_hiring_csv(self.data_dir / "20260514_hiring_demand.csv", latest_rows)
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444", "5555"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
                "5555": (10.0, -20.0, 9.87, -0.96, 5.01, 1.65),
            },
        )

        proc = self.run_generator()
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        manifest = json.loads((self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["revenue_turnaround_count"], 1)
        self.assertNotIn("monthly_new_unlimited_count", manifest)
        self.assertNotIn("monthly_new_unlimited_csv", manifest["outputs"])
        self.assertIn("revenue_turnaround_csv", manifest["outputs"])

        with Path(manifest["outputs"]["revenue_turnaround_csv"]).open(encoding="utf-8-sig", newline="") as handle:
            turnaround_rows = list(csv.DictReader(handle))
        self.assertEqual([row["股票代碼"] for row in turnaround_rows], ["5555"])

        anomaly_summary = json.loads(Path(manifest["outputs"]["anomaly_summary_json"]).read_text(encoding="utf-8"))
        self.assertNotIn("monthly_new_unlimited", anomaly_summary["events"])
        self.assertNotIn("monthly_new_unlimited_count", anomaly_summary["counts"])
        self.assertEqual(
            list(anomaly_summary["events"].keys()),
            ["today_new_unlimited", "revenue_turnaround", "current_month_revenue_increase", "three_month_revenue_growth"],
        )
        self.assertEqual(anomaly_summary["events"]["revenue_turnaround"]["count"], 1)

        html = Path(manifest["outputs"]["html_report"]).read_text(encoding="utf-8")
        self.assertNotIn("本月新增不限人數公司", html)
        self.assertIn("營收轉正觀察", html)

    def test_generator_default_output_updates_reports_level_latest_manifest(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (-2.0, -10.0, -1.0, -5.0, 3.0, 30.0),
                "4444": (10.0, 10.0, -1.0, 20.0, 5.0, 30.0),
            },
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                "--data-dir",
                str(self.data_dir),
                "--db-path",
                str(self.db_path),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)

        latest_manifest_path = self.data_dir / "reports" / "latest_unlimited_hiring_revenue_report_manifest.json"
        self.assertTrue(latest_manifest_path.exists())
        latest_manifest = json.loads(latest_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(latest_manifest["report_yyyymmdd"], "20260514")
        self.assertEqual(latest_manifest["outputs"]["latest_manifest"], str(latest_manifest_path))

    def test_checker_passes_for_complete_report(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (-2.0, -10.0, -1.0, -5.0, 3.0, 30.0),
                "4444": (10.0, 10.0, -1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        proc = self.run_checker(manifest_path)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "check" / "unlimited_hiring_revenue_report_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["gate_result"], "PASS")
        self.assertEqual(receipt["report_date"], "2026-05-14")
        self.assertEqual(receipt["new_unlimited_count"], 2)
        self.assertEqual(receipt["previous_unlimited_count"], 1)
        self.assertEqual(receipt["current_month_revenue_increase_count"], 2)
        self.assertEqual(receipt["revenue_growth_count"], 1)
        self.assertEqual(receipt["revenue_snapshot_row_count"], 3)

    def test_checker_requires_media_receipt_when_enabled(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        missing_proc = self.run_checker(manifest_path, ["--require-media"])
        self.assertNotEqual(missing_proc.returncode, 0)
        missing_receipt = json.loads((self.output_dir / "check" / "unlimited_hiring_revenue_report_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(missing_receipt["typed_blocker_counts"].get("missing_media_receipt"), 1)

        render_proc = self.run_renderer(manifest_path, ["--png-scale", "1.5", "--png-dpi", "150"])
        self.assertEqual(render_proc.returncode, 0, render_proc.stderr + render_proc.stdout)
        pass_proc = self.run_checker(manifest_path, ["--require-media"])
        self.assertEqual(pass_proc.returncode, 0, pass_proc.stderr + pass_proc.stdout)
        pass_receipt = json.loads((self.output_dir / "check" / "unlimited_hiring_revenue_report_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(pass_receipt["gate_result"], "PASS")
        self.assertTrue(pass_receipt["media"]["media_receipt_exists"])
        self.assertTrue(pass_receipt["media"]["png_exists"])
        self.assertTrue(pass_receipt["media"]["pdf_exists"])
        self.assertEqual(pass_receipt["media"]["png_scale"], 1.5)
        self.assertEqual(pass_receipt["media"]["png_dpi"], 150)

    def test_sync_web_artifacts_copies_summary_and_receipts_to_deployable_stage3_dirs(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"
        self.assertEqual(self.run_renderer(manifest_path, ["--png-scale", "1.5", "--png-dpi", "150"]).returncode, 0)
        seed_hiring_web_data_tables(self.db_path)
        seed_stock_monthly_revenue(self.db_path)
        stage3_dir = self.root / "stage3_web"

        proc = subprocess.run(
            [
                sys.executable,
                str(SYNC_WEB_ARTIFACTS),
                "--manifest",
                str(manifest_path),
                "--stage3-dir",
                str(stage3_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        sync_receipt = json.loads(proc.stdout)
        target_dir = stage3_dir / "hiring_reports" / "20260514"
        legacy_target_dir = stage3_dir / "data" / "hiring_reports" / "20260514"
        self.assertEqual(sync_receipt["gate_result"], "PASS")
        self.assertEqual(sync_receipt["target_dir"], str(target_dir))
        self.assertEqual(sync_receipt["target_dirs"]["deploy"], str(target_dir))
        self.assertEqual(sync_receipt["target_dirs"]["legacy_data"], str(legacy_target_dir))
        self.assertTrue((target_dir / "anomaly_summary_20260514.json").exists())
        self.assertTrue((target_dir / "unlimited_hiring_revenue_report_manifest_20260514.json").exists())
        self.assertTrue((target_dir / "unlimited_hiring_revenue_media_receipt_20260514.json").exists())
        self.assertTrue((target_dir / "hiring_anomaly_web_sync_receipt_20260514.json").exists())
        self.assertTrue((target_dir / "hiring_demand_web_data_20260514.json").exists())
        self.assertTrue((stage3_dir / "hiring_reports" / "latest_anomaly_summary.json").exists())
        self.assertTrue((stage3_dir / "hiring_reports" / "latest_unlimited_hiring_revenue_report_manifest.json").exists())
        latest_web_data_path = stage3_dir / "hiring_reports" / "latest_hiring_demand_web_data.json"
        self.assertTrue(latest_web_data_path.exists())
        latest_web_data = json.loads(latest_web_data_path.read_text(encoding="utf-8"))
        self.assertEqual(latest_web_data["counts"]["company_count"], 1)
        self.assertEqual(latest_web_data["data"][0]["stock_code"], "4770")
        self.assertEqual(latest_web_data["jobs_by_stock_code"]["4770"][0]["need_display"], "不限")
        latest_revenue_batch_path = stage3_dir / "hiring_reports" / "latest_hiring_revenue_batch.json"
        self.assertTrue(latest_revenue_batch_path.exists())
        latest_revenue_batch = json.loads(latest_revenue_batch_path.read_text(encoding="utf-8"))
        self.assertEqual(latest_revenue_batch["schema_version"], "hiring_revenue_batch_v1")
        self.assertEqual(latest_revenue_batch["count"], 3)
        self.assertEqual(latest_revenue_batch["data"]["3333"]["months"][-1], "2026/4")
        self.assertEqual(latest_revenue_batch["data"]["3333"]["mom"][-1], 3.0)
        self.assertEqual(latest_revenue_batch["data"]["3333"]["yoy"][-1], 30.0)
        latest_revenue_amounts_path = stage3_dir / "hiring_reports" / "latest_hiring_revenue_amounts.json"
        self.assertTrue(latest_revenue_amounts_path.exists())
        latest_revenue_amounts = json.loads(latest_revenue_amounts_path.read_text(encoding="utf-8"))
        self.assertEqual(latest_revenue_amounts["schema_version"], "hiring_revenue_amounts_v1")
        self.assertEqual(latest_revenue_amounts["count"], 2)
        self.assertEqual(len(latest_revenue_amounts["data"]["3333"]), 3)
        self.assertEqual(latest_revenue_amounts["data"]["3333"][-1]["date"], "2026-04-01")
        self.assertEqual(latest_revenue_amounts["data"]["3333"][-1]["revenue"], 120000000)
        self.assertEqual(latest_revenue_amounts["data"]["4444"][-1]["revenue"], 250000000)
        self.assertTrue((legacy_target_dir / "anomaly_summary_20260514.json").exists())
        self.assertTrue((stage3_dir / "data" / "hiring_reports" / "latest_anomaly_summary.json").exists())
        self.assertTrue((stage3_dir / "data" / "hiring_reports" / "latest_unlimited_hiring_revenue_report_manifest.json").exists())
        self.assertTrue((stage3_dir / "data" / "hiring_reports" / "latest_hiring_demand_web_data.json").exists())
        self.assertTrue((stage3_dir / "data" / "hiring_reports" / "latest_hiring_revenue_batch.json").exists())
        self.assertTrue((stage3_dir / "data" / "hiring_reports" / "latest_hiring_revenue_amounts.json").exists())

    def test_renderer_outputs_anomaly_png_metadata_and_full_current_month_section(self) -> None:
        previous_rows = [
            {
                "股票代碼": "2000",
                "公司簡稱": "既有不限",
                "公司全名": "既有不限股份有限公司",
                "市場類別": "上市",
                "員工人數": 100,
                "明確需求人數": 0,
                "不限職缺數": 1,
                "未標示職缺數": 0,
                "總職缺數": 1,
                "徵人需求度": 999.0,
                "更新時間": "2026-05-13",
            }
        ]
        latest_rows = []
        for index in range(12):
            code = f"30{index:02d}"
            latest_rows.append(
                {
                    "股票代碼": code,
                    "公司簡稱": f"雙增{index + 1:02d}",
                    "公司全名": f"雙增{index + 1:02d}股份有限公司",
                    "市場類別": "上市" if index % 2 == 0 else "上櫃",
                    "員工人數": 500 + index,
                    "明確需求人數": 0,
                    "不限職缺數": 1,
                    "未標示職缺數": 0,
                    "總職缺數": 1,
                    "徵人需求度": 999.0,
                    "更新時間": "2026-05-14",
                }
            )
        write_hiring_csv(self.data_dir / "20260513_hiring_demand.csv", previous_rows)
        write_hiring_csv(self.data_dir / "20260514_hiring_demand.csv", latest_rows)
        seed_revenue_db(
            self.db_path,
            [row["股票代碼"] for row in latest_rows],
            overrides={row["股票代碼"]: (10.0, 10.0, -1.0, 20.0, 5.0, 30.0) for row in latest_rows},
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        proc = self.run_renderer(manifest_path)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "unlimited_hiring_revenue_media_receipt_20260514.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["primary_human_artifact"], "png")
        self.assertEqual(receipt["png_mode"], "anomaly_detection_summary")
        self.assertEqual(receipt["png_footer_text"], "同步更新至徵人需求度網頁")
        self.assertEqual(receipt["revenue_window_months"], 6)
        self.assertEqual(receipt["png_chart_bar_count"], 6)
        self.assertEqual(receipt["pdf_chart_bar_count"], 6)
        self.assertEqual(
            list(receipt["png_sections"].keys()),
            ["today_new_unlimited", "revenue_turnaround", "current_month_revenue_increase", "three_month_revenue_growth"],
        )
        self.assertEqual(receipt["png_sections"]["current_month_revenue_increase"]["total_count"], 12)
        self.assertEqual(receipt["png_sections"]["current_month_revenue_increase"]["displayed_count"], 12)
        self.assertNotIn("monthly_new_unlimited", receipt["png_sections"])
        self.assertEqual(receipt["png_sections"]["revenue_turnaround"]["total_count"], 0)
        self.assertNotIn("PDF/HTML/CSV", receipt["png_footer_text"])

    def test_renderer_can_emit_telegram_high_resolution_png(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        proc = self.run_renderer(manifest_path, ["--png-scale", "2", "--png-dpi", "300"])
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "unlimited_hiring_revenue_media_receipt_20260514.json").read_text(encoding="utf-8"))
        png_path = Path(receipt["png_path"])

        self.assertEqual(receipt["png_scale"], 2)
        self.assertEqual(receipt["png_dpi"], 300)
        self.assertEqual(receipt["png_pixel_width"], 3360)
        self.assertGreater(receipt["png_pixel_height"], 0)
        with Image.open(png_path) as image:
            self.assertEqual(image.size[0], 3360)
            self.assertEqual(image.info.get("dpi"), (299.9994, 299.9994))

    def test_renderer_can_emit_fractional_scale_png_for_telegram_document(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        proc = self.run_renderer(manifest_path, ["--png-scale", "1.5", "--png-dpi", "150"])
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "unlimited_hiring_revenue_media_receipt_20260514.json").read_text(encoding="utf-8"))
        png_path = Path(receipt["png_path"])

        self.assertEqual(receipt["png_scale"], 1.5)
        self.assertEqual(receipt["png_dpi"], 150)
        self.assertEqual(receipt["png_pixel_width"], 2520)
        self.assertGreater(receipt["png_pixel_height"], 0)
        with Image.open(png_path) as image:
            self.assertEqual(image.size[0], 2520)
            self.assertEqual(image.info.get("dpi"), (150.01239999999999, 150.01239999999999))

    def test_renderer_records_png_font_profile_for_ab_test(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        proc = self.run_renderer(
            manifest_path,
            ["--png-scale", "1.5", "--png-dpi", "150", "--png-font-profile", "sf_mixed"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "unlimited_hiring_revenue_media_receipt_20260514.json").read_text(encoding="utf-8"))

        self.assertEqual(receipt["png_font_profile"], "sf_mixed")
        self.assertTrue(receipt["png_fonts"]["chinese"].endswith("STHeiti Medium.ttc"))
        self.assertTrue(receipt["png_fonts"]["latin"].endswith("SFNS.ttf"))
        self.assertTrue(receipt["png_fonts"]["number"].endswith("SFNS.ttf"))
        self.assertEqual(receipt["png_pixel_width"], 2520)

    def test_renderer_uses_chinese_font_for_chart_month_labels_with_sf_profiles(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        proc = self.run_renderer(
            manifest_path,
            ["--png-scale", "1.5", "--png-dpi", "150", "--png-font-profile", "sf_mixed"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "unlimited_hiring_revenue_media_receipt_20260514.json").read_text(encoding="utf-8"))

        self.assertTrue(receipt["png_fonts"]["chart_value"].endswith("SFNS.ttf"))
        self.assertTrue(receipt["png_fonts"]["chart_month"].endswith("STHeiti Medium.ttc"))

    def test_renderer_records_hiragino_mixed_font_profile_for_ab_test(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        proc = self.run_renderer(
            manifest_path,
            ["--png-scale", "1.5", "--png-dpi", "150", "--png-font-profile", "hiragino_mixed"],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "unlimited_hiring_revenue_media_receipt_20260514.json").read_text(encoding="utf-8"))

        self.assertEqual(receipt["png_font_profile"], "hiragino_mixed")
        self.assertTrue(receipt["png_fonts"]["chinese"].endswith("Hiragino Sans GB.ttc"))
        self.assertTrue(receipt["png_fonts"]["chart_month"].endswith("Hiragino Sans GB.ttc"))
        self.assertTrue(receipt["png_fonts"]["latin"].endswith("SFNS.ttf"))
        self.assertTrue(receipt["png_fonts"]["number"].endswith("SFNS.ttf"))

    def test_renderer_default_font_profile_is_hiragino_mixed(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        proc = self.run_renderer(manifest_path, ["--png-scale", "1.5", "--png-dpi", "150"])
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "unlimited_hiring_revenue_media_receipt_20260514.json").read_text(encoding="utf-8"))

        self.assertEqual(receipt["png_font_profile"], "hiragino_mixed")
        self.assertTrue(receipt["png_fonts"]["chinese"].endswith("Hiragino Sans GB.ttc"))
        self.assertTrue(receipt["png_fonts"]["chart_month"].endswith("Hiragino Sans GB.ttc"))

    def test_checker_fails_when_anomaly_summary_count_drifts(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        anomaly_path = Path(manifest["outputs"]["anomaly_summary_json"])
        anomaly_summary = json.loads(anomaly_path.read_text(encoding="utf-8"))
        anomaly_summary["events"]["today_new_unlimited"]["count"] = 999
        anomaly_path.write_text(json.dumps(anomaly_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        proc = self.run_checker(manifest_path)
        self.assertNotEqual(proc.returncode, 0)
        receipt = json.loads((self.output_dir / "check" / "unlimited_hiring_revenue_report_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["typed_blocker_counts"].get("anomaly_summary_count_mismatch"), 1)

    def test_checker_fails_when_revenue_is_missing(self) -> None:
        seed_revenue_db(self.db_path, ["2222", "3333"])
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"

        proc = self.run_checker(manifest_path)
        self.assertNotEqual(proc.returncode, 0)
        receipt = json.loads((self.output_dir / "check" / "unlimited_hiring_revenue_report_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["typed_blocker_counts"].get("missing_revenue_summary"), 1)

    def test_checker_fails_when_revenue_snapshot_drifts_from_db(self) -> None:
        seed_revenue_db(
            self.db_path,
            ["2222", "3333", "4444"],
            overrides={
                "3333": (1.0, 10.0, 2.0, 20.0, 3.0, 30.0),
                "4444": (10.0, 10.0, 1.0, 20.0, 5.0, 30.0),
            },
        )
        self.assertEqual(self.run_generator().returncode, 0)
        manifest_path = self.output_dir / "unlimited_hiring_revenue_report_manifest_20260514.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshot_csv = Path(manifest["outputs"]["revenue_snapshot_csv"])
        with snapshot_csv.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fieldnames = list(reader.fieldnames or [])
        rows[0]["m3_mom"] = "9999.0"
        with snapshot_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        proc = self.run_checker(manifest_path)
        self.assertNotEqual(proc.returncode, 0)
        receipt = json.loads((self.output_dir / "check" / "unlimited_hiring_revenue_report_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["typed_blocker_counts"].get("revenue_snapshot_db_mismatch"), 1)


if __name__ == "__main__":
    unittest.main()
