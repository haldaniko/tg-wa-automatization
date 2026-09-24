from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    webhook_secret: str
    app_host: str
    app_port: int
    database_path: Path
    dry_run: bool
    lead_phone_field: str
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_name: str
    telegram_session_string: str
    telegram_delete_imported_contact: bool
    whatsapp_service_url: str
    whatsapp_api_token: str
    openrouter_api_key: str
    openrouter_model: str
    openrouter_temperature: float
    openrouter_max_tokens: int
    openrouter_http_referer: str
    openrouter_app_title: str
    openrouter_system_prompt: str
    openrouter_user_prompt: str
    openrouter_whatsapp_system_prompt: str
    openrouter_whatsapp_user_prompt: str


def load_settings() -> Settings:
    load_dotenv()

    openrouter_system_prompt = os.getenv(
        "OPENROUTER_SYSTEM_PROMPT",
        "You write short, warm first-touch messages.",
    ).strip()
    openrouter_user_prompt = os.getenv(
        "OPENROUTER_USER_PROMPT",
        "Create a short greeting for this lead: {lead_json}",
    ).strip()

    return Settings(
        webhook_secret=_required("WEBHOOK_SECRET"),
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        database_path=Path(os.getenv("DATABASE_PATH", "data/leads.sqlite3")),
        dry_run=_bool("DRY_RUN", False),
        lead_phone_field=os.getenv("LEAD_PHONE_FIELD", "phone").strip(),
        telegram_api_id=int(_required("TELEGRAM_API_ID")),
        telegram_api_hash=_required("TELEGRAM_API_HASH"),
        telegram_session_name=os.getenv("TELEGRAM_SESSION_NAME", "sessions/userbot").strip(),
        telegram_session_string=os.getenv("TELEGRAM_SESSION_STRING", "").strip(),
        telegram_delete_imported_contact=_bool("TELEGRAM_DELETE_IMPORTED_CONTACT", False),
        whatsapp_service_url=os.getenv(
            "WHATSAPP_SERVICE_URL", "http://whatsapp:3000"
        ).strip().rstrip("/"),
        whatsapp_api_token=os.getenv("WHATSAPP_API_TOKEN", "").strip(),
        openrouter_api_key=_required("OPENROUTER_API_KEY"),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "~openai/gpt-sol-latest").strip(),
        openrouter_temperature=float(os.getenv("OPENROUTER_TEMPERATURE", "0.7")),
        openrouter_max_tokens=int(os.getenv("OPENROUTER_MAX_TOKENS", "220")),
        openrouter_http_referer=os.getenv("OPENROUTER_HTTP_REFERER", "").strip(),
        openrouter_app_title=os.getenv("OPENROUTER_APP_TITLE", "Lead Messenger Bot").strip(),
        openrouter_system_prompt=openrouter_system_prompt,
        openrouter_user_prompt=openrouter_user_prompt,
        openrouter_whatsapp_system_prompt=os.getenv(
            "OPENROUTER_WHATSAPP_SYSTEM_PROMPT",
            openrouter_system_prompt,
        ).strip(),
        openrouter_whatsapp_user_prompt=os.getenv(
            "OPENROUTER_WHATSAPP_USER_PROMPT",
            openrouter_user_prompt,
        ).strip(),
    )
