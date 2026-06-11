#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import fetch_hiring_demand as hiring
import probe_104_search_api as probe


ROOT = Path(__file__).resolve().parents[1]


class HiringHarnessRuntimeTests(unittest.TestCase):
    def test_probe_classifies_html_403_as_cloudflare_challenge(self) -> None:
        result = probe.classify_response(
            status_code=403,
            content_type="text/html; charset=UTF-8",
            text="<html><title>Just a moment...</title><body>cf-chl Cloudflare</body></html>",
            payload=None,
        )

        self.assertEqual(result["gate_result"], "FAIL")
        self.assertEqual(result["failure_type"], "cloudflare_challenge")
        self.assertEqual(result["recovery_action"], "wait_and_retry")

    def test_probe_classifies_valid_json_with_jobs_as_pass(self) -> None:
        result = probe.classify_response(
            status_code=200,
            content_type="application/json",
            text='{"data":[{"jobName":"作業員"}]}',
            payload={"data": [{"jobName": "作業員"}], "metadata": {"pagination": {"total": 1}}},
        )

        self.assertEqual(result["gate_result"], "PASS")
        self.assertEqual(result["failure_type"], None)
        self.assertEqual(result["recovery_action"], "continue")

    def test_recovery_policy_routes_typed_failures_to_actions(self) -> None:
        policy = json.loads((ROOT / "hiring_recovery_policy.json").read_text(encoding="utf-8"))

        self.assertEqual(policy["http_403"]["action"], "wait_and_retry")
        self.assertEqual(policy["cloudflare_challenge"]["action"], "wait_and_retry")
        self.assertEqual(policy["empty_jobs"]["action"], "keyword_probe_then_retry")
        self.assertEqual(policy["deploy_scope_violation"]["action"], "stop_without_mutating_user_files")

    def test_wrapper_uses_api_probe_recovery_instead_of_ping_gate(self) -> None:
        text = (ROOT / "run_hiring_demand.sh").read_text(encoding="utf-8")

        self.assertIn("probe_104_search_api.py", text)
        self.assertIn("HIRING_104_PROBE_MAX_ATTEMPTS", text)
        self.assertIn("api_probe_receipt", text)
        self.assertNotIn("ping -c 1 -W 5 www.104.com.tw", text)

    def test_employee_count_fallback_uses_search_result_then_google_only(self) -> None:
        with patch.object(hiring, "fetch_employee_count_from_company_api") as company_api, \
             patch.object(hiring, "fetch_employee_count_from_google", return_value=321) as google, \
             patch.object(hiring, "fetch_employee_count_from_mops") as mops:
            count = hiring.get_employee_count(0, "cust123", "測試股份有限公司", "9999", {})

        self.assertEqual(count, 321)
        google.assert_called_once_with("測試股份有限公司")
        company_api.assert_not_called()
        mops.assert_not_called()


if __name__ == "__main__":
    unittest.main()
