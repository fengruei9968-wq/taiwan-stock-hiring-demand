import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_HIRING_DIR = PROJECT_ROOT / "上市櫃公司徵人需求度"
LEGACY_HIRING_DIR = Path(
    "/Users/chiufengjui/D槽/Python/台股子公司投資資訊擷取與展示/上市櫃公司徵人需求度"
)
STAGE3_DIR = EXPECTED_HIRING_DIR / "stage3_web"


class HiringPipelinePathContractTest(unittest.TestCase):
    def test_hiring_pipeline_lives_under_formal_project(self):
        actual_root = Path(__file__).resolve().parents[1]
        self.assertEqual(actual_root, EXPECTED_HIRING_DIR)
        self.assertEqual(PROJECT_ROOT.name, "台股投資資訊系統_完整專案")

    def test_hiring_local_files_do_not_reference_legacy_directory(self):
        files_to_check = [
            EXPECTED_HIRING_DIR / "config.yaml",
            EXPECTED_HIRING_DIR / "run_hiring_demand.sh",
            EXPECTED_HIRING_DIR / "install_scheduler.sh",
            EXPECTED_HIRING_DIR / "CURRENT_HIRING_DEMAND_EXECUTION.md",
            EXPECTED_HIRING_DIR / "CLAUDE_hiring_demand.md",
            EXPECTED_HIRING_DIR / "generate_unlimited_hiring_revenue_report.py",
        ]

        legacy_text = str(LEGACY_HIRING_DIR)
        offenders = []
        for path in files_to_check:
            if not path.exists():
                offenders.append(f"{path}:missing")
                continue
            if legacy_text in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path))

        self.assertEqual(offenders, [])

    def test_runtime_wrappers_derive_project_root_from_their_own_location(self):
        for filename in [
            "run_hiring_demand.sh",
            "run_telegram_recipient_probe.sh",
            "run_monthly_revenue.sh",
            "run_stock_monthly_revenue_raw.sh",
            "backup_hiring_daily_artifacts.sh",
            "install_scheduler.sh",
        ]:
            text = (EXPECTED_HIRING_DIR / filename).read_text(encoding="utf-8")
            self.assertIn('dirname "${BASH_SOURCE[0]}"', text)
            self.assertIn("HIRING_PROJECT_ROOT", text)

    def test_config_paths_keep_stock_codes_inside_hiring_project(self):
        config = (EXPECTED_HIRING_DIR / "config.yaml").read_text(encoding="utf-8")
        self.assertIn('stock_codes_dir: "data/stock_codes"', config)
        self.assertNotIn("台股上市櫃公司名稱確認與自動定時更新/Stock_codes", config)
        self.assertIn('db_path: "stage3_web/investment.db"', config)
        self.assertIn('output_dir: "data"', config)

        fetcher = (EXPECTED_HIRING_DIR / "fetch_hiring_demand.py").read_text(encoding="utf-8")
        self.assertIn("PROJECT_ROOT = Path(os.environ.get", fetcher)
        self.assertIn("HIRING_DIR = BASE_DIR.resolve()", fetcher)
        self.assertIn("STOCK_CODES_DIR", fetcher)
        self.assertIn("HIRING_OUTPUT_DIR", fetcher)

    def test_fetcher_resolves_relative_db_and_output_paths_from_hiring_dir(self):
        text = (EXPECTED_HIRING_DIR / "fetch_hiring_demand.py").read_text(encoding="utf-8")

        self.assertIn("def _resolve_hiring_path", text)
        self.assertIn("path = HIRING_DIR / path", text)
        self.assertIn("paths['stock_codes_dir'] = _resolve_hiring_path", text)
        self.assertIn("paths['db_path'] = _resolve_hiring_path", text)
        self.assertIn("paths['output_dir'] = _resolve_hiring_path", text)
        self.assertIn("paths.get('stock_codes_dir', 'data/stock_codes')", text)
        self.assertIn("paths.get('db_path', 'stage3_web/investment.db')", text)
        self.assertIn("paths.get('output_dir', 'data')", text)

    def test_config_includes_quality_inspector_and_technician_keywords(self):
        config = (EXPECTED_HIRING_DIR / "config.yaml").read_text(encoding="utf-8")

        self.assertIn('- "品檢員"', config)
        self.assertIn('- "技術士"', config)

    def test_installer_rewrites_plists_to_current_project_root(self):
        text = (EXPECTED_HIRING_DIR / "install_scheduler.sh").read_text(encoding="utf-8")
        self.assertIn("render_plist_template", text)
        self.assertIn("SCHEDULER_TEMPLATE_DIR", text)
        self.assertIn("__HIRING_DIR__", text)
        self.assertIn("__PROJECT_ROOT__", text)
        self.assertIn("--render-only", text)
        self.assertNotIn("CANONICAL_PROJECT_ROOT", text)

    def test_standalone_stage3_web_lives_inside_hiring_project(self):
        app = STAGE3_DIR / "app.py"
        text = app.read_text(encoding="utf-8")
        self.assertIn('@app.route("/hiring-demand")', text)
        self.assertIn('@app.route("/api/hiring-demand")', text)
        self.assertIn("BASE_DIR / \"investment.db\"", text)

    def test_daily_wrapper_renders_media_checks_receipt_syncs_web_and_gates_telegram(self):
        wrapper = EXPECTED_HIRING_DIR / "run_hiring_demand.sh"
        text = wrapper.read_text(encoding="utf-8")

        self.assertIn("render_unlimited_hiring_revenue_media.py", text)
        self.assertIn("--require-media", text)
        self.assertIn("sync_hiring_anomaly_web_artifacts.py", text)
        self.assertIn("HIRING_TELEGRAM_SEND_MODE", text)
        self.assertIn("--send-document", text)
        self.assertIn("--recipients-path", text)
        self.assertIn("telegram_recipients.json", text)
        self.assertIn("徵人需求度每日異常偵測摘要.png", text)
        self.assertIn('--caption ""', text)
        self.assertIn("stage3_web/hiring_reports", text)
        self.assertIn("data/hiring_reports", text)
        self.assertIn("unlimited_hiring_revenue_media_receipt_", text)
        self.assertIn("latest_hiring_demand_web_data.json", (EXPECTED_HIRING_DIR / "sync_hiring_anomaly_web_artifacts.py").read_text(encoding="utf-8"))

    def test_daily_wrapper_deploy_stages_only_hiring_report_artifacts(self):
        wrapper = EXPECTED_HIRING_DIR / "run_hiring_demand.sh"
        text = wrapper.read_text(encoding="utf-8")

        self.assertIn('"$GIT" add stage3_web/hiring_reports stage3_web/data/hiring_reports', text)
        self.assertIn('"$GIT" rev-parse --show-toplevel', text)
        self.assertNotIn('[ ! -d "$STAGE3_DIR/.git" ]', text)
        self.assertNotIn('"$GIT" add investment.db hiring_reports data/hiring_reports', text)
        self.assertIn("grep -Ev '^stage3_web/(hiring_reports/|data/hiring_reports/)'", text)
        self.assertNotIn("grep -Ev '^(investment\\.db|hiring_reports/|data/hiring_reports/)'", text)

    def test_daily_wrapper_auto_remediates_missing_revenue_summary(self):
        wrapper = EXPECTED_HIRING_DIR / "run_hiring_demand.sh"
        text = wrapper.read_text(encoding="utf-8")

        self.assertIn("missing_revenue_summary", text)
        self.assertIn("MISSING_REVENUE_CODES", text)
        self.assertIn("fetch_monthly_revenue.py", text)
        self.assertIn("--codes", text)
        self.assertIn("--skip-git", text)
        self.assertIn("monthly_revenue_backfill_receipt.json", text)
        self.assertIn("report_check_retry_", text)

    def test_monthly_revenue_fetcher_supports_targeted_no_git_backfill(self):
        script = EXPECTED_HIRING_DIR / "fetch_monthly_revenue.py"
        text = script.read_text(encoding="utf-8")

        self.assertIn("parser.add_argument('--codes'", text)
        self.assertIn("parser.add_argument('--skip-git'", text)
        self.assertIn("HIRING_REVENUE_SKIP_GIT", text)
        self.assertIn("monthly_revenue_fetch_receipt", text)
        self.assertIn("monthly_revenue_targeted_fetch_missing_codes", text)

    def test_emerging_revenue_fetcher_supports_no_git_receipt(self):
        script = EXPECTED_HIRING_DIR / "fetch_emerging_revenue.py"
        text = script.read_text(encoding="utf-8")

        self.assertIn("parser.add_argument('--skip-git'", text)
        self.assertIn("parser.add_argument('--output-receipt'", text)
        self.assertIn("HIRING_REVENUE_SKIP_GIT", text)
        self.assertIn("emerging_monthly_revenue_fetch_receipt", text)

    def test_png_metric_card_draws_chinese_unit_with_cjk_font(self):
        renderer = EXPECTED_HIRING_DIR / "render_unlimited_hiring_revenue_media.py"
        text = renderer.read_text(encoding="utf-8")

        self.assertIn('value_parts = value.split(" ", 1)', text)
        self.assertIn("value_parts[1]", text)
        self.assertIn("label_font", text)
        self.assertIn('中文單位', text)

    def test_hourly_telegram_recipient_probe_wrapper_only_updates_recipient_list(self):
        wrapper = EXPECTED_HIRING_DIR / "run_telegram_recipient_probe.sh"
        text = wrapper.read_text(encoding="utf-8")

        self.assertIn("telegram_recipient_probe.py", text)
        self.assertIn("telegram_recipients.json", text)
        self.assertIn("telegram_recipient_probe_receipt_", text)
        self.assertIn("launchd_telegram_probe.log", text)
        self.assertNotIn("TELEGRAM_SCRIPT", text)
        self.assertNotIn('run_python_script "$TELEGRAM_SCRIPT"', text)
        self.assertNotIn("--send-document", text)
        self.assertNotIn("fetch_hiring_demand.py", text)
        self.assertNotIn("render_unlimited_hiring_revenue_media.py", text)

    def test_hourly_telegram_recipient_probe_plist_runs_every_hour(self):
        plist = EXPECTED_HIRING_DIR / "scheduler_templates" / "com.hiring.telegram.recipient.probe.plist.template"
        text = plist.read_text(encoding="utf-8")
        launcher = (EXPECTED_HIRING_DIR / "scheduler_templates" / "run_hiring_demand_launcher.sh.template").read_text(encoding="utf-8")

        self.assertIn("com.hiring.telegram.recipient.probe", text)
        self.assertIn("__LOCAL_LAUNCHER_PATH__", text)
        self.assertIn("run-probe", text)
        self.assertIn("<key>StartInterval</key>", text)
        self.assertIn("<integer>3600</integer>", text)
        self.assertIn("telegram_probe_stdout.log", text)
        self.assertIn("telegram_probe_stderr.log", text)
        self.assertNotIn("run_hiring_demand.sh", text)
        self.assertIn("run_telegram_recipient_probe.sh", launcher)

    def test_stock_codes_updater_has_independent_scheduler_and_output_dir(self):
        plist = EXPECTED_HIRING_DIR / "scheduler_templates" / "com.hiring.stock.codes.updater.plist.template"
        text = plist.read_text(encoding="utf-8")
        launcher = (EXPECTED_HIRING_DIR / "scheduler_templates" / "run_hiring_demand_launcher.sh.template").read_text(encoding="utf-8")
        installer = (EXPECTED_HIRING_DIR / "install_scheduler.sh").read_text(encoding="utf-8")
        wrapper = (EXPECTED_HIRING_DIR / "run_stock_codes_update.sh").read_text(encoding="utf-8")

        self.assertIn("com.hiring.stock.codes.updater", text)
        self.assertIn("__LOCAL_LAUNCHER_PATH__", text)
        self.assertIn("run-stock-codes", text)
        self.assertIn("<integer>5</integer>", text)
        self.assertIn("<integer>0</integer>", text)
        self.assertIn("stock_codes_stdout.log", text)
        self.assertIn("stock_codes_stderr.log", text)
        self.assertIn("run_stock_codes_update.sh", launcher)
        self.assertIn("install-stock-codes", installer)
        self.assertIn("status-stock-codes", installer)
        self.assertIn("run-stock-codes", installer)
        self.assertIn("stock_codes_updater.py", wrapper)
        self.assertIn("data/stock_codes", wrapper)
        self.assertNotIn("com.stock.updater", text)

    def test_raw_monthly_revenue_plists_match_market_schedule(self):
        listed_otc = (EXPECTED_HIRING_DIR / "scheduler_templates" / "com.stock.monthly.revenue.raw.updater.plist.template").read_text(encoding="utf-8")
        emerging = (EXPECTED_HIRING_DIR / "scheduler_templates" / "com.stock.monthly.revenue.raw.emerging.updater.plist.template").read_text(encoding="utf-8")
        missing_retry = (EXPECTED_HIRING_DIR / "scheduler_templates" / "com.stock.monthly.revenue.raw.missing.retry.plist.template").read_text(encoding="utf-8")

        self.assertIn("__LOCAL_LAUNCHER_PATH__", listed_otc)
        self.assertIn("__LOCAL_LAUNCHER_PATH__", emerging)
        self.assertIn("__LOCAL_LAUNCHER_PATH__", missing_retry)
        self.assertIn("run-raw-revenue-listed-otc", listed_otc)
        self.assertIn("run-raw-revenue-emerging", emerging)
        self.assertIn("run-raw-revenue-missing-retry", missing_retry)

        self.assertIn("<integer>5</integer>", listed_otc)
        self.assertIn("<key>RAW_REVENUE_MARKET_TYPES</key>", listed_otc)
        self.assertIn("<string>上市,上櫃</string>", listed_otc)

        self.assertIn("<integer>10</integer>", emerging)
        self.assertIn("<key>RAW_REVENUE_MARKET_TYPES</key>", emerging)
        self.assertIn("<string>興櫃</string>", emerging)

        self.assertIn("<integer>15</integer>", missing_retry)
        self.assertIn("<key>RAW_REVENUE_MARKET_TYPES</key>", missing_retry)
        self.assertIn("<string>上市,上櫃,興櫃</string>", missing_retry)
        self.assertIn("<key>RAW_REVENUE_MISSING_ONLY</key>", missing_retry)
        self.assertIn("<string>1</string>", missing_retry)

    def test_install_scheduler_manages_all_raw_revenue_plists(self):
        text = (EXPECTED_HIRING_DIR / "install_scheduler.sh").read_text(encoding="utf-8")

        self.assertIn("com.stock.monthly.revenue.raw.updater.plist", text)
        self.assertIn("com.stock.monthly.revenue.raw.emerging.updater.plist", text)
        self.assertIn("com.stock.monthly.revenue.raw.missing.retry.plist", text)
        self.assertIn("RAW_REVENUE_PLIST_NAMES", text)
        self.assertIn('${plist_name}.template', text)

    def test_daily_artifact_backup_plist_runs_monthly_on_day_5_at_8pm(self):
        plist = EXPECTED_HIRING_DIR / "scheduler_templates" / "com.hiring.daily.artifacts.backup.plist.template"
        text = plist.read_text(encoding="utf-8")

        self.assertIn("com.hiring.daily.artifacts.backup", text)
        self.assertIn("backup_hiring_daily_artifacts.sh", text)
        self.assertIn("__HIRING_DIR__", text)
        self.assertIn("<key>Day</key>", text)
        self.assertIn("<integer>5</integer>", text)
        self.assertIn("<key>Hour</key>", text)
        self.assertIn("<integer>20</integer>", text)
        self.assertIn("<key>Minute</key>", text)
        self.assertIn("<integer>0</integer>", text)

    def test_scheduler_templates_are_portable_and_raw_plists_are_local_only(self):
        template_dir = EXPECTED_HIRING_DIR / "scheduler_templates"
        templates = sorted(template_dir.glob("com.*.plist.template"))
        self.assertGreaterEqual(len(templates), 7)

        for template in templates:
            text = template.read_text(encoding="utf-8")
            if template.name in {
                "com.hiring.demand.updater.plist.template",
                "com.hiring.telegram.recipient.probe.plist.template",
                "com.hiring.stock.codes.updater.plist.template",
                "com.stock.monthly.revenue.raw.updater.plist.template",
                "com.stock.monthly.revenue.raw.emerging.updater.plist.template",
                "com.stock.monthly.revenue.raw.missing.retry.plist.template",
            }:
                self.assertIn("__LOCAL_LAUNCHER_PATH__", text)
            else:
                self.assertIn("__HIRING_DIR__", text)
            self.assertNotIn("/Users/chiufengjui/D槽", text)
            if template.name != "com.hiring.daily.artifacts.backup.plist.template":
                self.assertNotIn("/Volumes/Extreme SSD", text)

        backup = (template_dir / "com.hiring.daily.artifacts.backup.plist.template").read_text(encoding="utf-8")
        self.assertIn("__ARTIFACT_BACKUP_ROOT__", backup)

        gitignore = (EXPECTED_HIRING_DIR / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("com.*.plist", gitignore)
        self.assertIn("!scheduler_templates/*.plist.template", gitignore)

    def test_daily_artifact_backup_wrapper_is_copy_only(self):
        wrapper = EXPECTED_HIRING_DIR / "backup_hiring_daily_artifacts.sh"
        text = wrapper.read_text(encoding="utf-8")

        self.assertIn("rsync -a", text)
        self.assertIn("delete_source=false", text)
        self.assertIn("move_source=false", text)
        self.assertIn("stage3_web_touched=false", text)
        self.assertNotIn("rm -rf", text)
        self.assertNotIn("mv ", text)

    def test_install_scheduler_manages_daily_artifact_backup(self):
        text = (EXPECTED_HIRING_DIR / "install_scheduler.sh").read_text(encoding="utf-8")

        self.assertIn("com.hiring.daily.artifacts.backup.plist", text)
        self.assertIn("install-artifact-backup", text)
        self.assertIn("status-artifact-backup", text)
        self.assertIn("run-artifact-backup", text)
        self.assertIn("每月 5 號 20:00", text)


if __name__ == "__main__":
    unittest.main()
