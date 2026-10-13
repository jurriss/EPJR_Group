"""Cached decimal currency conversion using Frankfurter reference rates."""

from __future__ import annotations

import json
import threading
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MONEY_QUANTUM = Decimal("0.01")
RATE_TTL_SECONDS = 6 * 60 * 60
DEFAULT_API_URL = "https://api.frankfurter.dev/v2"


class ExchangeRateError(RuntimeError):
    """Raised when a trustworthy conversion rate cannot be obtained."""


class ExchangeRateService:
    def __init__(self, api_url=DEFAULT_API_URL, ttl_seconds=RATE_TTL_SECONDS, timeout=5):
        self.api_url = api_url.rstrip("/")
        self.ttl_seconds = ttl_seconds
        self.timeout = timeout
        self._cache: dict[tuple[str, str], tuple[Decimal, float]] = {}
        self._lock = threading.Lock()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def get_rate(self, base: str, quote: str) -> Decimal:
        base = str(base or "").upper()
        quote = str(quote or "").upper()
        if len(base) != 3 or len(quote) != 3:
            raise ExchangeRateError("Valūtas kods nav derīgs.")
        if base == quote:
            return Decimal("1")

        key = (base, quote)
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[1] < self.ttl_seconds:
                return cached[0]

        try:
            request = Request(
                f"{self.api_url}/rate/{base}/{quote}",
                headers={"Accept": "application/json", "User-Agent": "Pennywise/1.0"},
            )
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
            rate = Decimal(str(payload.get("rate")))
            if not rate.is_finite() or rate <= 0:
                raise InvalidOperation
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError,
                InvalidOperation, json.JSONDecodeError) as error:
            with self._lock:
                stale = self._cache.get(key)
            if stale:
                return stale[0]
            raise ExchangeRateError(
                "Valūtas kursu pašlaik neizdevās iegūt. Lūdzu, mēģiniet vēlreiz vēlāk."
            ) from error

        with self._lock:
            self._cache[key] = (rate, now)
        return rate

    def convert(self, amount: Decimal, base: str, quote: str) -> Decimal:
        rate = self.get_rate(base, quote)
        return (amount * rate).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


exchange_rates = ExchangeRateService()

