from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "test")
os.environ.setdefault("OPENROUTER_API_KEY", "test")

from src import main  # noqa: E402


class WhatsAppWebhookTest(unittest.TestCase):
    def test_dry_run_is_deduplicated_independently(self) -> None:
        payload = {
            "spreadsheetId": "sheet-1",
            "sheetName": "Leads",
            "rowNumber": 2,
            "lead": {"phone": "+380972964484", "name": "Test"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["DATABASE_PATH"] = str(Path(temp_dir) / "leads.sqlite3")
            generate_message = AsyncMock(return_value="WhatsApp test message")
            with patch.object(
                main.OpenRouterClient,
                "generate_message",
                new=generate_message,
            ):
                with TestClient(main.app) as client:
                    first = client.post(
                        "/webhooks/google-sheets/whatsapp",
                        json=payload,
                        headers={"X-Webhook-Secret": "test-secret"},
                    )
                    second = client.post(
                        "/webhooks/google-sheets/whatsapp",
                        json=payload,
                        headers={"X-Webhook-Secret": "test-secret"},
                    )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "dry_run")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(generate_message.await_count, 1)
        self.assertEqual(
            generate_message.await_args.kwargs["user_prompt"],
            main.services.settings.openrouter_whatsapp_user_prompt,
        )


if __name__ == "__main__":
    unittest.main()
