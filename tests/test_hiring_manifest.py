#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

import fetch_hiring_demand as hiring


class HiringManifestTests(unittest.TestCase):
    def test_build_run_manifest_records_sources_and_outputs(self) -> None:
        result_df = pd.DataFrame(
            [
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
                }
            ]
        )
        all_jobs = [
            {"linkJobId": "a", "jobName": "作業員"},
            {"linkJobId": "a", "jobName": "作業員"},
            {"linkJobId": "b", "jobName": "工程師"},
        ]
        company_data = {
            "9999": {
                "total_job_count": 1,
                "jobs": [{"link_job_id": "a"}],
            }
        }
        manifest = hiring.build_run_manifest(
            run_id="unit_20260513",
            run_mode="write-db",
            status="success",
            started_at=datetime(2026, 5, 13, 11, 30, 0),
            ended_at=datetime(2026, 5, 13, 11, 35, 0),
            config={
                "search_keywords": ["作業員"],
                "paths": {
                    "db_path": "/tmp/investment.db",
                    "output_dir": "/tmp/out",
                },
            },
            stock_codes_file=Path("/tmp/stock_codes.csv"),
            all_jobs=all_jobs,
            company_data=company_data,
            result_df=result_df,
            csv_path=Path("/tmp/out/20260513_hiring_demand.csv"),
            db_inserted_count=1,
            job_inserted_count=1,
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["run_id"], "unit_20260513")
        self.assertEqual(manifest["run_mode"], "write-db")
        self.assertEqual(manifest["governance_contract_id"], "hiring-demand-ai-runtime-governance-v1")
        self.assertEqual(manifest["fetch_date"], "2026-05-13")
        self.assertEqual(manifest["csv_row_count"], 1)
        self.assertEqual(manifest["db_inserted_count"], 1)
        self.assertEqual(manifest["job_inserted_count"], 1)
        self.assertFalse(manifest["ai_runtime_governance"]["external_runtime_installed_or_started"])
        self.assertEqual(manifest["ai_runtime_governance"]["local_gate"], "check_hiring_demand_run.py")
        self.assertEqual(manifest["lineage"]["inputs"][0]["asset_type"], "stock_codes_csv")
        self.assertEqual(manifest["lineage"]["outputs"][0]["asset_type"], "hiring_demand_csv")
        self.assertIn("hiring_run_check_receipt.json", manifest["lineage"]["expected_receipts"])
        self.assertEqual(manifest["api_source_summary"]["total_jobs"], 3)
        self.assertEqual(manifest["api_source_summary"]["unique_jobs"], 2)
        self.assertEqual(manifest["api_source_summary"]["filtered_jobs"], 2)
        self.assertEqual(manifest["api_source_summary"]["matched_jobs"], 1)
        self.assertEqual(manifest["api_source_summary"]["matched_company_count"], 1)


if __name__ == "__main__":
    unittest.main()
