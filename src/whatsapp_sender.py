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
    def __init__(
        self,
        settings: Settings,
        *,
        service_url: str | None = None,
        api_token: str | None = None,
        account_name: str = "WhatsApp",
    ) -> None:
        self.service_url = service_url or settings.whatsapp_service_url
        self.api_token = (
            settings.whatsapp_api_token if api_token is None else api_token
        )
        self.account_name = account_name
        self.client = httpx.AsyncClient(timeout=60)

    async def close(self) -> None:
        await self.client.aclose()

    async def send_to_phone(self, phone: str, message: str) -> WhatsAppSendResult:
        if not self.api_token:
            raise WhatsAppNotReadyError(
                f"{self.account_name} is not configured. Set its API token first."
            )

        response = await self.client.post(
            f"{self.service_url}/send",
            headers={"Authorization": f"Bearer {self.api_token}"},
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
