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
SCRIPT = ROOT / "check_hiring_runtime_governance.py"


class HiringRuntimeGovernanceTests(unittest.TestCase):
    def test_current_folder_governance_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(ROOT),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            receipt = json.loads((output_dir / "hiring_runtime_governance_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["gate_result"], "PASS")
            self.assertFalse(receipt["external_runtime_installed_or_started"])
            self.assertEqual(receipt["scope"], "hiring_demand_folder_only")

    def test_missing_governance_docs_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fixture"
            output_dir = Path(tmp) / "out"
            root.mkdir()
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            receipt = json.loads((output_dir / "hiring_runtime_governance_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["gate_result"], "FAIL")
            self.assertGreater(receipt["typed_blocker_counts"].get("missing_required_file", 0), 0)


if __name__ == "__main__":
    unittest.main()
