from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from pathlib import Path

from telethon import TelegramClient, functions, types
from telethon.errors import RPCError
from telethon.sessions import StringSession

from .config import Settings


@dataclass(frozen=True)
class TelegramSendResult:
    user_id: int | None
    message_id: int | None


class TelegramUserNotFoundError(RuntimeError):
    pass


class TelegramSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: TelegramClient | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self.settings.telegram_session_string:
            session = StringSession(self.settings.telegram_session_string)
        else:
            session_path = Path(self.settings.telegram_session_name)
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session = str(session_path)

        self.client = TelegramClient(
            session,
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash,
        )
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            raise RuntimeError(
                "Telegram session is not authorized. Run scripts/login_telegram.py first."
            )

    async def disconnect(self) -> None:
        if self.client:
            await self.client.disconnect()

    async def send_to_phone(
        self,
        phone: str,
        message: str,
        first_name: str = "Lead",
    ) -> TelegramSendResult:
        if not self.client:
            raise RuntimeError("Telegram client is not connected.")

        async with self._lock:
            contact = types.InputPhoneContact(
                client_id=random.randint(1, 2**63 - 1),
                phone=phone,
                first_name=first_name[:64] or "Lead",
                last_name="",
            )
            result = await self.client(functions.contacts.ImportContactsRequest([contact]))
            user = result.users[0] if result.users else await self._resolve_user_by_phone(phone)
            if not user:
                raise TelegramUserNotFoundError(
                    "Telegram user was not found by this phone number or is hidden by privacy settings."
                )

            sent_message = await self.client.send_message(user, message)

            if self.settings.telegram_delete_imported_contact:
                await self.client(functions.contacts.DeleteContactsRequest(id=[user]))

            return TelegramSendResult(
                user_id=getattr(user, "id", None),
                message_id=getattr(sent_message, "id", None),
            )

    async def _resolve_user_by_phone(self, phone: str) -> types.User | None:
        if not self.client:
            raise RuntimeError("Telegram client is not connected.")

        for candidate in self._phone_lookup_candidates(phone):
            try:
                entity = await self.client.get_entity(candidate)
            except (RPCError, ValueError, TypeError):
                continue
            if isinstance(entity, types.User):
                return entity

        for candidate in self._phone_lookup_candidates(phone):
            try:
                result = await self.client(
                    functions.contacts.ResolvePhoneRequest(candidate)
                )
            except RPCError:
                continue
            if result.users:
                return result.users[0]

        return None

    @staticmethod
    def _phone_lookup_candidates(phone: str) -> tuple[str, ...]:
        normalized = phone.strip()
        without_plus = normalized.removeprefix("+")
        candidates = (normalized, without_plus)
        return tuple(
            candidate
            for index, candidate in enumerate(candidates)
            if candidate and candidate not in candidates[:index]
        )
