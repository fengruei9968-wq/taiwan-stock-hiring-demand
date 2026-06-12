#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import stock_codes_updater as updater


class StockCodesUpdaterTests(unittest.TestCase):
    def test_parse_market_rows_keeps_only_four_digit_codes(self) -> None:
        rows = [
            {"公司代號": "2330", "公司名稱": "台灣積體電路製造股份有限公司", "公司簡稱": "台積電"},
            {"公司代號": "0050", "公司名稱": "元大台灣50", "公司簡稱": "元大台灣50"},
            {"公司代號": "12345", "公司名稱": "五位數權證", "公司簡稱": "權證"},
            {"公司代號": "ABCD", "公司名稱": "非數字", "公司簡稱": "非數字"},
        ]

        parsed = updater.parse_market_rows("上市", rows)

        self.assertEqual([item["股票代碼"] for item in parsed], ["2330", "0050"])
        self.assertEqual(parsed[0]["公司全名"], "台灣積體電路製造股份有限公司")
        self.assertEqual(parsed[0]["市場類別"], "上市")

    def test_write_outputs_to_hiring_data_stock_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "data" / "stock_codes"
            stocks = [
                {"股票代碼": "2330", "公司簡稱": "台積電", "公司全名": "台灣積體電路製造股份有限公司", "市場類別": "上市"},
                {"股票代碼": "2383", "公司簡稱": "台光電", "公司全名": "台光電子材料股份有限公司", "市場類別": "上市"},
            ]

            result = updater.write_stock_code_outputs(stocks, output_dir, "20260612", min_total_companies=2)

            self.assertEqual(result.total_count, 2)
            self.assertTrue(result.is_complete)
            self.assertEqual(result.all_csv.name, "20260612_stock_codes_all.csv")
            self.assertEqual(result.basic_csv.name, "20260612_stock_codes.csv")
            self.assertIn("公司全名", result.all_csv.read_text(encoding="utf-8-sig"))

    def test_main_skips_existing_complete_csv_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "data" / "stock_codes"
            output_dir.mkdir(parents=True)
            existing = output_dir / "20260612_stock_codes_all.csv"
            existing.write_text("股票代碼,公司簡稱,公司全名,市場類別,資料來源,更新時間\n", encoding="utf-8")

            with patch.object(updater, "fetch_all_stocks", side_effect=AssertionError("network fetch called")):
                code = updater.main(["--output-dir", str(output_dir), "--date", "20260612"])

            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
