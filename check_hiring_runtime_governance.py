#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only AI Runtime Governance gate for the hiring-demand folder."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_FILE_MARKERS = {
    ".gitignore": [
        "Governance evidence exceptions",
        "!data/runs/*/workflow_manifest.json",
        "!data/runs/*/workflow_trace_receipt.json",
        "!data/reports/*/unlimited_hiring_revenue_report_manifest_*.json",
        "!data/reports/*/anomaly_summary_*.json",
        "!data/reports/*/unlimited_hiring_revenue_media_receipt_*.json",
        "!data/reports/report_check_*/unlimited_hiring_revenue_report_check_receipt.json",
        "!data/reports/report_media_check_*/unlimited_hiring_revenue_report_check_receipt.json",
        "!data/reports/*/telegram_send_receipt_*.json",
        "Latest runtime pointers are regenerated on every run and stay local-only.",
        "data/runs/latest_workflow_manifest.json",
        "data/runs/latest_workflow_trace.jsonl",
        "data/runs/latest_workflow_trace_receipt.json",
        "data/reports/latest_unlimited_hiring_revenue_report_manifest.json",
        "telegram_recipients.json",
        "!telegram_recipients.example.json",
    ],
    "CURRENT_HIRING_DEMAND_EXECUTION.md": [
        "scrape-only",
        "write-db",
        "deploy",
        "hiring_run_manifest.json",
        "check_hiring_demand_run.py",
        "--require-deploy-mode",
        "tools/create_ascii_handoff.py",
        "營收雙指標改善觀察",
        "營收轉正觀察",
        "營收強勢延續公司",
    ],
    "CLAUDE_hiring_demand.md": [
        "三層治理規則",
        "CURRENT_HIRING_DEMAND_EXECUTION.md",
        "HIRING_DEMAND_PITFALLS.md",
        "check_hiring_demand_run.py",
        "HIRING_DEMAND_DEPLOY_MODE=deploy",
        "../tools/create_ascii_handoff.py",
        "telegram_sender.py",
        "telegram_recipient_probe.py",
        "run_telegram_recipient_probe.sh",
        "com.hiring.telegram.recipient.probe.plist",
    ],
    "fetch_hiring_demand.py": [
        "VALID_RUN_MODES",
        "build_run_manifest",
        "write_run_manifest",
        "write_workflow_governance_artifacts",
        "scrape-only mode",
        "governance_contract_id",
        "Google fallback",
    ],
    "probe_104_search_api.py": [
        "hiring_104_api_probe",
        "classify_response",
        "cloudflare_challenge",
        "non_json_response",
        "empty_jobs",
        "recovery_action",
        "api_probe_receipt",
    ],
    "hiring_recovery_policy.json": [
        "wait_and_retry",
        "keyword_probe_then_retry",
        "stop_without_mutating_user_files",
        "cloudflare_challenge",
        "deploy_scope_violation",
    ],
    "HIRING_DEPLOY_BOUNDARY.md": [
        "pipeline source of truth",
        "stage3_web/hiring_reports",
        "stage3_web/data/hiring_reports",
        "stage3_web/app.py",
        "stage3_web/templates/hiring_demand.html",
        "stage3_web/investment.db",
        "forbidden",
    ],
    "check_hiring_deploy_boundary.py": [
        "hiring_deploy_boundary_check",
        "DEPLOY_COPY_DIRS",
        "FORBIDDEN_COMMIT_PATHS",
        "stage3_dir / \"hiring_reports\"",
        "stage3_dir / \"data\" / \"hiring_reports\"",
        "forbidden_sync_boundary_marker",
    ],
    "hiring_workflow_governance.py": [
        "build_workflow_manifest",
        "write_workflow_trace_receipt",
        "workflow_trace.jsonl",
        "local-jsonl-only",
        "external_runtime_default",
    ],
    "check_hiring_demand_run.py": [
        "EXPECTED_HEADER",
        "validate_special_values",
        "validate_csv_db_alignment",
        "typed_blockers.csv",
        "db_check_status",
        "--require-deploy-mode",
    ],
    "generate_unlimited_hiring_revenue_report.py": [
        "unlimited_job_count_gt_zero",
        "monthly_revenue_summary",
        "unlimited_hiring_revenue_report",
        "new_unlimited_companies",
        "current_month_revenue_increase_companies",
        "revenue_turnaround_companies",
        "current_month_revenue_increase_rule",
        "revenue_turnaround_rule",
        "latest_month_mom_gt_previous_month_mom_and_latest_month_yoy_gt_previous_month_yoy",
        "latest_month_yoy_turns_positive_and_latest_month_mom_positive_excluding_current_month_increase",
        "營收雙指標改善觀察",
        "營收轉正觀察",
        "營收強勢延續公司",
        "anomaly_summary_json",
        "REVENUE_SNAPSHOT_FIELDS",
        "monthly_revenue_snapshot_manifest",
        "revenue_snapshots",
        "HIRING_TELEGRAM_SEND_MODE=enabled",
    ],
    "hiring_anomaly_detector.py": [
        "hiring_demand_anomaly_summary",
        "increase_only",
        "日期_異常偵測摘要",
        "營收雙指標改善觀察",
        "營收轉正觀察",
        "營收強勢延續公司",
        "web_button_implementation_status",
        "implemented_as_structured_summary_modal",
        "https://financial-report-data-processing.up.railway.app/hiring-demand",
    ],
    "telegram_sender.py": [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "recipients_path",
        "recipient_count",
        "TelegramRecipient",
        "telegram_send_authorized",
        "chat_id_masked",
        "sendMessage",
        "sendPhoto",
        "sendDocument",
        "document_path",
        "gate_result",
        "dry_run",
    ],
    "telegram_recipient_probe.py": [
        "extract_start_recipients",
        "upsert_recipients_file",
        "telegram_recipient_list",
        "getUpdates",
        "chat_id_masked",
        "dry_run",
    ],
    "run_telegram_recipient_probe.sh": [
        "telegram_recipient_probe.py",
        "telegram_recipients.json",
        "telegram_recipient_probe_receipt_",
        "launchd_telegram_probe.log",
        "不發 PNG",
        "不部署",
    ],
    "com.hiring.telegram.recipient.probe.plist": [
        "com.hiring.telegram.recipient.probe",
        "run_telegram_recipient_probe.sh",
        "StartInterval",
        "<integer>3600</integer>",
        "launchd_telegram_probe_stdout.log",
        "launchd_telegram_probe_stderr.log",
    ],
    "telegram_recipients.example.json": [
        "telegram_recipient_list",
        "friend_example",
        "chat_id",
        "enabled",
    ],
    "HIRING_DEMAND_PITFALLS.md": [
        "Telegram token / chat_id 遮罩",
        "sanitize_text()",
        "chat_id_masked",
        "test_sanitize_text_does_not_corrupt_text_when_chat_id_is_empty",
        "telegram_recipients.json",
        "governance checker",
    ],
    "check_unlimited_hiring_revenue_report.py": [
        "missing_revenue_summary",
        "new_unlimited_companies_mismatch",
        "current_month_revenue_increase_companies_mismatch",
        "revenue_turnaround_companies_mismatch",
        "營收雙指標改善觀察",
        "營收轉正觀察",
        "營收強勢延續公司",
        "anomaly_summary_count_mismatch",
        "revenue_snapshot_db_mismatch",
        "revenue_snapshot_row_count_mismatch",
        "unlimited_hiring_revenue_report_check_receipt.json",
        "--require-media",
        "missing_media_receipt",
        "media_receipt_manifest_mismatch",
        "telegram_sent",
    ],
    "render_unlimited_hiring_revenue_media.py": [
        "PNG_MODE",
        "anomaly_detection_summary",
        "PNG_FOOTER_TEXT",
        "同步更新至徵人需求度網頁",
        "build_png_section_metadata",
        "PNG_FONT_PROFILES",
        'PNG_FONT_PROFILE_DEFAULT = "hiragino_mixed"',
        "png_font_profile",
        "png_fonts",
        "chart_month",
        "chart_value",
        "sf_mixed",
        "sf_mono_numbers",
        "hiragino_mixed",
        "png_scale",
        "png_dpi",
        "png_pixel_width",
        "png_pixel_height",
        "current_month_revenue_increase",
        "revenue_turnaround",
        "營收雙指標改善觀察",
        "營收轉正觀察",
        "營收強勢延續公司",
    ],
    "run_hiring_demand.sh": [
        "PROBE_SCRIPT",
        "probe_104_search_api.py",
        "HIRING_104_PROBE_MAX_ATTEMPTS",
        "api_probe_receipt",
        "CHECKER_SCRIPT",
        "REPORT_SCRIPT",
        "REPORT_CHECKER_SCRIPT",
        "REPORT_RENDER_SCRIPT",
        "WEB_SYNC_SCRIPT",
        "TELEGRAM_SCRIPT",
        "HIRING_DEMAND_DEPLOY_MODE",
        "HIRING_TELEGRAM_SEND_MODE",
        "render_unlimited_hiring_revenue_media.py",
        "sync_hiring_anomaly_web_artifacts.py",
        "--require-media",
        "--send-document",
        "--recipients-path",
        "telegram_recipients.json",
        "徵人需求度每日異常偵測摘要.png",
        '--caption ""',
        "stage3_web/hiring_reports",
        "data/hiring_reports",
        "--require-deploy-mode",
        '"$GIT" add stage3_web/hiring_reports stage3_web/data/hiring_reports',
    ],
    "install_scheduler.sh": [
        "install-probe",
        "uninstall-probe",
        "status-probe",
        "run-probe",
        "com.hiring.telegram.recipient.probe.plist",
        "每 1 小時",
    ],
    "sync_hiring_anomaly_web_artifacts.py": [
        "hiring_anomaly_web_artifact_sync",
        "stage3_web",
        "deploy",
        "data",
        "hiring_reports",
        "latest_anomaly_summary.json",
        "latest_unlimited_hiring_revenue_report_manifest.json",
        "latest_unlimited_hiring_revenue_media_receipt.json",
    ],
    "docs/ai_runtime_governance/governance_reference_mapping.md": [
        "不安裝",
        "OPA",
        "Temporal",
        "Langfuse",
        "OpenTelemetry",
    ],
    "docs/ai_runtime_governance/workflow_three_layer_architecture.md": [
        "第一層",
        "第二層",
        "第三層",
        "positive control",
        "negative controls",
    ],
    "docs/ai_runtime_governance/workflow_closed_loop_plan.md": [
        "閉回路",
        "必停條件",
        "PASS",
        "FAIL",
        "WARN",
    ],
    "docs/ai_runtime_governance/workflow_hardening_checklist.md": [
        "已落地",
        "尚未落地",
        "runtime governance checker",
        "external runtime install",
    ],
    "docs/ai_runtime_governance/proposed_file_change_list.md": [
        "本輪變更只限徵人需求度資料夾",
        "check_hiring_runtime_governance.py",
        "不修改 stage0",
        "不安裝、不啟動外部 runtime",
    ],
    "tests/test_hiring_demand_checker.py": [
        "test_valid_csv_db_and_jobs_pass",
        "test_db_row_count_mismatch_fails",
        "test_invalid_unlimited_special_value_fails",
        "test_deploy_requires_explicit_deploy_mode",
        "test_scrape_only_skips_db_checks_and_never_allows_deploy",
    ],
    "tests/test_hiring_manifest.py": [
        "test_build_run_manifest_records_sources_and_outputs",
        "governance_contract_id",
        "lineage",
    ],
    "tests/test_hiring_workflow_governance.py": [
        "test_build_workflow_manifest_maps_hiring_manifest_to_common_fields",
        "test_write_workflow_trace_creates_jsonl_and_receipt",
        "test_write_run_manifest_also_writes_workflow_governance_artifacts",
    ],
    "tests/test_hiring_harness_runtime.py": [
        "test_probe_classifies_html_403_as_cloudflare_challenge",
        "test_recovery_policy_routes_typed_failures_to_actions",
        "test_wrapper_uses_api_probe_recovery_instead_of_ping_gate",
        "test_employee_count_fallback_uses_search_result_then_google_only",
    ],
    "tests/test_hiring_deploy_boundary.py": [
        "test_boundary_doc_defines_source_web_copy_and_forbidden_db",
        "test_boundary_checker_passes_current_layout",
        "stage3_web/investment.db",
    ],
    "tests/test_unlimited_hiring_revenue_report.py": [
        "test_generator_outputs_only_new_current_month_and_three_month_growth_tables",
        "test_current_month_signal_requires_mom_and_yoy_growth",
        "test_generator_outputs_revenue_turnaround_event_without_monthly_new_section",
        "test_revenue_turnaround_signal_requires_yoy_turn_positive_mom_and_not_current_month_increase",
        "test_renderer_outputs_anomaly_png_metadata_and_full_current_month_section",
        "test_renderer_can_emit_telegram_high_resolution_png",
        "test_renderer_records_png_font_profile_for_ab_test",
        "test_renderer_uses_chinese_font_for_chart_month_labels_with_sf_profiles",
        "test_renderer_records_hiragino_mixed_font_profile_for_ab_test",
        "test_renderer_default_font_profile_is_hiragino_mixed",
        "test_checker_fails_when_revenue_snapshot_drifts_from_db",
        "test_checker_fails_when_anomaly_summary_count_drifts",
        "test_checker_passes_for_complete_report",
        "test_checker_requires_media_receipt_when_enabled",
        "test_sync_web_artifacts_copies_summary_and_receipts_to_deployable_stage3_dirs",
        "test_checker_fails_when_revenue_is_missing",
        "anomaly_summary_json",
        "revenue_snapshot_csv",
        "revenue_snapshot_row_count",
        "current_month_revenue_increase_count",
        "revenue_turnaround_count",
        "revenue_growth_count",
        "png_mode",
        "png_scale",
        "png_dpi",
        "missing_media_receipt",
        "revenue-bars",
    ],
    "tests/test_telegram_sender.py": [
        "test_load_env_masks_chat_id_without_exposing_token",
        "test_sanitize_text_does_not_corrupt_text_when_chat_id_is_empty",
        "test_send_message_and_photo_write_success_receipt",
        "test_send_document_writes_success_receipt",
        "test_send_document_fans_out_to_enabled_recipients",
        "test_dry_run_loads_env_and_document_without_sending_network_request",
        "SECRET",
        "chat_id_masked",
    ],
    "tests/test_telegram_recipient_probe.py": [
        "test_extract_start_recipients_from_updates",
        "test_upsert_recipients_file_preserves_existing_and_dedupes_chat_id",
        "telegram_recipient_probe",
    ],
    "tests/test_hiring_pipeline_path_contract.py": [
        "test_hourly_telegram_recipient_probe_wrapper_only_updates_recipient_list",
        "test_hourly_telegram_recipient_probe_plist_runs_every_hour",
        "StartInterval",
        "3600",
    ],
    "tests/test_hiring_runtime_governance.py": [
        "test_current_folder_governance_passes",
        "test_missing_governance_docs_fail",
    ],
}


REQUIRED_PROJECT_FILE_MARKERS = {
    "../tools/create_ascii_handoff.py": [
        "Create short ASCII copies",
        "--prefix",
        "markdown_link",
        "handoff_path",
    ],
}


@dataclass
class Finding:
    finding_type: str
    plain_description: str
    affected_file: str
    affected_key: str
    required_fix: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def check_required_markers(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for rel_path, markers in REQUIRED_FILE_MARKERS.items():
        path = root / rel_path
        if not path.exists():
            findings.append(
                Finding(
                    "missing_required_file",
                    "三層治理必要檔案不存在。",
                    str(path),
                    rel_path,
                    "在徵人需求度資料夾內補上該檔案，不要改其他專案。",
                )
            )
            continue
        text = read_text(path)
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "missing_required_marker",
                        f"檔案缺少必要治理標記: {marker}",
                        str(path),
                        marker,
                        "補齊文件、checker、manifest 或 test 的對應規則後重跑本 checker。",
                    )
                )
    for rel_path, markers in REQUIRED_PROJECT_FILE_MARKERS.items():
        path = (root / rel_path).resolve()
        if not path.exists():
            findings.append(
                Finding(
                    "missing_required_file",
                    "專案層級 handoff 工具不存在。",
                    str(path),
                    rel_path,
                    "補上 tools/create_ascii_handoff.py 後重跑本 checker。",
                )
            )
            continue
        text = read_text(path)
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "missing_required_marker",
                        f"專案層級 handoff 工具缺少必要標記: {marker}",
                        str(path),
                        marker,
                        "修正 ASCII handoff 工具後重跑本 checker。",
                    )
                )
    return findings


def build_receipt(root: Path, output_dir: Path, blockers: list[Finding]) -> dict[str, Any]:
    blocker_counts = Counter(item.finding_type for item in blockers)
    gate_result = "PASS" if not blockers else "FAIL"
    return {
        "receipt_type": "hiring_runtime_governance_check",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "gate_result": gate_result,
        "closeout_allowed": gate_result == "PASS",
        "external_runtime_installed_or_started": False,
        "scope": "hiring_demand_folder_only",
        "required_file_count": len(REQUIRED_FILE_MARKERS),
        "typed_blocker_count": len(blockers),
        "typed_blocker_counts": dict(blocker_counts),
        "outputs": {
            "receipt_json": str(output_dir / "hiring_runtime_governance_receipt.json"),
            "receipt_md": str(output_dir / "hiring_runtime_governance_receipt.md"),
            "typed_blockers_csv": str(output_dir / "typed_blockers.csv"),
        },
    }


def write_receipt_md(path: Path, receipt: dict[str, Any], blockers: list[Finding]) -> None:
    if receipt["gate_result"] == "PASS":
        plain = "可以收口：徵人需求度資料夾內的三層治理文件、checker、manifest helper 與 tests 都有對應落點。"
    else:
        plain = "不能收口：徵人需求度資料夾內仍缺治理文件、程式標記或測試證據。"

    lines = [
        "# 徵人需求度 AI Runtime Governance Receipt",
        "",
        "## 白話結論",
        "",
        plain,
        "",
        "## 工程化佐證",
        "",
        f"- root: `{receipt['root']}`",
        f"- scope: `{receipt['scope']}`",
        f"- gate_result: `{receipt['gate_result']}`",
        f"- closeout_allowed: `{receipt['closeout_allowed']}`",
        f"- external_runtime_installed_or_started: `{receipt['external_runtime_installed_or_started']}`",
        f"- required_file_count: `{receipt['required_file_count']}`",
        f"- typed_blocker_count: `{receipt['typed_blocker_count']}`",
        "",
        "## Typed Blockers",
        "",
    ]
    if blockers:
        for blocker in blockers[:80]:
            lines.append(f"- `{blocker.finding_type}` {blocker.affected_key}: {blocker.plain_description}")
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_governance(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    blockers = check_required_markers(root)
    receipt = build_receipt(root, output_dir, blockers)

    (output_dir / "hiring_runtime_governance_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_receipt_md(output_dir / "hiring_runtime_governance_receipt.md", receipt, blockers)
    write_csv(
        output_dir / "typed_blockers.csv",
        [asdict(item) for item in blockers],
        ["finding_type", "plain_description", "affected_file", "affected_key", "required_fix"],
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["gate_result"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check local AI Runtime Governance landing for hiring demand.")
    parser.add_argument("--root", default=".", help="Hiring-demand folder root.")
    parser.add_argument("--output-dir", required=True, help="Output directory for governance receipt.")
    return parser


def main() -> int:
    return check_governance(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
