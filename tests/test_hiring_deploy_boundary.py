#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "check_hiring_deploy_boundary.py"
DOC = ROOT / "HIRING_DEPLOY_BOUNDARY.md"


class HiringDeployBoundaryTests(unittest.TestCase):
    def test_boundary_doc_defines_source_web_copy_and_forbidden_db(self) -> None:
        text = DOC.read_text(encoding="utf-8")

        self.assertIn("pipeline source of truth", text)
        self.assertIn("stage3_web/hiring_reports", text)
        self.assertIn("stage3_web/data/hiring_reports", text)
        self.assertIn("latest_hiring_demand_web_data.json", text)
        self.assertIn("stage3_web/app.py", text)
        self.assertIn("stage3_web/templates/hiring_demand.html", text)
        self.assertIn("stage3_web/static/css/style.css", text)
        self.assertIn("stage3_web/investment.db", text)
        self.assertIn("forbidden", text)

    def test_boundary_checker_passes_current_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--hiring-dir",
                    str(ROOT),
                    "--stage3-dir",
                    str(ROOT / "stage3_web"),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            receipt = json.loads((output_dir / "hiring_deploy_boundary_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["gate_result"], "PASS")
            self.assertEqual(receipt["deploy_copy_dirs"], ["hiring_reports", "data/hiring_reports"])
            self.assertIn("stage3_web/investment.db", receipt["forbidden_commit_paths"])


if __name__ == "__main__":
    unittest.main()
