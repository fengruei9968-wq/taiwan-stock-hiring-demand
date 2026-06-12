#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cleanup_report_artifacts.py"


class CleanupReportArtifactsTests(unittest.TestCase):
    def test_dry_run_writes_review_report_without_moving_or_deleting_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            reports = root / "data" / "reports" / "20260501"
            reports.mkdir(parents=True)
            old_png = reports / "old_summary.png"
            old_pdf = reports / "old_summary.pdf"
            old_png.write_bytes(b"png")
            old_pdf.write_bytes(b"pdf")

            old_time = time.time() - 40 * 24 * 60 * 60
            for path in [old_png, old_pdf]:
                path.touch()
                path.chmod(0o644)
                __import__("os").utime(path, (old_time, old_time))

            out_dir = root / "_test_runtime" / "cleanup_reports"
            archive_root = Path(tmp) / "_archives" / "上市櫃公司徵人需求度"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--archive-root",
                    str(archive_root),
                    "--output-dir",
                    str(out_dir),
                    "--older-than-days",
                    "30",
                ],
                cwd=root,
                text=True,
                capture_output=True,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertTrue(old_png.exists())
            self.assertTrue(old_pdf.exists())
            self.assertFalse((archive_root / "report_artifacts").exists())

            receipt = json.loads((out_dir / "report_artifacts_cleanup_receipt.json").read_text(encoding="utf-8"))
            self.assertTrue(receipt["dry_run_only"])
            self.assertEqual(receipt["candidate_count"], 2)
            self.assertEqual(receipt["action"], "review_required")
            self.assertIn("old_summary.png", (out_dir / "report_artifacts_cleanup_review.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
