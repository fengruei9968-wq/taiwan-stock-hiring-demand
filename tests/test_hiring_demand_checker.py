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


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "check_hiring_demand_run.py"
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


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def seed_db(path: Path, demand_rows: list[dict[str, object]], job_rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE hiring_demand (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            company_short_name TEXT NOT NULL,
            company_full_name TEXT,
            market_type TEXT,
            employee_count INTEGER DEFAULT 0,
            explicit_need INTEGER DEFAULT 0,
            unlimited_job_count INTEGER DEFAULT 0,
            unspecified_job_count INTEGER DEFAULT 0,
            total_job_count INTEGER DEFAULT 0,
            demand_ratio REAL DEFAULT 0.0,
            fetch_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, fetch_date)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE hiring_demand_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            job_name TEXT NOT NULL,
            link_job_id TEXT,
            need_emp_raw TEXT,
            need_emp INTEGER DEFAULT 0,
            is_unlimited INTEGER DEFAULT 0,
            is_unspecified INTEGER DEFAULT 0,
            fetch_date TEXT NOT NULL,
            UNIQUE(stock_code, link_job_id, fetch_date)
        )
        """
    )
    for row in demand_rows:
        cur.execute(
            """
            INSERT INTO hiring_demand (
                stock_code, company_short_name, company_full_name, market_type,
                employee_count, explicit_need, unlimited_job_count,
                unspecified_job_count, total_job_count, demand_ratio, fetch_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["股票代碼"],
                row["公司簡稱"],
                row["公司全名"],
                row["市場類別"],
                int(row["員工人數"]),
                int(row["明確需求人數"]),
                int(row["不限職缺數"]),
                int(row["未標示職缺數"]),
                int(row["總職缺數"]),
                float(row["徵人需求度"]),
                row["更新時間"],
            ),
        )
    for row in job_rows:
        cur.execute(
            """
            INSERT INTO hiring_demand_jobs (
                stock_code, job_name, link_job_id, need_emp_raw, need_emp,
                is_unlimited, is_unspecified, fetch_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["stock_code"],
                row["job_name"],
                row["link_job_id"],
                row["need_emp_raw"],
                int(row["need_emp"]),
                int(row["is_unlimited"]),
                int(row["is_unspecified"]),
                row["fetch_date"],
            ),
        )
    conn.commit()
    conn.close()


class HiringDemandCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.csv_path = self.root / "data" / "20260513_hiring_demand.csv"
        self.db_path = self.root / "investment.db"
        self.manifest_path = self.root / "hiring_run_manifest.json"
        self.output_dir = self.root / "out"
        self.rows = [
            {
                "股票代碼": "9999",
                "公司簡稱": "測試",
                "公司全名": "測試股份有限公司",
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
                "股票代碼": "8888",
                "公司簡稱": "不限",
                "公司全名": "不限股份有限公司",
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
        self.job_rows = [
            {
                "stock_code": "9999",
                "job_name": "作業員",
                "link_job_id": "abc",
                "need_emp_raw": "5人",
                "need_emp": 5,
                "is_unlimited": 0,
                "is_unspecified": 0,
                "fetch_date": "2026-05-13",
            },
            {
                "stock_code": "8888",
                "job_name": "包裝員",
                "link_job_id": "def",
                "need_emp_raw": "不限",
                "need_emp": 0,
                "is_unlimited": 1,
                "is_unspecified": 0,
                "fetch_date": "2026-05-13",
            },
        ]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_manifest(self, *, run_mode: str = "write-db", csv_path: Path | None = None) -> None:
        manifest = {
            "schema_version": 1,
            "run_id": "unit_20260513",
            "run_mode": run_mode,
            "status": "success",
            "fetch_date": "2026-05-13",
            "input_stock_codes_file": str(self.root / "stock_codes.csv"),
            "csv_path": str(csv_path or self.csv_path),
            "db_path": str(self.db_path),
            "api_source_summary": {
                "total_jobs": 2,
                "filtered_jobs": 2,
                "matched_jobs": 2,
                "matched_company_count": 2,
                "job_detail_count": 2,
            },
        }
        Path(manifest["input_stock_codes_file"]).write_text("股票代碼,公司簡稱,公司全名,市場類別\n", encoding="utf-8")
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def run_checker(self, *extra: str) -> subprocess.CompletedProcess[str]:
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(self.manifest_path),
            "--output-dir",
            str(self.output_dir),
            *extra,
        ]
        return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)

    def test_valid_csv_db_and_jobs_pass(self) -> None:
        write_csv(self.csv_path, self.rows)
        seed_db(self.db_path, self.rows, self.job_rows)
        self.write_manifest()
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "hiring_run_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["gate_result"], "PASS")
        self.assertTrue(receipt["closeout_allowed"])
        self.assertEqual(receipt["csv_row_count"], 2)
        self.assertEqual(receipt["db_hiring_demand_count"], 2)
        self.assertEqual(receipt["db_hiring_demand_jobs_count"], 2)

    def test_db_row_count_mismatch_fails(self) -> None:
        write_csv(self.csv_path, self.rows)
        seed_db(self.db_path, self.rows[:1], self.job_rows)
        self.write_manifest()
        proc = self.run_checker()
        self.assertNotEqual(proc.returncode, 0)
        receipt = json.loads((self.output_dir / "hiring_run_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["typed_blocker_counts"].get("db_csv_row_count_mismatch"), 1)

    def test_invalid_unlimited_special_value_fails(self) -> None:
        bad_rows = [dict(self.rows[1], 不限職缺數=0)]
        write_csv(self.csv_path, bad_rows)
        seed_db(self.db_path, bad_rows, self.job_rows[:1])
        self.write_manifest()
        proc = self.run_checker()
        self.assertNotEqual(proc.returncode, 0)
        receipt = json.loads((self.output_dir / "hiring_run_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["typed_blocker_counts"].get("invalid_unlimited_ratio"), 1)

    def test_deploy_requires_explicit_deploy_mode(self) -> None:
        write_csv(self.csv_path, self.rows)
        seed_db(self.db_path, self.rows, self.job_rows)
        self.write_manifest(run_mode="write-db")
        proc = self.run_checker("--require-deploy-mode")
        self.assertNotEqual(proc.returncode, 0)
        receipt = json.loads((self.output_dir / "hiring_run_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["typed_blocker_counts"].get("deploy_mode_not_explicit"), 1)

    def test_scrape_only_skips_db_checks_and_never_allows_deploy(self) -> None:
        write_csv(self.csv_path, self.rows)
        self.write_manifest(run_mode="scrape-only")
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "hiring_run_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["gate_result"], "PASS")
        self.assertEqual(receipt["db_check_status"], "skipped_scrape_only")
        self.assertEqual(receipt["db_hiring_demand_count"], 0)
        self.assertFalse(receipt["deploy_allowed"])

    def test_employee_count_unresolved_is_warning_not_blocker(self) -> None:
        warning_rows = [dict(self.rows[0], 員工人數=0, 徵人需求度=0.0)]
        write_csv(self.csv_path, warning_rows)
        seed_db(self.db_path, warning_rows, self.job_rows[:1])
        self.write_manifest()
        proc = self.run_checker()
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        receipt = json.loads((self.output_dir / "hiring_run_check_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["warning_counts"].get("employee_count_unresolved"), 1)


if __name__ == "__main__":
    unittest.main()
