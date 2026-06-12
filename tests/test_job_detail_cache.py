#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import fetch_hiring_demand as hiring


class JobDetailCacheTests(unittest.TestCase):
    def build_config(self, tmp_path: Path) -> dict:
        return {
            "search_keywords": ["作業員"],
            "job_title_filter_char": "員",
            "exclude_keywords": [],
            "paths": {"output_dir": str(tmp_path / "data")},
            "runtime": {"run_date": "20260612"},
        }

    def build_stock_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "股票代碼": "2383",
                    "公司簡稱": "台光電",
                    "公司全名": "台光電子材料股份有限公司",
                    "市場類別": "上市",
                }
            ]
        )

    def test_cache_hit_does_not_call_job_detail_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.build_config(Path(tmp))
            cache_state = hiring.load_job_detail_cache(config)
            cache_state["records"]["job-a"] = {"need_emp_raw": "2人", "fetched_at": "2026-06-12T00:00:00"}
            hiring.save_job_detail_cache(cache_state)

            cache_state = hiring.load_job_detail_cache(config)
            with patch.object(hiring, "fetch_job_detail_need_emp", side_effect=AssertionError("detail API called")):
                self.assertEqual(hiring.fetch_job_detail_need_emp_cached("job-a", config, cache_state), "2人")

    def test_cache_miss_fetches_and_persists_result_for_next_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.build_config(Path(tmp))
            cache_state = hiring.load_job_detail_cache(config)

            with patch.object(hiring, "fetch_job_detail_need_emp", return_value="3人") as fetch_mock:
                self.assertEqual(hiring.fetch_job_detail_need_emp_cached("job-b", config, cache_state), "3人")
                fetch_mock.assert_called_once_with("job-b", config)

            reloaded_cache = hiring.load_job_detail_cache(config)
            with patch.object(hiring, "fetch_job_detail_need_emp", side_effect=AssertionError("detail API called twice")):
                self.assertEqual(hiring.fetch_job_detail_need_emp_cached("job-b", config, reloaded_cache), "3人")

    def test_refresh_mode_uses_empty_separate_benchmark_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.build_config(Path(tmp))
            cache_state = hiring.load_job_detail_cache(config)
            cache_state["records"]["job-a"] = {"need_emp_raw": "2人", "fetched_at": "2026-06-12T00:00:00"}
            original_cache_path = hiring.save_job_detail_cache(cache_state)

            with patch.dict(
                "os.environ",
                {
                    "HIRING_JOB_DETAIL_CACHE_MODE": "refresh",
                    "HIRING_JOB_DETAIL_CACHE_REFRESH_KEY": "benchmark",
                },
            ):
                refresh_state = hiring.load_job_detail_cache(config)

            self.assertEqual(refresh_state["records"], {})
            self.assertEqual(refresh_state["mode"], "refresh")
            self.assertNotEqual(Path(refresh_state["_path"]), original_cache_path)
            self.assertTrue(str(refresh_state["_path"]).endswith("20260612_refresh_benchmark_need_emp_cache.json"))

    def test_aggregate_company_data_reuses_cached_details_and_fetches_only_missing_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.build_config(Path(tmp))
            cache_state = hiring.load_job_detail_cache(config)
            cache_state["records"]["job-cached"] = {
                "need_emp_raw": "2人",
                "fetched_at": "2026-06-12T00:00:00",
            }
            hiring.save_job_detail_cache(cache_state)

            all_jobs = [
                {
                    "custName": "台光電子材料股份有限公司",
                    "custNo": "cust-2383",
                    "jobName": "作業員",
                    "jobNo": "1",
                    "linkJobId": "job-cached",
                    "employeeCount": 8000,
                },
                {
                    "custName": "台光電子材料股份有限公司",
                    "custNo": "cust-2383",
                    "jobName": "品檢員",
                    "jobNo": "2",
                    "linkJobId": "job-new",
                    "employeeCount": 8000,
                },
            ]

            with patch.object(hiring, "fetch_job_detail_need_emp", return_value="不限") as fetch_mock:
                company_data = hiring.aggregate_company_data(all_jobs, self.build_stock_df(), config)

            fetch_mock.assert_called_once_with("job-new", config)
            self.assertEqual(company_data["2383"]["explicit_need"], 2)
            self.assertEqual(company_data["2383"]["unlimited_job_count"], 1)
            self.assertEqual(company_data["2383"]["total_job_count"], 2)


if __name__ == "__main__":
    unittest.main()
