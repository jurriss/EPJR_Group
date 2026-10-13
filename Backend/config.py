"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _cors_origins() -> list[str]:
    raw_origins = os.getenv("CORS_ORIGINS", "")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


class Config:
    """Base configuration for local development and future deployment."""

    MONGO_URI = os.getenv("MONGO_URI")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "pennyswise")
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    SECRET_KEY_IS_EPHEMERAL = not bool(os.getenv("SECRET_KEY"))
    MONGO_TIMEOUT_MS = int(os.getenv("MONGO_TIMEOUT_MS", "5000"))
    EXCHANGE_RATE_API_URL = os.getenv(
        "EXCHANGE_RATE_API_URL", "https://api.frankfurter.dev/v2"
    )
    EXCHANGE_RATE_CACHE_SECONDS = int(os.getenv("EXCHANGE_RATE_CACHE_SECONDS", "21600"))
    EXCHANGE_RATE_TIMEOUT_SECONDS = int(os.getenv("EXCHANGE_RATE_TIMEOUT_SECONDS", "5"))
    CORS_ORIGINS = _cors_origins()
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = 64 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _as_bool(os.getenv("SESSION_COOKIE_SECURE"))
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
