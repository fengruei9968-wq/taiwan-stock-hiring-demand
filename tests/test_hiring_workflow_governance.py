#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

import fetch_hiring_demand as hiring
import hiring_workflow_governance as workflow_governance


def build_sample_hiring_manifest(tmp_path: Path) -> dict:
    result_df = pd.DataFrame(
        [
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
            }
        ]
    )
    return hiring.build_run_manifest(
        run_id="unit_20260515",
        run_mode="write-db",
        status="success",
        started_at=datetime(2026, 5, 15, 11, 30, 0),
        ended_at=datetime(2026, 5, 15, 11, 35, 0),
        config={
            "search_keywords": ["作業員"],
            "paths": {
                "db_path": str(tmp_path / "investment.db"),
                "output_dir": str(tmp_path / "data"),
            },
        },
        stock_codes_file=tmp_path / "stock_codes.csv",
        all_jobs=[{"linkJobId": "a", "jobName": "作業員"}],
        company_data={"8888": {"total_job_count": 1, "jobs": [{"link_job_id": "a"}]}},
        result_df=result_df,
        csv_path=tmp_path / "data" / "20260515_hiring_demand.csv",
        db_inserted_count=1,
        job_inserted_count=1,
    )


class HiringWorkflowGovernanceTests(unittest.TestCase):
    def test_build_workflow_manifest_maps_hiring_manifest_to_common_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            hiring_manifest = build_sample_hiring_manifest(tmp_path)
            workflow_manifest = workflow_governance.build_workflow_manifest(
                hiring_manifest,
                hiring_manifest_path=tmp_path / "hiring_run_manifest.json",
            )

        self.assertEqual(workflow_manifest["workflow_name"], "hiring_demand_update")
        self.assertEqual(workflow_manifest["run_id"], "unit_20260515")
        self.assertEqual(workflow_manifest["mode"], "write-db")
        self.assertEqual(workflow_manifest["runtime_policy"]["external_runtime_default"], "disabled")
        self.assertFalse(workflow_manifest["runtime_policy"]["external_runtimes"]["opa"]["installed"])
        self.assertEqual(workflow_manifest["source_of_truth"][0]["role"], "active_truth")
        self.assertEqual(workflow_manifest["inputs"][0]["role"], "stock_codes_csv")
        self.assertEqual(workflow_manifest["outputs"][0]["role"], "hiring_demand_csv")
        self.assertIn("missing_trusted_verifier_or_negative_control", workflow_manifest["terminal_blockers"])
        self.assertEqual(workflow_manifest["validation"]["schema_check"], "PENDING_CHECKER")
        self.assertFalse(workflow_manifest["closeout"]["completed"])

    def test_write_workflow_trace_creates_jsonl_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            hiring_manifest = build_sample_hiring_manifest(tmp_path)
            workflow_manifest = workflow_governance.build_workflow_manifest(hiring_manifest)
            trace_path = tmp_path / "workflow_trace.jsonl"
            receipt_path = tmp_path / "workflow_trace_receipt.json"

            receipt = workflow_governance.write_workflow_trace_receipt(
                workflow_manifest,
                trace_path=trace_path,
                receipt_path=receipt_path,
            )

            spans = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(receipt["span_count"], len(workflow_manifest["steps"]))
            self.assertTrue(receipt["contract_id"].startswith("hiring-demand-ai-runtime-governance-v1:"))
            self.assertEqual(spans[0]["trace_id"], receipt["trace_id"])
            self.assertEqual(spans[0]["step_id"], workflow_manifest["steps"][0]["id"])

    def test_write_run_manifest_also_writes_workflow_governance_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            hiring_manifest = build_sample_hiring_manifest(tmp_path)
            manifest_path = hiring.write_run_manifest(hiring_manifest, str(tmp_path / "data"))
            run_root = manifest_path.parent
            runs_dir = run_root.parent

            self.assertTrue((run_root / "workflow_manifest.json").exists())
            self.assertTrue((run_root / "workflow_trace.jsonl").exists())
            self.assertTrue((run_root / "workflow_trace_receipt.json").exists())
            self.assertTrue((runs_dir / "latest_workflow_manifest.json").exists())
            self.assertTrue((runs_dir / "latest_workflow_trace.jsonl").exists())
            self.assertTrue((runs_dir / "latest_workflow_trace_receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
