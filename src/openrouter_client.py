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

        system_content = (
            system_prompt
            if system_prompt is not None
            else self.settings.openrouter_system_prompt
        )
        last_error: RuntimeError | None = None

        for attempt in range(5):
            user_content = rendered_user_prompt
            if attempt:
                user_content += (
                    "\n\nReturn exactly one complete ready-to-send message. "
                    "Do not return null, None, drafts, fragments, or explanations."
                )

            response = await self.client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={
                    "model": self.settings.openrouter_model,
                    "temperature": self.settings.openrouter_temperature,
                    "max_tokens": self.settings.openrouter_max_tokens,
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_content},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
            try:
                choice = data["choices"][0]
                message = choice["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"Unexpected OpenRouter response: {data}") from exc

            try:
                return self._clean_generated_message(message, choice.get("finish_reason"))
            except RuntimeError as exc:
                last_error = exc

        raise last_error or RuntimeError("OpenRouter returned an invalid message.")

    def _clean_generated_message(self, message: Any, finish_reason: Any) -> str:
        if finish_reason == "length":
            raise RuntimeError(
                "OpenRouter stopped because max_tokens was reached; message was not sent."
            )
        if message is None:
            raise RuntimeError("OpenRouter returned null instead of a message.")
        if not isinstance(message, str):
            raise RuntimeError(f"OpenRouter returned non-text message content: {message!r}")

        clean = message.strip()
        if not clean:
            raise RuntimeError("OpenRouter returned an empty message.")
        if clean.lower() in {"none", "null", "undefined"}:
            raise RuntimeError(f"OpenRouter returned placeholder text: {clean!r}")
        if self._looks_incomplete(clean):
            raise RuntimeError(f"OpenRouter returned an incomplete message: {clean!r}")
        return clean

    def _looks_incomplete(self, message: str) -> bool:
        words = message.split()
        if len(words) < 4:
            return True
        if message[-1] in ".!?)]}\"'»":
            return False
        last_word = words[-1].strip(" ,;:").lower()
        dangling_words = {
            "i",
            "i'm",
            "im",
            "я",
            "мы",
            "вы",
            "и",
            "а",
            "но",
            "что",
            "как",
            "для",
            "по",
            "с",
            "в",
            "на",
            "у",
            "о",
            "к",
            "от",
            "за",
        }
        return last_word in dangling_words

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
