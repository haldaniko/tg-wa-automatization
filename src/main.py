from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from httpx import HTTPError, HTTPStatusError

from .config import Settings, load_settings
from .openrouter_client import OpenRouterClient
from .phone import get_phone_from_lead, normalize_phone
from .storage import Storage
from .telegram_sender import TelegramSender, TelegramUserNotFoundError
from .whatsapp_sender import (
    WhatsAppNotReadyError,
    WhatsAppSender,
    WhatsAppUserNotFoundError,
)


class Services:
    settings: Settings
    storage: Storage
    openrouter: OpenRouterClient
    telegram: TelegramSender
    whatsapp: WhatsAppSender


services = Services()


@asynccontextmanager
async def lifespan(app: FastAPI):
    services.settings = load_settings()
    services.storage = Storage(services.settings.database_path)
    services.storage.init()
    services.openrouter = OpenRouterClient(services.settings)
    services.telegram = TelegramSender(services.settings)
    services.whatsapp = WhatsAppSender(services.settings)
    if not services.settings.dry_run:
        await services.telegram.connect()
    yield
    await services.openrouter.close()
    await services.whatsapp.close()
    if not services.settings.dry_run:
        await services.telegram.disconnect()


app = FastAPI(title="Google Sheets Lead Messenger", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/google-sheets")
async def google_sheets_webhook(request: Request) -> dict[str, Any]:
    settings = services.settings
    payload, lead, row_key, phone = await _parse_lead_request(request)

    claim_status = services.storage.claim(row_key, phone)
    if claim_status == "sent":
        existing = services.storage.get(row_key)
        return {
            "status": "duplicate",
            "row_key": row_key,
            "phone": phone,
            "message_preview": _preview((existing or {}).get("message") or ""),
        }
    if claim_status == "processing":
        return {
            "status": "already_processing",
            "row_key": row_key,
            "phone": phone,
        }

    try:
        message = await services.openrouter.generate_message(lead, payload, phone)
        if settings.dry_run:
            telegram_result_user_id = None
            telegram_result_message_id = None
        else:
            result = await services.telegram.send_to_phone(
                phone,
                message,
                first_name=_lead_first_name(lead),
            )
            telegram_result_user_id = result.user_id
            telegram_result_message_id = result.message_id

        services.storage.mark_sent(
            row_key,
            phone,
            message,
            telegram_result_user_id,
            telegram_result_message_id,
        )
        return {
            "status": "sent" if not settings.dry_run else "dry_run",
            "row_key": row_key,
            "phone": phone,
            "telegram_user_id": telegram_result_user_id,
            "telegram_message_id": telegram_result_message_id,
            "message_preview": _preview(message),
        }
    except TelegramUserNotFoundError as exc:
        services.storage.mark_failed(row_key, phone, str(exc))
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPStatusError as exc:
        error = f"OpenRouter HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        services.storage.mark_failed(row_key, phone, error)
        raise HTTPException(status_code=502, detail=error) from exc
    except Exception as exc:
        services.storage.mark_failed(row_key, phone, str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/webhooks/google-sheets/whatsapp")
async def google_sheets_whatsapp_webhook(request: Request) -> dict[str, Any]:
    settings = services.settings
    payload, lead, row_key, phone = await _parse_lead_request(request)
    storage_key = f"whatsapp:{row_key}"

    claim_status = services.storage.claim(storage_key, phone)
    if claim_status == "sent":
        existing = services.storage.get(storage_key)
        return {
            "status": "duplicate",
            "row_key": row_key,
            "phone": phone,
            "message_preview": _preview((existing or {}).get("message") or ""),
        }
    if claim_status == "processing":
        return {
            "status": "already_processing",
            "row_key": row_key,
            "phone": phone,
        }

    try:
        message = await services.openrouter.generate_message(
            lead,
            payload,
            phone,
            system_prompt=settings.openrouter_whatsapp_system_prompt,
            user_prompt=settings.openrouter_whatsapp_user_prompt,
        )
        if settings.dry_run:
            whatsapp_message_id = None
        else:
            result = await services.whatsapp.send_to_phone(phone, message)
            whatsapp_message_id = result.message_id

        services.storage.mark_whatsapp_sent(
            storage_key,
            phone,
            message,
            whatsapp_message_id,
        )
        return {
            "status": "sent" if not settings.dry_run else "dry_run",
            "row_key": row_key,
            "phone": phone,
            "whatsapp_message_id": whatsapp_message_id,
            "message_preview": _preview(message),
        }
    except WhatsAppUserNotFoundError as exc:
        services.storage.mark_failed(storage_key, phone, str(exc))
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WhatsAppNotReadyError as exc:
        services.storage.mark_failed(storage_key, phone, str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPError as exc:
        error = _external_http_error(exc)
        services.storage.mark_failed(storage_key, phone, error)
        raise HTTPException(status_code=502, detail=error) from exc
    except Exception as exc:
        services.storage.mark_failed(storage_key, phone, str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _parse_lead_request(
    request: Request,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    settings = services.settings
    incoming_secret = request.headers.get("x-webhook-secret", "")
    if not hmac.compare_digest(incoming_secret, settings.webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be a JSON object.")

    lead = _extract_lead(payload)
    row_key = _build_row_key(payload, lead)
    try:
        raw_phone = get_phone_from_lead(lead, settings.lead_phone_field)
        phone = normalize_phone(raw_phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return payload, lead, row_key, phone


def _external_http_error(exc: HTTPError) -> str:
    request_url = str(exc.request.url) if exc.request else ""
    source = "OpenRouter" if "openrouter.ai" in request_url else "WhatsApp service"
    if isinstance(exc, HTTPStatusError):
        return f"{source} HTTP {exc.response.status_code}: {exc.response.text[:500]}"
    return f"{source} request failed: {exc}"


def _extract_lead(payload: dict[str, Any]) -> dict[str, Any]:
    lead = payload.get("lead")
    if isinstance(lead, dict):
        return lead

    values = payload.get("values")
    headers = payload.get("headers")
    if isinstance(headers, list) and isinstance(values, list):
        return {str(header): value for header, value in zip(headers, values)}

    return payload


def _build_row_key(payload: dict[str, Any], lead: dict[str, Any]) -> str:
    spreadsheet_id = str(payload.get("spreadsheetId", "")).strip()
    sheet_name = str(payload.get("sheetName", "")).strip()
    row_number = str(payload.get("rowNumber", "")).strip()
    if spreadsheet_id and sheet_name and row_number:
        return f"{spreadsheet_id}:{sheet_name}:{row_number}"

    external_id = lead.get("id") or lead.get("ID") or lead.get("lead_id") or lead.get("Lead ID")
    if external_id:
        return f"lead:{external_id}"

    phone = lead.get("phone") or lead.get("Phone") or lead.get("Телефон") or "unknown"
    return f"payload:{hash(str(payload))}:{phone}"


def _lead_first_name(lead: dict[str, Any]) -> str:
    for field in ("first_name", "First Name", "name", "Name", "Имя", "имя"):
        value = lead.get(field)
        if value is not None and str(value).strip():
            return str(value).strip().split()[0]
    return "Lead"


def _preview(text: str, limit: int = 160) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 3] + "..."
