from __future__ import annotations

import json
from typing import Any

import httpx

from .config import Settings


class OpenRouterClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=40)

    async def close(self) -> None:
        await self.client.aclose()

    async def generate_message(
        self,
        lead: dict[str, Any],
        payload: dict[str, Any],
        phone: str,
        *,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> str:
        rendered_user_prompt = self._render_prompt(
            lead=lead,
            payload=payload,
            phone=phone,
            prompt=(
                user_prompt
                if user_prompt is not None
                else self.settings.openrouter_user_prompt
            ),
        )
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self.settings.openrouter_http_referer:
            headers["HTTP-Referer"] = self.settings.openrouter_http_referer
        if self.settings.openrouter_app_title:
            headers["X-OpenRouter-Title"] = self.settings.openrouter_app_title

        response = await self.client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": self.settings.openrouter_model,
                "temperature": self.settings.openrouter_temperature,
                "max_tokens": self.settings.openrouter_max_tokens,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            system_prompt
                            if system_prompt is not None
                            else self.settings.openrouter_system_prompt
                        ),
                    },
                    {"role": "user", "content": rendered_user_prompt},
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        try:
            message = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected OpenRouter response: {data}") from exc

        message = str(message).strip()
        if not message:
            raise RuntimeError("OpenRouter returned an empty message.")
        return message

    def _render_prompt(
        self,
        lead: dict[str, Any],
        payload: dict[str, Any],
        phone: str,
        prompt: str,
    ) -> str:
        lead_json = json.dumps(lead, ensure_ascii=False, indent=2)
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
        replacements = {
            "{lead_json}": lead_json,
            "{payload_json}": payload_json,
            "{phone}": phone,
            "{sheet_name}": str(payload.get("sheetName", "")),
            "{spreadsheet_id}": str(payload.get("spreadsheetId", "")),
            "{row_number}": str(payload.get("rowNumber", "")),
        }
        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, value)
        return prompt
