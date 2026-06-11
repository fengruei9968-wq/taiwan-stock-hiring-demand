#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual Telegram sender for hiring-demand report tests.

This module reads the local .env file, sends an authorized test message/photo,
and writes a sanitized receipt. It does not enable scheduling or deployment.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request


TELEGRAM_API_BASE = "https://api.telegram.org"


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str


@dataclass(frozen=True)
class TelegramRecipient:
    label: str
    name: str
    chat_id: str
    source: str


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f".env not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def load_telegram_config(env_path: Path) -> TelegramConfig:
    values = read_env(env_path)
    bot_token = values.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = values.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN")
    if not chat_id:
        raise ValueError("Missing TELEGRAM_CHAT_ID")
    return TelegramConfig(bot_token=bot_token, chat_id=chat_id)


def load_telegram_recipients(env_path: Path, recipients_path: Path | None = None) -> list[TelegramRecipient]:
    config = load_telegram_config(env_path)
    recipients = [
        TelegramRecipient(
            label="env_default",
            name="env_default",
            chat_id=config.chat_id,
            source=str(env_path),
        )
    ]
    seen = {config.chat_id}

    if recipients_path and recipients_path.exists():
        payload = json.loads(recipients_path.read_text(encoding="utf-8"))
        for raw_item in payload.get("recipients", []):
            if raw_item.get("enabled") is False:
                continue
            chat_id = str(raw_item.get("chat_id") or "").strip()
            if not chat_id or chat_id in seen:
                continue
            label = str(raw_item.get("label") or raw_item.get("username") or raw_item.get("name") or "recipient").strip()
            name = str(raw_item.get("name") or raw_item.get("username") or label).strip()
            recipients.append(
                TelegramRecipient(
                    label=label,
                    name=name,
                    chat_id=chat_id,
                    source=str(recipients_path),
                )
            )
            seen.add(chat_id)

    return recipients


def mask_chat_id(chat_id: str) -> str:
    if len(chat_id) <= 6:
        return "***"
    return f"{chat_id[:4]}***{chat_id[-4:]}"


def sanitize_text(value: str, config: TelegramConfig) -> str:
    sanitized = value
    if config.bot_token:
        sanitized = sanitized.replace(config.bot_token, "***TOKEN***")
    if config.chat_id:
        sanitized = sanitized.replace(config.chat_id, mask_chat_id(config.chat_id))
    return sanitized


def telegram_url(config: TelegramConfig, method: str) -> str:
    return f"{TELEGRAM_API_BASE}/bot{config.bot_token}/{method}"


def post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def build_multipart_body(fields: dict[str, Any], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = f"----codex-telegram-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for key, path in files.items():
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"; filename="{path.name}"\r\n'.encode("utf-8")
        )
        chunks.append(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def post_multipart(url: str, fields: dict[str, Any], files: dict[str, Path], timeout: int = 60) -> dict[str, Any]:
    body, boundary = build_multipart_body(fields, files)
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def message_id(response: dict[str, Any]) -> int | None:
    result = response.get("result")
    if isinstance(result, dict) and isinstance(result.get("message_id"), int):
        return result["message_id"]
    return None


def base_receipt(config: TelegramConfig, env_path: Path, photo_path: Path, document_path: Path | None = None) -> dict[str, Any]:
    return {
        "receipt_type": "hiring_demand_telegram_send_test",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "telegram_send_authorized": True,
        "dry_run": False,
        "token_loaded": True,
        "chat_id_masked": mask_chat_id(config.chat_id),
        "env_path": str(env_path),
        "photo_path": str(photo_path),
        "photo_exists": photo_path.exists(),
        "document_path": str(document_path) if document_path else "",
        "document_exists": document_path.exists() if document_path else False,
        "message": {"sent": False, "message_id": None},
        "photo": {"sent": False, "message_id": None},
        "document": {"sent": False, "message_id": None},
        "recipient_count": 1,
        "recipients": [],
        "gate_result": "PENDING",
        "typed_blockers": [],
    }


def recipient_receipt(recipient: TelegramRecipient) -> dict[str, Any]:
    return {
        "label": recipient.label,
        "name": recipient.name,
        "chat_id_masked": mask_chat_id(recipient.chat_id),
        "source": recipient.source,
        "message": {"sent": False, "message_id": None},
        "photo": {"sent": False, "message_id": None},
        "document": {"sent": False, "message_id": None},
    }


def aggregate_stage(recipient_results: list[dict[str, Any]], stage: str, requested: bool) -> dict[str, Any]:
    if not requested:
        return {"sent": False, "message_id": None}
    if not recipient_results:
        return {"sent": False, "message_id": None}
    stage_results = [item[stage] for item in recipient_results]
    sent = all(bool(item.get("sent")) for item in stage_results)
    aggregate: dict[str, Any] = {
        "sent": sent,
        "message_id": stage_results[0].get("message_id") if len(stage_results) == 1 else None,
    }
    statuses = {item.get("status") for item in stage_results if item.get("status")}
    if len(statuses) == 1:
        aggregate["status"] = statuses.pop()
    if all("ok" in item for item in stage_results):
        aggregate["ok"] = sent
    return aggregate


def record_error(receipt: dict[str, Any], config: TelegramConfig, stage: str, error: Exception) -> None:
    receipt["typed_blockers"].append(
        {
            "stage": stage,
            "error_type": type(error).__name__,
            "message": sanitize_text(str(error), config),
        }
    )


def run_send(
    *,
    env_path: Path,
    recipients_path: Path | None = None,
    photo_path: Path,
    output_receipt: Path,
    message_text: str,
    caption: str,
    send_message: bool,
    send_photo: bool,
    document_path: Path | None = None,
    send_document: bool = False,
    dry_run: bool = False,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    config = load_telegram_config(env_path)
    recipients = load_telegram_recipients(env_path, recipients_path)
    receipt = base_receipt(config, env_path, photo_path, document_path)
    receipt["recipient_count"] = len(recipients)
    recipient_results = [recipient_receipt(recipient) for recipient in recipients]
    receipt["recipients"] = recipient_results
    receipt["dry_run"] = dry_run
    if dry_run:
        receipt["telegram_send_authorized"] = False
        for item in recipient_results:
            if send_message:
                item["message"] = {"sent": False, "message_id": None, "status": "DRY_RUN"}
            if send_photo:
                if not photo_path.exists():
                    receipt["typed_blockers"].append({"stage": "sendPhoto", "message": "photo_path does not exist"})
                else:
                    item["photo"] = {"sent": False, "message_id": None, "status": "DRY_RUN"}
            if send_document:
                if document_path is None:
                    receipt["typed_blockers"].append({"stage": "sendDocument", "message": "document_path is required"})
                elif not document_path.exists():
                    receipt["typed_blockers"].append({"stage": "sendDocument", "message": "document_path does not exist"})
                else:
                    item["document"] = {"sent": False, "message_id": None, "status": "DRY_RUN"}
        receipt["message"] = aggregate_stage(recipient_results, "message", send_message)
        receipt["photo"] = aggregate_stage(recipient_results, "photo", send_photo)
        receipt["document"] = aggregate_stage(recipient_results, "document", send_document)
        receipt["gate_result"] = "PASS" if not receipt["typed_blockers"] else "FAIL"
        output_receipt.parent.mkdir(parents=True, exist_ok=True)
        output_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        return receipt

    for index, recipient in enumerate(recipients):
        item = recipient_results[index]
        if send_message:
            try:
                response = post_json(
                    telegram_url(config, "sendMessage"),
                    {"chat_id": recipient.chat_id, "text": message_text, "disable_web_page_preview": True},
                    timeout=timeout_seconds,
                )
                item["message"] = {
                    "sent": bool(response.get("ok")),
                    "message_id": message_id(response),
                    "ok": bool(response.get("ok")),
                }
                if not response.get("ok"):
                    receipt["typed_blockers"].append(
                        {"stage": "sendMessage", "recipient": recipient.label, "message": "Telegram returned ok=false"}
                    )
            except Exception as error:  # noqa: BLE001 - receipt must capture external failures.
                record_error(receipt, config, f"sendMessage:{recipient.label}", error)

        if send_photo:
            if not photo_path.exists():
                receipt["typed_blockers"].append({"stage": "sendPhoto", "message": "photo_path does not exist"})
            else:
                try:
                    response = post_multipart(
                        telegram_url(config, "sendPhoto"),
                        {"chat_id": recipient.chat_id, "caption": caption},
                        {"photo": photo_path},
                        timeout=timeout_seconds,
                    )
                    item["photo"] = {
                        "sent": bool(response.get("ok")),
                        "message_id": message_id(response),
                        "ok": bool(response.get("ok")),
                    }
                    if not response.get("ok"):
                        receipt["typed_blockers"].append(
                            {"stage": "sendPhoto", "recipient": recipient.label, "message": "Telegram returned ok=false"}
                        )
                except Exception as error:  # noqa: BLE001 - receipt must capture external failures.
                    record_error(receipt, config, f"sendPhoto:{recipient.label}", error)

        if send_document:
            if document_path is None:
                receipt["typed_blockers"].append({"stage": "sendDocument", "message": "document_path is required"})
            elif not document_path.exists():
                receipt["typed_blockers"].append({"stage": "sendDocument", "message": "document_path does not exist"})
            else:
                try:
                    response = post_multipart(
                        telegram_url(config, "sendDocument"),
                        {"chat_id": recipient.chat_id, "caption": caption},
                        {"document": document_path},
                        timeout=timeout_seconds,
                    )
                    item["document"] = {
                        "sent": bool(response.get("ok")),
                        "message_id": message_id(response),
                        "ok": bool(response.get("ok")),
                    }
                    if not response.get("ok"):
                        receipt["typed_blockers"].append(
                            {"stage": "sendDocument", "recipient": recipient.label, "message": "Telegram returned ok=false"}
                        )
                except Exception as error:  # noqa: BLE001 - receipt must capture external failures.
                    record_error(receipt, config, f"sendDocument:{recipient.label}", error)

    receipt["message"] = aggregate_stage(recipient_results, "message", send_message)
    receipt["photo"] = aggregate_stage(recipient_results, "photo", send_photo)
    receipt["document"] = aggregate_stage(recipient_results, "document", send_document)

    expected_message = not send_message or receipt["message"]["sent"]
    expected_photo = not send_photo or receipt["photo"]["sent"]
    expected_document = not send_document or receipt["document"]["sent"]
    receipt["gate_result"] = (
        "PASS" if expected_message and expected_photo and expected_document and not receipt["typed_blockers"] else "FAIL"
    )
    output_receipt.parent.mkdir(parents=True, exist_ok=True)
    output_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send an authorized Telegram test message/photo.")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--recipients-path", default="")
    parser.add_argument("--photo-path", required=True)
    parser.add_argument("--document-path", default="")
    parser.add_argument("--output-receipt", required=True)
    parser.add_argument("--message-text", required=True)
    parser.add_argument("--caption", required=True)
    parser.add_argument("--send-message", action="store_true")
    parser.add_argument("--send-photo", action="store_true")
    parser.add_argument("--send-document", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Load env and validate files without calling Telegram.")
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Telegram request timeout in seconds.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.send_message and not args.send_photo and not args.send_document:
        raise SystemExit("At least one of --send-message, --send-photo, or --send-document is required.")
    receipt = run_send(
        env_path=Path(args.env_path),
        recipients_path=Path(args.recipients_path) if args.recipients_path else None,
        photo_path=Path(args.photo_path),
        document_path=Path(args.document_path) if args.document_path else None,
        output_receipt=Path(args.output_receipt),
        message_text=args.message_text,
        caption=args.caption,
        send_message=args.send_message,
        send_photo=args.send_photo,
        send_document=args.send_document,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["gate_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
