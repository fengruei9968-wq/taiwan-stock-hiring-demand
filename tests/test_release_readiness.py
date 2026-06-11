#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "check_release_readiness.py"

MINIMAL_FIXTURE_FILES = [
    "AGENTS.md",
    "docs/CURRENT_EXECUTION.md",
    "docs/COMMANDS.md",
    "docs/ADR/ADR-001-governance-import-policy.md",
    "manifests/repo_manifest.yaml",
    "manifests/data_contract.yaml",
    "manifests/allowed_entrypoints.yaml",
    "run_tests.sh",
    "install_scheduler.sh",
    "cleanup_test_runtime.py",
    "scheduler_templates/com.hiring.daily.artifacts.backup.plist.template",
    "scheduler_templates/com.hiring.demand.updater.plist.template",
    "scheduler_templates/com.hiring.telegram.recipient.probe.plist.template",
    "scheduler_templates/com.hiring.test-runtime.cleanup.plist.template",
    "scheduler_templates/com.monthly.revenue.updater.plist.template",
    "scheduler_templates/com.stock.monthly.revenue.raw.emerging.updater.plist.template",
    "scheduler_templates/com.stock.monthly.revenue.raw.missing.retry.plist.template",
    "scheduler_templates/com.stock.monthly.revenue.raw.updater.plist.template",
    "tests/test_release_readiness.py",
    "tests/test_cleanup_test_runtime.py",
    "check_hiring_deploy_boundary.py",
    "check_hiring_runtime_governance.py",
    "check_release_readiness.py",
    "stage3_web/app.py",
    "stage3_web/templates/hiring_demand.html",
    "stage3_web/static/css/style.css",
    "stage3_web/Procfile",
    "stage3_web/requirements.txt",
    "stage3_web/hiring_reports/latest_hiring_demand_web_data.json",
    "stage3_web/hiring_reports/latest_hiring_revenue_batch.json",
    "stage3_web/hiring_reports/latest_anomaly_summary.json",
    "stage3_web/hiring_reports/latest_unlimited_hiring_revenue_report_manifest.json",
    "stage3_web/hiring_reports/latest_unlimited_hiring_revenue_media_receipt.json",
]


def build_minimal_fixture(target: Path) -> None:
    for rel_path in MINIMAL_FIXTURE_FILES:
        src = ROOT / rel_path
        dst = target / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


class ReleaseReadinessTests(unittest.TestCase):
    def test_current_folder_release_readiness_has_no_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(ROOT), "--output-dir", str(out)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            receipt = json.loads((out / "hiring_release_readiness_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["gate_result"], "PASS")
            self.assertEqual(receipt["blocker_count"], 0)
            self.assertFalse(receipt["release_commit_authorized"])
            self.assertEqual(receipt["railway_root_directory"], "stage3_web")

    def test_missing_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture"
            build_minimal_fixture(fixture)
            (fixture / "manifests" / "repo_manifest.yaml").unlink()
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(fixture), "--output-dir", str(out)],
                cwd=fixture,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            receipt = json.loads((out / "hiring_release_readiness_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["gate_result"], "FAIL")
            self.assertGreater(receipt["finding_counts"].get("missing_required_file", 0), 0)

    def test_bad_deploy_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture"
            build_minimal_fixture(fixture)
            target = fixture / "stage3_web" / "hiring_reports" / "latest_hiring_demand_web_data.json"
            target.write_text("{not-json", encoding="utf-8")
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(fixture), "--output-dir", str(out)],
                cwd=fixture,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            receipt = json.loads((out / "hiring_release_readiness_receipt.json").read_text(encoding="utf-8"))
            self.assertGreater(receipt["finding_counts"].get("invalid_deploy_json", 0), 0)


if __name__ == "__main__":
    unittest.main()
