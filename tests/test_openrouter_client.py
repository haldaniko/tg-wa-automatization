from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import httpx

from src.config import Settings
from src.openrouter_client import OpenRouterClient


def _settings() -> Settings:
    return Settings(
        webhook_secret="secret",
        app_host="127.0.0.1",
        app_port=8000,
        database_path=Path("test.sqlite3"),
        dry_run=True,
        lead_phone_field="phone",
        telegram_api_id=1,
        telegram_api_hash="hash",
        telegram_session_name="sessions/test",
        telegram_session_string="",
        telegram_delete_imported_contact=False,
        whatsapp_service_url="http://whatsapp:3000",
        whatsapp_api_token="token",
        openrouter_api_key="key",
        openrouter_model="test-model",
        openrouter_temperature=0.7,
        openrouter_max_tokens=220,
        openrouter_http_referer="",
        openrouter_app_title="Test",
        openrouter_system_prompt="Write a message.",
        openrouter_user_prompt="Lead: {lead_json}",
        openrouter_whatsapp_system_prompt="Write a WhatsApp message.",
        openrouter_whatsapp_user_prompt="Lead: {lead_json}",
    )


def _openrouter_response(content: object, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"content": content},
                }
            ]
        },
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


class OpenRouterClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_retries_null_and_returns_valid_message(self) -> None:
        client = OpenRouterClient(_settings())
        client.client.post = AsyncMock(
            side_effect=[
                _openrouter_response(None),
                _openrouter_response("Здравствуйте! Хотели бы узнать больше о ваших услугах?"),
            ]
        )

        try:
            message = await client.generate_message(
                {"phone": "+380972964484"},
                {"lead": {"phone": "+380972964484"}},
                "+380972964484",
            )
        finally:
            await client.close()

        self.assertEqual(
            message,
            "Здравствуйте! Хотели бы узнать больше о ваших услугах?",
        )
        self.assertEqual(client.client.post.await_count, 2)

    async def test_rejects_placeholder_text_after_retry(self) -> None:
        client = OpenRouterClient(_settings())
        client.client.post = AsyncMock(
            side_effect=[_openrouter_response("None") for _ in range(5)]
        )

        try:
            with self.assertRaisesRegex(RuntimeError, "placeholder"):
                await client.generate_message({}, {}, "+380972964484")
        finally:
            await client.close()
        self.assertEqual(client.client.post.await_count, 5)

    async def test_rejects_length_truncated_message(self) -> None:
        client = OpenRouterClient(_settings())
        client.client.post = AsyncMock(
            side_effect=[
                _openrouter_response("Здравствуйте, Мохамед!\n\nЯ", "length")
                for _ in range(5)
            ]
        )

        try:
            with self.assertRaisesRegex(RuntimeError, "max_tokens"):
                await client.generate_message({}, {}, "+380972964484")
        finally:
            await client.close()
        self.assertEqual(client.client.post.await_count, 5)

    async def test_rejects_dangling_fragment_after_retry(self) -> None:
        client = OpenRouterClient(_settings())
        client.client.post = AsyncMock(
            side_effect=[
                _openrouter_response("Здравствуйте, Мохамед!\n\nЯ") for _ in range(5)
            ]
        )

        try:
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                await client.generate_message({}, {}, "+380972964484")
        finally:
            await client.close()
        self.assertEqual(client.client.post.await_count, 5)


if __name__ == "__main__":
    unittest.main()
