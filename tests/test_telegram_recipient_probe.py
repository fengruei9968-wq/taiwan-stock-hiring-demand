#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import telegram_recipient_probe


class TelegramRecipientProbeTests(unittest.TestCase):
    def test_extract_start_recipients_from_updates(self) -> None:
        updates = {
            "ok": True,
            "result": [
                {
                    "update_id": 10,
                    "message": {
                        "text": "/start",
                        "from": {"id": 123, "first_name": "Tom", "username": "tommy123"},
                        "chat": {"id": 987654321, "type": "private"},
                    },
                },
                {
                    "update_id": 11,
                    "message": {
                        "text": "hello",
                        "from": {"id": 456, "first_name": "Amy", "username": "amy_lin"},
                        "chat": {"id": 111222333, "type": "private"},
                    },
                },
            ],
        }

        recipients = telegram_recipient_probe.extract_start_recipients(updates)

        self.assertEqual(len(recipients), 1)
        self.assertEqual(recipients[0]["label"], "tommy123")
        self.assertEqual(recipients[0]["name"], "Tom")
        self.assertEqual(recipients[0]["username"], "tommy123")
        self.assertEqual(recipients[0]["chat_id"], "987654321")
        self.assertTrue(recipients[0]["enabled"])

    def test_upsert_recipients_file_preserves_existing_and_dedupes_chat_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recipients_path = Path(tmp) / "telegram_recipients.json"
            recipients_path.write_text(
                json.dumps(
                    {
                        "schema_version": "2026-05-16",
                        "recipients": [
                            {"label": "owner", "name": "Owner", "chat_id": "111111111", "enabled": True},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = telegram_recipient_probe.upsert_recipients_file(
                recipients_path,
                [
                    {"label": "friend", "name": "Friend", "username": "friend", "chat_id": "222222222", "enabled": True},
                    {"label": "owner_new", "name": "Owner Updated", "username": "owner", "chat_id": "111111111", "enabled": True},
                ],
            )

            self.assertEqual(payload["schema_version"], "2026-05-16")
            self.assertEqual([item["chat_id"] for item in payload["recipients"]], ["111111111", "222222222"])
            self.assertEqual(payload["recipients"][0]["label"], "owner_new")
            self.assertEqual(payload["recipients"][1]["label"], "friend")
            saved_text = recipients_path.read_text(encoding="utf-8")
            self.assertIn("telegram_recipient_list", saved_text)

    def test_upsert_recipients_file_preserves_disabled_opt_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recipients_path = Path(tmp) / "telegram_recipients.json"
            recipients_path.write_text(
                json.dumps(
                    {
                        "schema_version": "2026-05-16",
                        "recipients": [
                            {
                                "label": "tsaiball",
                                "name": "Tsaiball",
                                "chat_id": "333333333",
                                "enabled": False,
                                "disabled_at": "2026-05-17T13:00:00",
                                "disabled_reason": "user_requested_no_png",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = telegram_recipient_probe.upsert_recipients_file(
                recipients_path,
                [
                    {
                        "label": "Tsaiball",
                        "name": "Tsaiball",
                        "username": "tsaiball",
                        "chat_id": "333333333",
                        "enabled": True,
                        "discovered_at": "2026-05-17T13:30:00",
                    },
                ],
            )

            recipient = payload["recipients"][0]
            self.assertFalse(recipient["enabled"])
            self.assertEqual(recipient["disabled_at"], "2026-05-17T13:00:00")
            self.assertEqual(recipient["disabled_reason"], "user_requested_no_png")
            self.assertEqual(recipient["last_seen_after_disabled_at"], "2026-05-17T13:30:00")


if __name__ == "__main__":
    unittest.main()
