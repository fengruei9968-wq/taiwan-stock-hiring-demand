#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import socket
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.104.com.tw/jobs/search/",
    "Accept": "application/json, text/plain, */*",
}
POLICY_PATH = Path(__file__).with_name("hiring_recovery_policy.json")


def load_recovery_policy(path: Path = POLICY_PATH) -> dict[str, dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def policy_action(failure_type: str | None) -> str:
    if failure_type is None:
        return "continue"
    policy = load_recovery_policy()
    return policy.get(failure_type, policy["unknown_failure"])["action"]


def looks_like_cloudflare(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "cloudflare",
        "cf-chl",
        "just a moment",
        "attention required",
        "checking your browser",
    )
    return any(marker in lowered for marker in markers)


def classify_response(
    *,
    status_code: int,
    content_type: str,
    text: str,
    payload: Any,
) -> dict[str, Any]:
    failure_type: str | None = None
    plain_description = "104 search API probe passed."

    if status_code == 403 and looks_like_cloudflare(text):
        failure_type = "cloudflare_challenge"
        plain_description = "104 returned an HTML Cloudflare challenge."
    elif status_code == 403:
        failure_type = "http_403"
        plain_description = "104 returned HTTP 403."
    elif status_code == 429:
        failure_type = "http_429"
        plain_description = "104 returned HTTP 429 rate limit."
    elif status_code >= 500:
        failure_type = "http_5xx"
        plain_description = f"104 returned HTTP {status_code}."
    elif status_code != 200:
        failure_type = "http_unexpected_status"
        plain_description = f"104 returned HTTP {status_code}."
    elif looks_like_cloudflare(text):
        failure_type = "cloudflare_challenge"
        plain_description = "104 response body looks like a Cloudflare challenge."
    elif not isinstance(payload, dict):
        failure_type = "non_json_response"
        plain_description = "104 response was not parseable JSON."
    elif not isinstance(payload.get("data"), list):
        failure_type = "unexpected_json_schema"
        plain_description = "104 JSON did not contain a data list."
    elif len(payload.get("data") or []) == 0:
        failure_type = "empty_jobs"
        plain_description = "104 JSON was valid but returned no jobs."

    return {
        "gate_result": "PASS" if failure_type is None else "FAIL",
        "failure_type": failure_type,
        "recovery_action": policy_action(failure_type),
        "plain_description": plain_description,
        "http_status": status_code,
        "content_type": content_type,
        "job_count": len(payload.get("data") or []) if isinstance(payload, dict) else 0,
    }


def build_probe_params(keyword: str, page_size: int) -> dict[str, Any]:
    return {
        "keyword": keyword,
        "page": 1,
        "pagesize": page_size,
        "order": 15,
        "asc": 0,
    }


def run_probe(keyword: str, timeout: float, page_size: int) -> dict[str, Any]:
    started_at = datetime.now().isoformat(timespec="seconds")
    params = build_probe_params(keyword, page_size)
    try:
        response = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=timeout)
        content_type = response.headers.get("Content-Type", "")
        text = response.text[:4096]
        try:
            payload = response.json()
        except ValueError:
            payload = None
        result = classify_response(
            status_code=response.status_code,
            content_type=content_type,
            text=text,
            payload=payload,
        )
    except requests.exceptions.Timeout:
        result = {
            "gate_result": "FAIL",
            "failure_type": "network_timeout",
            "recovery_action": policy_action("network_timeout"),
            "plain_description": "104 probe timed out.",
            "http_status": None,
            "content_type": "",
            "job_count": 0,
        }
    except requests.exceptions.ConnectionError as exc:
        failure_type = "dns_failure" if isinstance(getattr(exc, "__context__", None), socket.gaierror) else "connection_error"
        result = {
            "gate_result": "FAIL",
            "failure_type": failure_type,
            "recovery_action": policy_action(failure_type),
            "plain_description": f"104 probe connection error: {type(exc).__name__}",
            "http_status": None,
            "content_type": "",
            "job_count": 0,
        }
    except requests.exceptions.RequestException as exc:
        result = {
            "gate_result": "FAIL",
            "failure_type": "request_exception",
            "recovery_action": policy_action("request_exception"),
            "plain_description": f"104 probe request exception: {type(exc).__name__}",
            "http_status": None,
            "content_type": "",
            "job_count": 0,
        }

    result.update(
        {
            "receipt_type": "hiring_104_api_probe",
            "schema_version": 1,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "started_at": started_at,
            "endpoint": SEARCH_URL,
            "keyword": keyword,
            "timeout_seconds": timeout,
            "page_size": page_size,
        }
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe 104 Job Bank search API before hiring-demand runs.")
    parser.add_argument("--keyword", default="作業員")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--output", required=True, help="Path to write api_probe_receipt JSON.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    receipt = run_probe(args.keyword, args.timeout, args.page_size)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["gate_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
