"""Focused tests for typed categories and real currency conversion."""

from __future__ import annotations

import json
import sys
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from bson.decimal128 import Decimal128


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402
from app import app  # noqa: E402
from utils.exchange_rates import ExchangeRateError, ExchangeRateService, exchange_rates  # noqa: E402
from utils.finance import serialize_transaction  # noqa: E402
from utils.users import delete_user_and_related_data  # noqa: E402


class _Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ExchangeRateUnitTests(unittest.TestCase):
    def test_conversion_uses_decimal_rounding_and_cache(self):
        service = ExchangeRateService(ttl_seconds=3600)
        response = json.dumps({"rate": 1.23456}).encode()
        with patch("utils.exchange_rates.urlopen", return_value=_Response(response)) as request:
            self.assertEqual(service.convert(Decimal("10.00"), "EUR", "USD"), Decimal("12.35"))
            self.assertEqual(service.convert(Decimal("2.00"), "EUR", "USD"), Decimal("2.47"))
        self.assertEqual(request.call_count, 1)

    def test_provider_failure_uses_stale_cache_but_never_invents_rate(self):
        service = ExchangeRateService(ttl_seconds=0)
        response = json.dumps({"rate": 0.8}).encode()
        with patch("utils.exchange_rates.urlopen", return_value=_Response(response)):
            self.assertEqual(service.get_rate("EUR", "GBP"), Decimal("0.8"))
        with patch("utils.exchange_rates.urlopen", side_effect=URLError("offline")):
            self.assertEqual(service.get_rate("EUR", "GBP"), Decimal("0.8"))

        empty_service = ExchangeRateService()
        with patch("utils.exchange_rates.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(ExchangeRateError):
                empty_service.get_rate("EUR", "GBP")

    def test_serialization_preserves_original_money(self):
        record = {
            "transaction_id": 1,
            "amount": Decimal128("10.00"),
            "currency": "USD",
            "type": "income",
            "description": "Tests",
            "date": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "category_id": 2,
        }
        with patch.object(exchange_rates, "convert", return_value=Decimal("8.57")):
            result = serialize_transaction(record, {2: "Alga"}, "EUR", "EUR")
        self.assertEqual(result["amount"], "10.00")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["converted_amount"], "8.57")
        self.assertEqual(record["amount"], Decimal128("10.00"))


class CurrencyAndCategoryIntegrationTests(unittest.TestCase):
    prefix = "cc_"

    @classmethod
    def setUpClass(cls):
        if not database.check_connection():
            raise unittest.SkipTest("MongoDB is not connected.")
        app.config.update(TESTING=True)
        database.seed_default_categories()
        cls.income_category = database.categories_collection.find_one({"type": "income"})
        cls.expense_categories = list(
            database.categories_collection.find({"type": "expense"}).limit(2)
        )
        if not cls.income_category or len(cls.expense_categories) < 2:
            raise unittest.SkipTest("Typed default categories are required.")

    def setUp(self):
        self.client = app.test_client()
        self.suffix = uuid.uuid4().hex[:10]
        response = self.client.post(
            "/api/auth/register",
            json={
                "username": f"{self.prefix}{self.suffix}",
                "email": f"{self.prefix}{self.suffix}@example.com",
                "password": "StrongTestPassword42",
                "first_name": "Valūtas",
                "last_name": "Tests",
                "age": 20,
                "currency": "EUR",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.user = response.get_json()["data"]["user"]

    def tearDown(self):
        delete_user_and_related_data(self.user["user_id"])

    def transaction_payload(self, transaction_type, category_id, amount="10.00"):
        return {
            "amount": amount,
            "type": transaction_type,
            "description": "Kategorijas pārbaude",
            "date": datetime.now(timezone.utc).date().isoformat(),
            "category_id": category_id,
        }

    def test_category_types_creation_filtering_and_editing(self):
        income_id = self.income_category["category_id"]
        expense_one = self.expense_categories[0]["category_id"]
        expense_two = self.expense_categories[1]["category_id"]

        wrong = self.client.post(
            "/api/transactions",
            json=self.transaction_payload("expense", income_id),
        )
        self.assertEqual(wrong.status_code, 400)
        self.assertIn("category_id", wrong.get_json()["errors"])

        created = self.client.post(
            "/api/transactions",
            json=self.transaction_payload("expense", expense_one),
        )
        self.assertEqual(created.status_code, 201)
        transaction_id = created.get_json()["data"]["transaction"]["transaction_id"]

        filtered = self.client.get(f"/api/transactions?category_id={expense_one}")
        self.assertEqual(filtered.get_json()["data"]["pagination"]["total"], 1)
        updated = self.client.put(
            f"/api/transactions/{transaction_id}",
            json={"category_id": expense_two},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["data"]["transaction"]["category_id"], expense_two)

        rejected_edit = self.client.put(
            f"/api/transactions/{transaction_id}",
            json={"category_id": income_id},
        )
        self.assertEqual(rejected_edit.status_code, 400)

        income_categories = self.client.get("/api/categories?type=income").get_json()["data"]["categories"]
        self.assertTrue(income_categories)
        self.assertTrue(all(item["type"] == "income" for item in income_categories))

    def test_currency_change_converts_totals_and_preserves_original(self):
        expense_id = self.expense_categories[0]["category_id"]
        created = self.client.post(
            "/api/transactions",
            json=self.transaction_payload("expense", expense_id, "10.00"),
        )
        transaction_id = created.get_json()["data"]["transaction"]["transaction_id"]
        profile = self.client.put("/api/users/me", json={"currency": "USD"})
        self.assertEqual(profile.status_code, 200)

        with patch.object(exchange_rates, "get_rate", return_value=Decimal("1.25")):
            overview = self.client.get(
                f"/api/overview?month={datetime.now(timezone.utc):%Y-%m}"
            )
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.get_json()["data"]["current_month_spending"], "12.50")
        stored = database.transactions_collection.find_one({"transaction_id": transaction_id})
        self.assertEqual(stored["amount"], Decimal128("10.00"))
        self.assertEqual(stored["currency"], "EUR")

    def test_missing_rate_returns_latvian_503_and_legacy_data_is_frozen(self):
        transaction_id = database.generate_unique_numeric_id(
            database.transactions_collection, "transaction_id"
        )
        database.transactions_collection.insert_one(
            {
                "transaction_id": transaction_id,
                "amount": Decimal128("7.00"),
                "type": "expense",
                "description": "Mantojuma ieraksts",
                "date": datetime.now(timezone.utc),
                "category_id": self.expense_categories[0]["category_id"],
                "user_id": self.user["user_id"],
            }
        )
        self.assertEqual(
            self.client.put("/api/users/me", json={"currency": "USD"}).status_code,
            200,
        )
        stored = database.transactions_collection.find_one({"transaction_id": transaction_id})
        self.assertEqual(stored["currency"], "EUR")
        self.assertEqual(stored["currency_source"], "legacy_profile")

        with patch.object(
            exchange_rates,
            "get_rate",
            side_effect=ExchangeRateError("Valūtas kursu pašlaik neizdevās iegūt."),
        ):
            response = self.client.get("/api/transactions")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Valūtas kursu", response.get_json()["message"])

    def test_default_category_seed_is_idempotent(self):
        first = database.seed_default_categories()
        second = database.seed_default_categories()
        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        for title, category_type in database.DEFAULT_CATEGORIES:
            self.assertEqual(
                database.categories_collection.count_documents(
                    {"title": title, "type": category_type}
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
