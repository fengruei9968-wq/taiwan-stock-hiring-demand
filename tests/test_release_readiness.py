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
    "docs/SCHEDULER.md",
    "docs/ADR/ADR-001-governance-import-policy.md",
    "manifests/repo_manifest.yaml",
    "manifests/data_contract.yaml",
    "manifests/allowed_entrypoints.yaml",
    "manifests/scheduler_manifest.yaml",
    "run_tests.sh",
    "install_scheduler.sh",
    "scheduler_requirements.txt",
    "config.yaml",
    "fetch_hiring_demand.py",
    "stock_codes_updater.py",
    "run_stock_codes_update.sh",
    "cleanup_test_runtime.py",
    "cleanup_report_artifacts.py",
    "check_scheduler_installation.py",
    "scheduler_templates/com.hiring.daily.artifacts.backup.plist.template",
    "scheduler_templates/com.hiring.demand.updater.plist.template",
    "scheduler_templates/com.hiring.stock.codes.updater.plist.template",
    "scheduler_templates/com.hiring.telegram.recipient.probe.plist.template",
    "scheduler_templates/com.hiring.test-runtime.cleanup.plist.template",
    "scheduler_templates/com.monthly.revenue.updater.plist.template",
    "scheduler_templates/com.stock.monthly.revenue.raw.emerging.updater.plist.template",
    "scheduler_templates/com.stock.monthly.revenue.raw.missing.retry.plist.template",
    "scheduler_templates/com.stock.monthly.revenue.raw.updater.plist.template",
    "scheduler_templates/run_hiring_demand_launcher.sh.template",
    "tests/test_release_readiness.py",
    "tests/test_cleanup_test_runtime.py",
    "tests/test_cleanup_report_artifacts.py",
    "tests/test_stock_codes_updater.py",
    "tests/test_scheduler_local_runtime.py",
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
    "stage3_web/hiring_reports/latest_hiring_revenue_amounts.json",
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

    def test_job_detail_cache_in_release_candidate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture"
            build_minimal_fixture(fixture)
            subprocess.run(["git", "init"], cwd=fixture, check=True, text=True, capture_output=True)
            cache_path = fixture / "data" / "runs" / "job_detail_cache" / "20260612_need_emp_cache.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text('{"date":"20260612","records":{"abc":{"need_emp_raw":"2人"}}}', encoding="utf-8")
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(fixture), "--output-dir", str(out)],
                cwd=fixture,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            receipt = json.loads((out / "hiring_release_readiness_receipt.json").read_text(encoding="utf-8"))
            self.assertGreater(receipt["finding_counts"].get("runtime_cache_not_ignored", 0), 0)

    def test_png_or_pdf_inside_publish_surface_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture"
            build_minimal_fixture(fixture)
            media_path = fixture / "stage3_web" / "hiring_reports" / "latest_daily_summary.png"
            media_path.write_bytes(b"not-a-real-png")
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(fixture), "--output-dir", str(out)],
                cwd=fixture,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            receipt = json.loads((out / "hiring_release_readiness_receipt.json").read_text(encoding="utf-8"))
            self.assertGreater(receipt["finding_counts"].get("binary_report_artifact_in_publish_surface", 0), 0)

    def test_stock_codes_relative_path_resolving_outside_hiring_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture"
            build_minimal_fixture(fixture)
            fetcher = fixture / "fetch_hiring_demand.py"
            text = fetcher.read_text(encoding="utf-8")
            text = text.replace(
                "paths['stock_codes_dir'] = _resolve_hiring_path(\n        paths.get('stock_codes_dir', 'data/stock_codes'),",
                "paths['stock_codes_dir'] = _resolve_project_path(\n        paths.get('stock_codes_dir', '../台股上市櫃公司名稱確認與自動定時更新/Stock_codes'),",
            )
            fetcher.write_text(text, encoding="utf-8")
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(fixture), "--output-dir", str(out)],
                cwd=fixture,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            receipt = json.loads((out / "hiring_release_readiness_receipt.json").read_text(encoding="utf-8"))
            self.assertGreater(receipt["finding_counts"].get("path_boundary_violation", 0), 0)


if __name__ == "__main__":
    unittest.main()
