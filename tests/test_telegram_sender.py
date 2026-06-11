#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import telegram_sender


class TelegramSenderTests(unittest.TestCase):
    def test_load_env_masks_chat_id_without_exposing_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "TELEGRAM_BOT_TOKEN=123456:SECRET\nTELEGRAM_CHAT_ID=-1001234567890\n",
                encoding="utf-8",
            )

            config = telegram_sender.load_telegram_config(env_path)
            receipt = telegram_sender.base_receipt(config, env_path, Path("/tmp/report.png"))

            self.assertEqual(config.bot_token, "123456:SECRET")
            self.assertEqual(config.chat_id, "-1001234567890")
            self.assertEqual(receipt["chat_id_masked"], "-100***7890")
            self.assertNotIn("SECRET", json.dumps(receipt, ensure_ascii=False))

    def test_sanitize_text_does_not_corrupt_text_when_chat_id_is_empty(self) -> None:
        config = telegram_sender.TelegramConfig(bot_token="123456:SECRET", chat_id="")

        sanitized = telegram_sender.sanitize_text('{"ok": true, "token": "123456:SECRET"}', config)

        self.assertEqual(sanitized, '{"ok": true, "token": "***TOKEN***"}')

    def test_send_message_and_photo_write_success_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env"
            photo_path = tmp_path / "report.png"
            receipt_path = tmp_path / "receipt.json"
            env_path.write_text(
                "TELEGRAM_BOT_TOKEN=123456:SECRET\nTELEGRAM_CHAT_ID=987654321\n",
                encoding="utf-8",
            )
            photo_path.write_bytes(b"png")

            calls: list[str] = []

            def fake_post_json(url: str, payload: dict[str, object], timeout: int = 30) -> dict[str, object]:
                calls.append(url)
                self.assertEqual(timeout, 180)
                return {"ok": True, "result": {"message_id": 101}}

            def fake_post_multipart(
                url: str,
                fields: dict[str, object],
                files: dict[str, Path],
                timeout: int = 60,
            ) -> dict[str, object]:
                calls.append(url)
                self.assertEqual(timeout, 180)
                self.assertEqual(files["photo"], photo_path)
                return {"ok": True, "result": {"message_id": 102}}

            with patch.object(telegram_sender, "post_json", side_effect=fake_post_json), patch.object(
                telegram_sender, "post_multipart", side_effect=fake_post_multipart
            ):
                receipt = telegram_sender.run_send(
                    env_path=env_path,
                    photo_path=photo_path,
                    output_receipt=receipt_path,
                    message_text="測試訊息",
                    caption="測試圖片",
                    send_message=True,
                    send_photo=True,
                )

            self.assertEqual(receipt["gate_result"], "PASS")
            self.assertTrue(receipt["message"]["sent"])
            self.assertTrue(receipt["photo"]["sent"])
            self.assertEqual(receipt["message"]["message_id"], 101)
            self.assertEqual(receipt["photo"]["message_id"], 102)
            self.assertEqual(len(calls), 2)
            self.assertTrue(receipt_path.exists())
            self.assertNotIn("SECRET", receipt_path.read_text(encoding="utf-8"))

    def test_send_document_writes_success_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env"
            document_path = tmp_path / "report_highres.png"
            receipt_path = tmp_path / "receipt.json"
            env_path.write_text(
                "TELEGRAM_BOT_TOKEN=123456:SECRET\nTELEGRAM_CHAT_ID=987654321\n",
                encoding="utf-8",
            )
            document_path.write_bytes(b"png")

            calls: list[str] = []

            def fake_post_multipart(
                url: str,
                fields: dict[str, object],
                files: dict[str, Path],
                timeout: int = 60,
            ) -> dict[str, object]:
                calls.append(url)
                self.assertEqual(timeout, 180)
                self.assertTrue(url.endswith("/sendDocument"))
                self.assertEqual(files["document"], document_path)
                self.assertEqual(fields["caption"], "高清 PNG")
                return {"ok": True, "result": {"message_id": 202}}

            with patch.object(telegram_sender, "post_multipart", side_effect=fake_post_multipart):
                receipt = telegram_sender.run_send(
                    env_path=env_path,
                    photo_path=document_path,
                    document_path=document_path,
                    output_receipt=receipt_path,
                    message_text="測試訊息",
                    caption="高清 PNG",
                    send_message=False,
                    send_photo=False,
                    send_document=True,
                )

            self.assertEqual(receipt["gate_result"], "PASS")
            self.assertTrue(receipt["document"]["sent"])
            self.assertEqual(receipt["document"]["message_id"], 202)
            self.assertEqual(receipt["document_path"], str(document_path))
            self.assertEqual(calls, ["https://api.telegram.org/bot123456:SECRET/sendDocument"])
            self.assertTrue(receipt_path.exists())
            self.assertNotIn("SECRET", receipt_path.read_text(encoding="utf-8"))

    def test_send_document_fans_out_to_enabled_recipients(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env"
            recipients_path = tmp_path / "telegram_recipients.json"
            document_path = tmp_path / "report_highres.png"
            receipt_path = tmp_path / "receipt.json"
            env_path.write_text(
                "TELEGRAM_BOT_TOKEN=123456:SECRET\nTELEGRAM_CHAT_ID=111111111\n",
                encoding="utf-8",
            )
            recipients_path.write_text(
                json.dumps(
                    {
                        "schema_version": "2026-05-16",
                        "recipients": [
                            {"label": "friend", "name": "Friend", "chat_id": "222222222", "enabled": True},
                            {"label": "off", "name": "Disabled", "chat_id": "333333333", "enabled": False},
                            {"label": "duplicate_owner", "name": "Duplicate", "chat_id": "111111111", "enabled": True},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            document_path.write_bytes(b"png")

            sent_chat_ids: list[str] = []

            def fake_post_multipart(
                url: str,
                fields: dict[str, object],
                files: dict[str, Path],
                timeout: int = 60,
            ) -> dict[str, object]:
                self.assertTrue(url.endswith("/sendDocument"))
                self.assertEqual(files["document"], document_path)
                sent_chat_ids.append(str(fields["chat_id"]))
                return {"ok": True, "result": {"message_id": 200 + len(sent_chat_ids)}}

            with patch.object(telegram_sender, "post_multipart", side_effect=fake_post_multipart):
                receipt = telegram_sender.run_send(
                    env_path=env_path,
                    recipients_path=recipients_path,
                    photo_path=document_path,
                    document_path=document_path,
                    output_receipt=receipt_path,
                    message_text="",
                    caption="",
                    send_message=False,
                    send_photo=False,
                    send_document=True,
                )

            self.assertEqual(sent_chat_ids, ["111111111", "222222222"])
            self.assertEqual(receipt["recipient_count"], 2)
            self.assertEqual(receipt["gate_result"], "PASS")
            self.assertTrue(receipt["document"]["sent"])
            self.assertEqual([item["label"] for item in receipt["recipients"]], ["env_default", "friend"])
            self.assertTrue(all(item["document"]["sent"] for item in receipt["recipients"]))
            receipt_text = receipt_path.read_text(encoding="utf-8")
            self.assertNotIn("SECRET", receipt_text)
            self.assertNotIn("111111111", receipt_text)
            self.assertNotIn("222222222", receipt_text)

    def test_dry_run_loads_env_and_document_without_sending_network_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env"
            document_path = tmp_path / "report_highres.png"
            receipt_path = tmp_path / "receipt.json"
            env_path.write_text(
                "TELEGRAM_BOT_TOKEN=123456:SECRET\nTELEGRAM_CHAT_ID=987654321\n",
                encoding="utf-8",
            )
            document_path.write_bytes(b"png")

            with patch.object(telegram_sender, "post_json") as post_json, patch.object(
                telegram_sender, "post_multipart"
            ) as post_multipart:
                receipt = telegram_sender.run_send(
                    env_path=env_path,
                    photo_path=document_path,
                    document_path=document_path,
                    output_receipt=receipt_path,
                    message_text="測試訊息",
                    caption="高清 PNG",
                    send_message=False,
                    send_photo=False,
                    send_document=True,
                    dry_run=True,
                )

            post_json.assert_not_called()
            post_multipart.assert_not_called()
            self.assertEqual(receipt["gate_result"], "PASS")
            self.assertTrue(receipt["dry_run"])
            self.assertFalse(receipt["document"]["sent"])
            self.assertEqual(receipt["document"]["status"], "DRY_RUN")
            self.assertNotIn("SECRET", receipt_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
