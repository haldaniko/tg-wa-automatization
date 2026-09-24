from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import Settings


@dataclass(frozen=True)
class WhatsAppSendResult:
    message_id: str | None


class WhatsAppUserNotFoundError(RuntimeError):
    pass


class WhatsAppNotReadyError(RuntimeError):
    pass


class WhatsAppSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=60)

    async def close(self) -> None:
        await self.client.aclose()

    async def send_to_phone(self, phone: str, message: str) -> WhatsAppSendResult:
        if not self.settings.whatsapp_api_token:
            raise WhatsAppNotReadyError(
                "WhatsApp is not configured. Set WHATSAPP_API_TOKEN first."
            )

        response = await self.client.post(
            f"{self.settings.whatsapp_service_url}/send",
            headers={"Authorization": f"Bearer {self.settings.whatsapp_api_token}"},
            json={"phone": phone, "message": message},
        )
        if response.status_code == 404:
            raise WhatsAppUserNotFoundError(_response_detail(response))
        if response.status_code == 503:
            raise WhatsAppNotReadyError(_response_detail(response))

        response.raise_for_status()
        data = response.json()
        return WhatsAppSendResult(message_id=data.get("message_id"))


def _response_detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    return str(detail or response.text or f"WhatsApp HTTP {response.status_code}")[:1000]
