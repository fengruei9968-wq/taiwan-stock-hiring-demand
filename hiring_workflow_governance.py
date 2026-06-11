#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local workflow manifest and trace helpers for hiring demand.

This module is stdlib-only. It maps the hiring-demand run manifest to the
project-wide AI Runtime Governance shape and writes local JSONL trace evidence.
It does not install, start, deploy, or call any external governance runtime.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


CONTRACT_ID = "hiring-demand-ai-runtime-governance-v1"
WORKFLOW_SCHEMA_VERSION = "2026-05-15"
WORKFLOW_NAME = "hiring_demand_update"
EXTERNAL_RUNTIME_NAMES = [
    "opa",
    "opa_gatekeeper_library",
    "temporal",
    "langfuse",
    "great_expectations",
    "prefect",
    "dagster",
    "argo_workflows",
    "opentelemetry",
    "superpowers_runtime",
]
TERMINAL_BLOCKERS = [
    "formal_batch_unauthorized",
    "formal_result_replacement_unauthorized",
    "git_commit_push_merge_unauthorized",
    "external_paid_api_or_forbidden_tool",
    "missing_required_source_data",
    "missing_trusted_verifier_or_negative_control",
    "scope_run_id_path_boundary_exceeded",
    "environment_unavailable",
]


def _path_item(path: str | Path, role: str, **extra: Any) -> dict[str, Any]:
    item = {"path": str(path), "role": role}
    item.update(extra)
    return item


def _runtime_policy() -> dict[str, Any]:
    return {
        "external_runtime_default": "disabled",
        "external_runtimes": {
            name: {"installed": False, "started": False, "deployed": False}
            for name in EXTERNAL_RUNTIME_NAMES
        },
    }


def build_workflow_manifest(
    hiring_manifest: dict[str, Any],
    *,
    hiring_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Map the hiring-demand run manifest to the common governance shape."""
    run_mode = str(hiring_manifest.get("run_mode", ""))
    run_id = str(hiring_manifest.get("run_id", ""))
    csv_path = str(hiring_manifest.get("csv_path", ""))
    db_path = str(hiring_manifest.get("db_path", ""))
    stock_codes_file = str(hiring_manifest.get("input_stock_codes_file", ""))
    deploy_requested = run_mode == "deploy"
    db_write_expected = run_mode in {"write-db", "deploy"}

    steps = [
        {
            "id": "source_of_truth_gate",
            "layer": "outer",
            "status": "PASS",
            "triggered_rules": ["active_truth_required", "folder_scope_only"],
            "evidence_paths": ["CURRENT_HIRING_DEMAND_EXECUTION.md", "CLAUDE_hiring_demand.md"],
        },
        {
            "id": "fetch_104_jobs",
            "layer": "inner",
            "status": "PASS",
            "triggered_rules": ["global_keyword_search", "job_title_filter", "rate_limit"],
            "evidence_paths": [stock_codes_file, "config.yaml"],
        },
        {
            "id": "company_match_and_need_emp",
            "layer": "inner",
            "status": "PASS",
            "triggered_rules": ["company_match_fallback", "need_emp_detail_api", "999_998_special_values"],
            "evidence_paths": [str(hiring_manifest_path or ""), csv_path],
        },
        {
            "id": "csv_output",
            "layer": "inner",
            "status": "PASS",
            "triggered_rules": ["csv_schema", "dated_csv_filename"],
            "evidence_paths": [csv_path],
        },
        {
            "id": "db_write",
            "layer": "inner",
            "status": "PASS" if db_write_expected else "SKIP",
            "triggered_rules": ["hiring_demand_table", "hiring_demand_jobs_table"],
            "evidence_paths": [db_path] if db_write_expected else [],
        },
        {
            "id": "checker_required",
            "layer": "middle",
            "status": "PENDING",
            "triggered_rules": ["read_only_checker", "positive_control", "negative_controls"],
            "evidence_paths": ["check_hiring_demand_run.py"],
        },
    ]

    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "workflow_name": WORKFLOW_NAME,
        "run_id": run_id,
        "mode": run_mode,
        "generated_at": hiring_manifest.get("ended_at", datetime.now().isoformat(timespec="seconds")),
        "source_of_truth": [
            _path_item("CURRENT_HIRING_DEMAND_EXECUTION.md", "active_truth"),
            _path_item("CLAUDE_hiring_demand.md", "workflow_doc"),
        ],
        "authorization": {
            "formal_batch": False,
            "replace_formal_results": False,
            "commit": deploy_requested,
            "push": deploy_requested,
            "merge": False,
            "deploy": deploy_requested,
            "paid_api": False,
        },
        "runtime_policy": _runtime_policy(),
        "forbidden_actions": {
            "formal_batch": False,
            "replace_formal_results": False,
            "commit": False,
            "push": False,
            "merge": False,
            "deploy_external_runtime": False,
            "paid_api": False,
        },
        "inputs": [
            _path_item(stock_codes_file, "stock_codes_csv"),
            _path_item("config.yaml", "config"),
            {
                "path": "https://www.104.com.tw/jobs/search/api/jobs",
                "role": "104_search_api",
                "keywords": hiring_manifest.get("api_source_summary", {}).get("search_keywords", []),
            },
        ],
        "steps": steps,
        "outputs": [
            _path_item(csv_path, "hiring_demand_csv", row_count=hiring_manifest.get("csv_row_count", 0)),
            _path_item(db_path, "investment_db", row_count=hiring_manifest.get("db_inserted_count", 0)),
            _path_item(str(hiring_manifest_path or ""), "hiring_run_manifest"),
        ],
        "validation": {
            "schema_check": "PENDING_CHECKER",
            "row_count_check": "PENDING_CHECKER",
            "evidence_check": "PENDING_CHECKER",
        },
        "positive_controls": [{"name": "test_valid_csv_db_and_jobs_pass", "status": "DEFINED"}],
        "negative_controls": [
            {"name": "test_db_row_count_mismatch_fails", "status": "DEFINED"},
            {"name": "test_invalid_unlimited_special_value_fails", "status": "DEFINED"},
            {"name": "test_deploy_requires_explicit_deploy_mode", "status": "DEFINED"},
            {"name": "test_scrape_only_skips_db_checks_and_never_allows_deploy", "status": "DEFINED"},
        ],
        "terminal_blockers": TERMINAL_BLOCKERS,
        "closeout": {
            "required": True,
            "completed": False,
            "fresh_verification": False,
            "closeout_report_path": "",
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_workflow_trace_receipt(
    workflow_manifest: dict[str, Any],
    *,
    trace_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    """Write local JSONL spans and a JSON receipt for the workflow manifest."""
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_id = uuid.uuid4().hex
    generated_at = datetime.now().isoformat(timespec="seconds")
    steps = workflow_manifest.get("steps", [])

    with trace_path.open("w", encoding="utf-8") as handle:
        for index, step in enumerate(steps, start=1):
            span = {
                "trace_id": trace_id,
                "span_id": f"{trace_id}-{index:04d}",
                "workflow_name": workflow_manifest.get("workflow_name", WORKFLOW_NAME),
                "run_id": workflow_manifest.get("run_id", ""),
                "step_id": step.get("id", ""),
                "layer": step.get("layer", ""),
                "status": step.get("status", ""),
                "triggered_rules": step.get("triggered_rules", []),
                "evidence_paths": step.get("evidence_paths", []),
                "recorded_at": generated_at,
            }
            json.dump(span, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")

    receipt = {
        "contract_id": f"{CONTRACT_ID}:{workflow_manifest.get('run_id', '')}:{WORKFLOW_NAME}",
        "workflow_name": workflow_manifest.get("workflow_name", WORKFLOW_NAME),
        "run_id": workflow_manifest.get("run_id", ""),
        "trace_id": trace_id,
        "span_count": len(steps),
        "trace_path": str(trace_path),
        "receipt_path": str(receipt_path),
        "external_runtime_policy": "local-jsonl-only",
        "generated_at": generated_at,
    }
    write_json(receipt_path, receipt)
    return receipt


def write_workflow_governance_artifacts(
    hiring_manifest: dict[str, Any],
    *,
    run_root: Path,
    hiring_manifest_path: Path,
) -> dict[str, Path]:
    """Write aligned workflow manifest plus trace artifacts for a run root."""
    workflow_manifest = build_workflow_manifest(
        hiring_manifest,
        hiring_manifest_path=hiring_manifest_path,
    )
    workflow_manifest_path = run_root / "workflow_manifest.json"
    trace_path = run_root / "workflow_trace.jsonl"
    receipt_path = run_root / "workflow_trace_receipt.json"
    write_json(workflow_manifest_path, workflow_manifest)
    write_workflow_trace_receipt(workflow_manifest, trace_path=trace_path, receipt_path=receipt_path)

    runs_dir = run_root.parent
    latest_manifest_path = runs_dir / "latest_workflow_manifest.json"
    latest_trace_path = runs_dir / "latest_workflow_trace.jsonl"
    latest_receipt_path = runs_dir / "latest_workflow_trace_receipt.json"
    shutil.copyfile(workflow_manifest_path, latest_manifest_path)
    shutil.copyfile(trace_path, latest_trace_path)
    shutil.copyfile(receipt_path, latest_receipt_path)

    return {
        "workflow_manifest": workflow_manifest_path,
        "workflow_trace": trace_path,
        "workflow_trace_receipt": receipt_path,
        "latest_workflow_manifest": latest_manifest_path,
        "latest_workflow_trace": latest_trace_path,
        "latest_workflow_trace_receipt": latest_receipt_path,
    }
