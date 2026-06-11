import unittest
from pathlib import Path
from unittest.mock import patch
import sqlite3
import tempfile

import fetch_stock_monthly_revenue_raw as raw

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, text: str, *, status_code: int = 200) -> None:
        self.content = text.encode("utf-8-sig")
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
        return None


class StockMonthlyRevenueRawTests(unittest.TestCase):
    def test_missing_months_for_mops_listed_otc_can_be_filled_by_finmind(self) -> None:
        meta = raw.StockMeta(stock_code="1101", short_name="台泥", market_type="上市")
        mops_record = raw.RevenueRecord(
            stock_code="1101",
            revenue_year=2026,
            revenue_month=3,
            revenue_amount=1000,
            revenue_unit="thousand_twd",
            source="mops_sii",
            source_url="https://mops.example/2026-3.csv",
            market_type_at_fetch="上市",
            company_short_name="台泥",
            company_full_name="",
            fetched_at="2026-05-25T00:00:00",
            run_id="20260525",
        )
        finmind_record = raw.RevenueRecord(
            stock_code="1101",
            revenue_year=2026,
            revenue_month=4,
            revenue_amount=2000,
            revenue_unit="thousand_twd",
            source="finmind",
            source_url=raw.FINMIND_API_URL,
            market_type_at_fetch="上市",
            company_short_name="台泥",
            company_full_name="",
            fetched_at="2026-05-25T00:00:00",
            run_id="20260525",
        )

        with patch("fetch_stock_monthly_revenue_raw.fetch_finmind_records", return_value=[finmind_record]) as mock_fetch:
            fallback_records, blockers = raw.fetch_finmind_missing_month_records(
                code="1101",
                meta=meta,
                current_records=[mops_record],
                token="token",
                start_month=(2026, 3),
                end_month=(2026, 4),
                fetched_at="2026-05-25T00:00:00",
                run_id="20260525",
            )

        self.assertEqual(blockers, [])
        self.assertEqual([(r.revenue_year, r.revenue_month, r.source) for r in fallback_records], [(2026, 4, "finmind")])
        mock_fetch.assert_called_once()

    def test_missing_only_filters_to_codes_without_complete_months(self) -> None:
        stock_meta = {
            "1101": raw.StockMeta(stock_code="1101", market_type="上市"),
            "1102": raw.StockMeta(stock_code="1102", market_type="上市"),
        }
        with tempfile.NamedTemporaryFile(suffix=".db") as db_file:
            conn = sqlite3.connect(db_file.name)
            try:
                raw.ensure_raw_table(conn)
                raw.save_records(
                    conn,
                    [
                        raw.RevenueRecord(
                            stock_code="1101",
                            revenue_year=2026,
                            revenue_month=4,
                            revenue_amount=1000,
                            revenue_unit="thousand_twd",
                            source="mops_sii",
                            source_url="",
                            market_type_at_fetch="上市",
                            company_short_name="",
                            company_full_name="",
                            fetched_at="2026-05-25T00:00:00",
                            run_id="20260525",
                        )
                    ],
                )
                filtered = raw.filter_missing_stock_meta(
                    conn,
                    stock_meta,
                    start_month=(2026, 4),
                    end_month=(2026, 4),
                )
            finally:
                conn.close()

        self.assertEqual(sorted(filtered), ["1102"])

    def test_mops_source_url_uses_csv_as_primary_and_html_as_emerging_fallback(self) -> None:
        self.assertEqual(
            raw.mops_month_source_url(2026, 4, "上市"),
            "https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_4.csv",
        )
        self.assertEqual(
            raw.mops_month_source_url(2026, 4, "上櫃"),
            "https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_115_4.csv",
        )
        self.assertEqual(
            raw.mops_month_source_url(2026, 4, "興櫃"),
            "https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_115_4.csv",
        )
        self.assertEqual(
            raw.mops_month_source_url(2026, 4, "興櫃", fallback=True),
            "https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_115_4_0.html",
        )

    def test_emerging_mops_falls_back_to_html_when_primary_csv_fails(self) -> None:
        html = """
        <html><body>
          <table>
            <tr>
              <th>出表日期</th><th>資料年月</th><th>公司代號</th><th>公司名稱</th>
              <th>產業別</th><th>營業收入-當月營收</th>
            </tr>
            <tr>
              <td>115/05/25</td><td>115/4</td><td>1260</td><td>富味鄉</td>
              <td>食品工業</td><td>4,756</td>
            </tr>
          </table>
        </body></html>
        """
        stock_meta = {
            "1260": raw.StockMeta(
                stock_code="1260",
                short_name="富味鄉",
                full_name="富味鄉食品股份有限公司",
                market_type="興櫃",
            )
        }

        responses = [
            FakeResponse("primary failed", status_code=404),
            FakeResponse(html),
        ]
        with patch("fetch_stock_monthly_revenue_raw.requests.get", side_effect=responses) as mock_get:
            records, status = raw.fetch_mops_market_month_records(
                year=2026,
                month=4,
                market_type="興櫃",
                stock_meta=stock_meta,
                fetched_at="2026-05-25T00:00:00",
                run_id="20260525",
            )

        self.assertEqual(status["source_url"], "https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_115_4_0.html")
        self.assertEqual(status["primary_source_url"], "https://mopsov.twse.com.tw/nas/t21/rotc/t21sc03_115_4.csv")
        self.assertEqual(status["fallback_used"], True)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(status["raw_row_count"], 1)
        self.assertEqual(status["matched_row_count"], 1)
        self.assertEqual(records[0].stock_code, "1260")
        self.assertEqual(records[0].revenue_amount, 4756)
        self.assertEqual(records[0].source, "mops_rotc")

    def test_emerging_mops_html_parser_deduplicates_nested_table_rows(self) -> None:
        row = """
        <tr>
          <td>1260</td><td>富味鄉</td><td>475,612</td><td>466,521</td>
          <td>460,468</td><td>1.94</td><td>3.28</td>
        </tr>
        """
        html = f"""
        <html><body>
          <table>
            <tr><th>公司 代號</th><th>公司名稱</th><th>營業收入-當月營收</th></tr>
            {row}
            {row}
          </table>
        </body></html>
        """
        stock_meta = {"1260": raw.StockMeta(stock_code="1260", short_name="富味鄉", market_type="興櫃")}

        responses = [
            FakeResponse("primary failed", status_code=404),
            FakeResponse(html),
        ]
        with patch("fetch_stock_monthly_revenue_raw.requests.get", side_effect=responses):
            records, status = raw.fetch_mops_market_month_records(
                year=2026,
                month=4,
                market_type="興櫃",
                stock_meta=stock_meta,
                fetched_at="2026-05-25T00:00:00",
                run_id="20260525",
            )

        self.assertEqual(status["raw_row_count"], 1)
        self.assertEqual(status["matched_row_count"], 1)
        self.assertEqual(len(records), 1)

    def test_raw_updater_defaults_to_skip_git_unless_commit_and_push_is_explicit(self) -> None:
        default_args = raw.build_parser().parse_args([])
        self.assertTrue(raw.should_skip_git(default_args))

        commit_args = raw.build_parser().parse_args(["--commit-and-push"])
        self.assertFalse(raw.should_skip_git(commit_args))

        defensive_skip_args = raw.build_parser().parse_args(["--commit-and-push", "--skip-git"])
        self.assertTrue(raw.should_skip_git(defensive_skip_args))

    def test_default_mops_wrapper_does_not_require_finmind_token(self) -> None:
        wrapper_text = (ROOT / "run_stock_monthly_revenue_raw.sh").read_text(encoding="utf-8")

        self.assertIn('RAW_MONTHLY_REVENUE_SKIP_GIT="${RAW_MONTHLY_REVENUE_SKIP_GIT:-1}"', wrapper_text)
        self.assertIn('DEFAULT_END_MONTH="$("$PYTHON" - <<', wrapper_text)
        self.assertIn('END_MONTH="${RAW_REVENUE_END_MONTH:-$DEFAULT_END_MONTH}"', wrapper_text)
        self.assertNotIn('if [ -z "${FINMIND_TOKEN:-}" ]', wrapper_text)
        self.assertNotIn("錯誤: 找不到 FINMIND_TOKEN", wrapper_text)

    def test_wrapper_supports_missing_only_retry_mode(self) -> None:
        wrapper_text = (ROOT / "run_stock_monthly_revenue_raw.sh").read_text(encoding="utf-8")

        self.assertIn('RAW_REVENUE_MISSING_ONLY="${RAW_REVENUE_MISSING_ONLY:-0}"', wrapper_text)
        self.assertIn('if [ "$RAW_REVENUE_MISSING_ONLY" = "1" ]', wrapper_text)
        self.assertIn('--missing-only', wrapper_text)


if __name__ == "__main__":
    unittest.main()
