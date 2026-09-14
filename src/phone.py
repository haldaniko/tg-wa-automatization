from __future__ import annotations

from typing import Any

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat


PHONE_FIELD_FALLBACKS = (
    "phone",
    "Phone",
    "PHONE",
    "telephone",
    "Телефон",
    "телефон",
    "Номер",
    "номер",
    "Номер телефона",
    "номер телефона",
)


def get_phone_from_lead(lead: dict[str, Any], preferred_field: str) -> str:
    candidates = (preferred_field, *PHONE_FIELD_FALLBACKS)
    for field in candidates:
        value = lead.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise ValueError(
        f"Phone number was not found. Check LEAD_PHONE_FIELD={preferred_field!r}."
    )


def normalize_phone(raw_phone: str, default_region: str) -> str:
    try:
        parsed = phonenumbers.parse(raw_phone, default_region or None)
    except NumberParseException as exc:
        raise ValueError(f"Invalid phone number {raw_phone!r}: {exc}") from exc

    if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"Invalid phone number {raw_phone!r}. Use +E.164 format if unsure.")

    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
