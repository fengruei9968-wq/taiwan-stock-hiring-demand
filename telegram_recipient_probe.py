#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discover Telegram chat IDs from bot /start updates and maintain recipients."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request

from telegram_sender import mask_chat_id, read_env, sanitize_text


SCHEMA_VERSION = "2026-05-16"


def safe_label(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_-]+", "_", value.strip())
    value = value.strip("_")
    return value or "telegram_user"


def fetch_updates(bot_token: str, timeout_seconds: int = 30) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    with request.urlopen(url, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_start_recipients(updates: dict[str, Any]) -> list[dict[str, Any]]:
    recipients: list[dict[str, Any]] = []
    seen: set[str] = set()
    for update in updates.get("result", []):
        message = update.get("message") or update.get("edited_message") or {}
        text = str(message.get("text") or "").strip()
        if not text.startswith("/start"):
            continue
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        chat_id = str(chat.get("id") or "").strip()
        if not chat_id or chat_id in seen:
            continue
        username = str(user.get("username") or "").strip()
        first_name = str(user.get("first_name") or "").strip()
        last_name = str(user.get("last_name") or "").strip()
        name = " ".join(part for part in [first_name, last_name] if part).strip() or username or chat_id
        label = safe_label(username or name or chat_id)
        recipients.append(
            {
                "label": label,
                "name": name,
                "username": username,
                "chat_id": chat_id,
                "enabled": True,
                "source": "telegram_getUpdates_start",
                "discovered_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        seen.add(chat_id)
    return recipients


def load_recipients_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "file_type": "telegram_recipient_list",
            "updated_at": "",
            "recipients": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def upsert_recipients_file(path: Path, new_recipients: list[dict[str, Any]]) -> dict[str, Any]:
    payload = load_recipients_file(path)
    existing = payload.get("recipients") or []
    by_chat_id = {str(item.get("chat_id")): dict(item) for item in existing if item.get("chat_id")}
    order = [str(item.get("chat_id")) for item in existing if item.get("chat_id")]

    for recipient in new_recipients:
        chat_id = str(recipient.get("chat_id") or "").strip()
        if not chat_id:
            continue
        current = by_chat_id.get(chat_id, {})
        was_disabled = current.get("enabled") is False
        disabled_at = current.get("disabled_at")
        disabled_reason = current.get("disabled_reason")
        current.update(recipient)
        if was_disabled:
            current["enabled"] = False
            if disabled_at:
                current["disabled_at"] = disabled_at
            if disabled_reason:
                current["disabled_reason"] = disabled_reason
            current["last_seen_after_disabled_at"] = recipient.get("discovered_at") or datetime.now().isoformat(timespec="seconds")
        by_chat_id[chat_id] = current
        if chat_id not in order:
            order.append(chat_id)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "file_type": "telegram_recipient_list",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "recipients": [by_chat_id[chat_id] for chat_id in order],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def masked_recipients(recipients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    masked = []
    for recipient in recipients:
        item = dict(recipient)
        item["chat_id_masked"] = mask_chat_id(str(item.get("chat_id") or ""))
        item.pop("chat_id", None)
        masked.append(item)
    return masked


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover Telegram recipients from /start updates.")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--recipients-path", default="telegram_recipients.json")
    parser.add_argument("--updates-json", default="", help="Read Telegram getUpdates payload from a local JSON file.")
    parser.add_argument("--output-receipt", default="")
    parser.add_argument("--dry-run", action="store_true", help="Do not write recipients file.")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    env_path = Path(args.env_path)
    recipients_path = Path(args.recipients_path)
    env_values = read_env(env_path)
    bot_token = env_values.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN")

    if args.updates_json:
        updates = json.loads(Path(args.updates_json).read_text(encoding="utf-8"))
    else:
        updates = fetch_updates(bot_token, timeout_seconds=args.timeout_seconds)

    recipients = extract_start_recipients(updates)
    if args.dry_run:
        payload = load_recipients_file(recipients_path)
    else:
        payload = upsert_recipients_file(recipients_path, recipients)

    receipt = {
        "receipt_type": "telegram_recipient_probe",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "env_path": str(env_path),
        "recipients_path": str(recipients_path),
        "token_loaded": True,
        "dry_run": bool(args.dry_run),
        "new_recipient_count": len(recipients),
        "total_recipient_count": len(payload.get("recipients") or []),
        "new_recipients": masked_recipients(recipients),
        "gate_result": "PASS",
    }
    receipt_text = sanitize_text(json.dumps(receipt, ensure_ascii=False, indent=2), type("_Config", (), {"bot_token": bot_token, "chat_id": ""})())
    if args.output_receipt:
        receipt_path = Path(args.output_receipt)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(receipt_text + "\n", encoding="utf-8")
    print(receipt_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
