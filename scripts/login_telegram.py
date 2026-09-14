from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from telethon import TelegramClient

from src.config import load_settings


async def main() -> None:
    settings = load_settings()
    session_path = Path(settings.telegram_session_name)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(
        str(session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.start()
    me = await client.get_me()
    print(f"Telegram session authorized for @{me.username or me.id}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
