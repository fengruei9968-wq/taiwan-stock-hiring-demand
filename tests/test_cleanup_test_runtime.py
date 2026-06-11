#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cleanup_test_runtime.py"


def load_module():
    spec = importlib.util.spec_from_file_location("cleanup_test_runtime", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class CleanupTestRuntimeTests(unittest.TestCase):
    def test_dry_run_reports_old_entries_without_deleting(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "_test_runtime" / "tmp"
            old_dir = target / "old-case"
            old_dir.mkdir(parents=True)
            (old_dir / "fixture.txt").write_text("old", encoding="utf-8")
            old_time = time.time() - (9 * 24 * 60 * 60)
            os.utime(old_dir / "fixture.txt", (old_time, old_time))
            os.utime(old_dir, (old_time, old_time))

            receipt = module.cleanup(root, target, older_than_days=7, delete=False)

            self.assertTrue(old_dir.exists())
            self.assertEqual(receipt["dry_run_only"], True)
            self.assertEqual(receipt["delete_authorized"], False)
            self.assertEqual(receipt["user_confirmation_required"], True)
            self.assertEqual(receipt["candidate_count"], 1)
            self.assertEqual(receipt["deleted_count"], 0)
            self.assertEqual(receipt["candidates"][0]["path"], "_test_runtime/tmp/old-case")

    def test_delete_removes_only_old_entries(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "_test_runtime" / "tmp"
            old_file = target / "old.txt"
            fresh_file = target / "fresh.txt"
            target.mkdir(parents=True)
            old_file.write_text("old", encoding="utf-8")
            fresh_file.write_text("fresh", encoding="utf-8")
            old_time = time.time() - (8 * 24 * 60 * 60)
            os.utime(old_file, (old_time, old_time))

            receipt = module.cleanup(root, target, older_than_days=7, delete=True)

            self.assertFalse(old_file.exists())
            self.assertTrue(fresh_file.exists())
            self.assertEqual(receipt["dry_run_only"], False)
            self.assertEqual(receipt["delete_authorized"], True)
            self.assertEqual(receipt["user_confirmation_required"], False)
            self.assertEqual(receipt["candidate_count"], 1)
            self.assertEqual(receipt["deleted_count"], 1)

    def test_review_file_asks_user_before_delete(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = {
                "dry_run_only": True,
                "delete_authorized": False,
                "user_confirmation_required": True,
                "candidate_count": 1,
                "candidates": [{"path": "_test_runtime/tmp/old-case", "age_days": 8.0}],
                "suggested_delete_command": "venv/bin/python3 cleanup_test_runtime.py --older-than-days 7 --delete",
            }
            review_file = root / "_test_runtime" / "cleanup_review_required.md"

            module.write_review_file(receipt, review_file)

            text = review_file.read_text(encoding="utf-8")
            self.assertIn("需要使用者確認", text)
            self.assertIn("_test_runtime/tmp/old-case", text)
            self.assertIn("--delete", text)

    def test_refuses_target_outside_test_runtime(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "data" / "runs"

            with self.assertRaises(ValueError):
                module.cleanup(root, outside, older_than_days=7, delete=True)


if __name__ == "__main__":
    unittest.main()
