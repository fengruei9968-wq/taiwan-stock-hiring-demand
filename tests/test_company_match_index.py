#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

import pandas as pd

from fetch_hiring_demand import build_company_match_index, match_company


class CompanyMatchIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stock_df = pd.DataFrame(
            [
                {
                    "股票代碼": "2330",
                    "公司簡稱": "台積電",
                    "公司全名": "台灣積體電路製造股份有限公司",
                    "市場類別": "上市",
                },
                {
                    "股票代碼": "2383",
                    "公司簡稱": "台光電",
                    "公司全名": "台光電子材料股份有限公司",
                    "市場類別": "上市",
                },
            ]
        )

    def test_index_matches_full_short_and_suffix_stripped_names(self) -> None:
        index = build_company_match_index(self.stock_df)

        self.assertEqual(match_company("台灣積體電路製造股份有限公司", self.stock_df, index)["股票代碼"], "2330")
        self.assertEqual(match_company("台積電", self.stock_df, index)["股票代碼"], "2330")
        self.assertEqual(match_company("台灣積體電路製造", self.stock_df, index)["股票代碼"], "2330")

    def test_suffix_stripped_fast_path_does_not_scan_dataframe_rows(self) -> None:
        index = build_company_match_index(self.stock_df)

        with patch.object(pd.DataFrame, "iterrows", side_effect=AssertionError("slow row scan used")):
            matched = match_company("台灣積體電路製造", self.stock_df, index)

        self.assertEqual(matched["股票代碼"], "2330")

    def test_contains_fallback_uses_prebuilt_entries_instead_of_dataframe_scan(self) -> None:
        index = build_company_match_index(self.stock_df)

        with patch.object(pd.DataFrame, "iterrows", side_effect=AssertionError("slow row scan used")):
            matched = match_company("積體電路製造", self.stock_df, index)

        self.assertEqual(matched["股票代碼"], "2330")


if __name__ == "__main__":
    unittest.main()
