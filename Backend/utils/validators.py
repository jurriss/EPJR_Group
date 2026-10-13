"""Reusable server-side validation helpers."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def validate_required_fields(
    payload: dict[str, Any] | None, required_fields: Iterable[str]
) -> list[str]:
    """Return user-facing errors for missing JSON fields."""

    if not isinstance(payload, dict):
        return ["Nepieciešams JSON pieprasījuma saturs."]

    errors: list[str] = []
    for field in required_fields:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"Lauks “{field}” ir obligāts.")
    return errors


def is_valid_email(email: Any) -> bool:
    return isinstance(email, str) and bool(EMAIL_PATTERN.fullmatch(email.strip()))


def is_positive_amount(value: Any) -> bool:
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def validate_registration_payload(
    payload: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    required = (
        "username",
        "email",
        "password",
        "first_name",
        "last_name",
        "age",
        "currency",
    )
    if not isinstance(payload, dict):
        return {}, {"request": "Nepieciešams JSON pieprasījuma saturs."}

    errors = {
        field: "Šis lauks ir obligāts."
        for field in required
        if payload.get(field) is None
        or (isinstance(payload.get(field), str) and not payload[field].strip())
    }
    cleaned, field_errors = validate_user_fields(payload, include_password=True)
    errors.update(field_errors)
    return cleaned, errors


def validate_profile_payload(
    payload: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(payload, dict):
        return {}, {"request": "Nepieciešams JSON pieprasījuma saturs."}

    allowed_fields = {"username", "email", "first_name", "last_name", "age", "currency"}
    provided = allowed_fields.intersection(payload)
    if not provided:
        return {}, {"request": "Norādiet vismaz vienu rediģējamu profila lauku."}
    return validate_user_fields({key: payload[key] for key in provided})


def validate_user_fields(
    payload: dict[str, Any], include_password: bool = False
) -> tuple[dict[str, Any], dict[str, str]]:
    cleaned: dict[str, Any] = {}
    errors: dict[str, str] = {}

    if "username" in payload:
        username = str(payload.get("username", "")).strip()
        if not 3 <= len(username) <= 30:
            errors["username"] = "Lietotājvārdam jābūt no 3 līdz 30 rakstzīmēm garam."
        elif not USERNAME_PATTERN.fullmatch(username):
            errors["username"] = "Lietotājvārdā drīkst izmantot burtus, ciparus, punktus, defises un pasvītrojumus."
        else:
            cleaned["username"] = username

    if "email" in payload:
        email = str(payload.get("email", "")).strip().lower()
        if len(email) > 254 or not is_valid_email(email):
            errors["email"] = "Ievadiet derīgu e-pasta adresi."
        else:
            cleaned["email"] = email

    for field in ("first_name", "last_name"):
        if field in payload:
            value = str(payload.get(field, "")).strip()
            if not 1 <= len(value) <= 50:
                errors[field] = "Vārdam jābūt no 1 līdz 50 rakstzīmēm garam."
            else:
                cleaned[field] = value

    if "age" in payload:
        raw_age = payload.get("age")
        try:
            age = int(raw_age)
            if isinstance(raw_age, bool) or age < 1 or age > 120:
                raise ValueError
            cleaned["age"] = age
        except (TypeError, ValueError):
            errors["age"] = "Vecumam jābūt veselam skaitlim no 1 līdz 120."

    if "currency" in payload:
        currency = str(payload.get("currency", "")).strip().upper()
        if not CURRENCY_PATTERN.fullmatch(currency):
            errors["currency"] = "Valūtai jābūt norādītai ar trīs burtu kodu, piemēram, EUR."
        else:
            cleaned["currency"] = currency

    if include_password and "password" in payload:
        password = payload.get("password")
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            errors["password"] = "Parolei jābūt no 8 līdz 128 rakstzīmēm garai."
        else:
            cleaned["password"] = password

    return cleaned, errors


def validate_category_title(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str):
        return None, "Kategorijas nosaukums ir obligāts."
    title = " ".join(value.strip().split())
    if not 2 <= len(title) <= 50:
        return None, "Kategorijas nosaukumam jābūt no 2 līdz 50 rakstzīmēm garam."
    return title, None
