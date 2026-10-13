"""Phase 3 integration tests against the configured MongoDB database."""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path

from bson.decimal128 import Decimal128


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402
from app import app  # noqa: E402
from utils.users import delete_user_and_related_data  # noqa: E402


class Phase3IntegrationTests(unittest.TestCase):
    prefix = "codex_phase3_"

    @classmethod
    def setUpClass(cls) -> None:
        if not database.check_connection():
            raise unittest.SkipTest("MongoDB is not connected.")
        app.config.update(TESTING=True)
        cls.categories = list(
            database.categories_collection.find({"type": "expense"}).sort("title", 1).limit(2)
        )
        cls.income_category = database.categories_collection.find_one({"type": "income"})
        if len(cls.categories) < 2 or cls.income_category is None:
            raise unittest.SkipTest("Typed seeded categories are required.")

    def setUp(self) -> None:
        self.client = app.test_client()
        self.suffix = uuid.uuid4().hex[:8]

    def tearDown(self) -> None:
        users = database.users_collection.find(
            {"username": {"$regex": f"^{self.prefix}"}}, {"user_id": 1}
        )
        for user in users:
            delete_user_and_related_data(user["user_id"])

    def registration_data(self, label="user"):
        unique = f"{self.suffix}_{label}"
        return {
            "username": f"{self.prefix}{self.suffix}_{label[:3]}",
            "email": f"{self.prefix}{unique}@example.com",
            "password": "StrongTestPassword42",
            "first_name": "Phase",
            "last_name": "Three",
            "age": 19,
            "currency": "EUR",
        }

    def register(self, client=None, label="user"):
        target = client or self.client
        response = target.post("/api/auth/register", json=self.registration_data(label))
        self.assertEqual(response.status_code, 201)
        return response.get_json()["data"]["user"]

    def transaction(self, **overrides):
        payload = {
            "amount": "25.50",
            "type": "expense",
            "description": "Lunch with friends",
            "date": "2026-09-15",
            "category_id": self.categories[0]["category_id"],
        }
        payload.update(overrides)
        return payload

    def test_authentication_required_for_all_financial_endpoints(self):
        for method, endpoint in (
            ("get", "/api/income"),
            ("post", "/api/income"),
            ("get", "/api/expenses"),
            ("post", "/api/expenses"),
            ("get", "/api/transactions"),
            ("post", "/api/transactions"),
            ("get", "/api/transactions/123"),
            ("get", "/api/overview"),
        ):
            response = getattr(self.client, method)(endpoint, json={} if method == "post" else None)
            self.assertEqual(response.status_code, 401, endpoint)

    def test_income_crud_and_cross_user_protection(self):
        owner = self.register()
        created = self.client.post(
            "/api/income", json={"amount": "1200.10", "user_id": -1}
        )
        self.assertEqual(created.status_code, 201)
        income = created.get_json()["data"]["income"]
        self.assertEqual(income["amount"], "1200.10")

        stored = database.income_collection.find_one({"income_id": income["income_id"]})
        self.assertIsInstance(stored["amount"], Decimal128)
        self.assertEqual(stored["user_id"], owner["user_id"])

        listing = self.client.get("/api/income").get_json()["data"]
        self.assertEqual(listing["summary"]["monthly_income"], "1200.10")
        updated = self.client.put(
            f"/api/income/{income['income_id']}", json={"amount": "1300.25"}
        )
        self.assertEqual(updated.get_json()["data"]["income"]["amount"], "1300.25")

        outsider = app.test_client()
        self.register(outsider, "outsider")
        self.assertEqual(
            outsider.put(
                f"/api/income/{income['income_id']}", json={"amount": "1"}
            ).status_code,
            404,
        )
        self.assertEqual(outsider.get("/api/income").get_json()["data"]["income"], [])
        self.assertEqual(
            self.client.delete(f"/api/income/{income['income_id']}").status_code, 200
        )

    def test_budget_crud_and_monthly_usage(self):
        self.register()
        category_id = self.categories[0]["category_id"]
        created = self.client.post(
            "/api/expenses", json={"amount": "500", "category_id": category_id}
        )
        self.assertEqual(created.status_code, 201)
        budget = created.get_json()["data"]["expense"]
        self.assertEqual(
            self.client.post(
                "/api/expenses", json={"amount": "600", "category_id": category_id}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                "/api/transactions",
                json=self.transaction(amount="125", category_id=category_id),
            ).status_code,
            201,
        )

        usage = self.client.get("/api/expenses?month=2026-09").get_json()["data"]
        self.assertEqual(usage["total_limit"], "500.00")
        self.assertEqual(usage["amount_spent"], "125.00")
        self.assertEqual(usage["percentage_used"], "25.0")
        self.assertEqual(usage["categories"][0]["status"], "on_track")

        updated = self.client.put(
            f"/api/expenses/{budget['expense_id']}",
            json={"amount": "100", "category_id": category_id},
        )
        self.assertEqual(updated.status_code, 200)
        usage = self.client.get("/api/expenses?month=2026-09").get_json()["data"]
        self.assertEqual(usage["status"], "exceeded")

        outsider = app.test_client()
        self.register(outsider, "budget_outsider")
        self.assertEqual(
            outsider.delete(f"/api/expenses/{budget['expense_id']}").status_code, 404
        )
        self.assertEqual(
            self.client.delete(f"/api/expenses/{budget['expense_id']}").status_code, 200
        )

    def test_transaction_crud_search_filters_and_pagination(self):
        owner = self.register()
        category_one = self.categories[0]["category_id"]
        category_two = self.categories[1]["category_id"]
        records = []
        for payload in (
            self.transaction(
                amount="2000", type="income", description="September salary",
                date="2026-09-01", category_id=self.income_category["category_id"],
            ),
            self.transaction(
                amount="4.75", description="Morning coffee",
                date="2026-09-20", category_id=category_two,
            ),
            self.transaction(
                amount="30", description="August train",
                date="2026-08-10", category_id=category_one,
            ),
        ):
            response = self.client.post("/api/transactions", json=payload)
            self.assertEqual(response.status_code, 201)
            records.append(response.get_json()["data"]["transaction"])

        coffee_id = records[1]["transaction_id"]
        fetched = self.client.get(f"/api/transactions/{coffee_id}")
        self.assertEqual(fetched.get_json()["data"]["transaction"]["description"], "Morning coffee")
        updated = self.client.put(
            f"/api/transactions/{coffee_id}", json={"description": "Coffee and cake"}
        )
        self.assertEqual(updated.status_code, 200)

        cases = (
            ("search=cake", 1),
            ("type=income", 1),
            (f"category_id={category_two}", 1),
            ("month=2026-09", 2),
            ("from=2026-09-15&to=2026-09-30", 1),
        )
        for query, expected in cases:
            data = self.client.get(f"/api/transactions?{query}").get_json()["data"]
            self.assertEqual(data["pagination"]["total"], expected, query)

        page_one = self.client.get("/api/transactions?limit=1&page=1").get_json()["data"]
        page_two = self.client.get("/api/transactions?limit=1&page=2").get_json()["data"]
        self.assertEqual(page_one["pagination"]["total_pages"], 3)
        self.assertNotEqual(
            page_one["transactions"][0]["transaction_id"],
            page_two["transactions"][0]["transaction_id"],
        )
        stored = database.transactions_collection.find_one({"transaction_id": coffee_id})
        self.assertIsInstance(stored["amount"], Decimal128)
        self.assertEqual(stored["user_id"], owner["user_id"])

        outsider = app.test_client()
        self.register(outsider, "transaction_outsider")
        self.assertEqual(outsider.get(f"/api/transactions/{coffee_id}").status_code, 404)
        self.assertEqual(
            outsider.delete(f"/api/transactions/{coffee_id}").status_code, 404
        )
        self.assertEqual(self.client.delete(f"/api/transactions/{coffee_id}").status_code, 200)

    def test_overview_monthly_calculations_and_six_month_trend(self):
        self.register()
        category_id = self.categories[0]["category_id"]
        self.client.post(
            "/api/expenses", json={"amount": "400", "category_id": category_id}
        )
        activity = (
            ("2026-04-02", "income", "50"),
            ("2026-05-02", "income", "60"),
            ("2026-06-02", "expense", "10"),
            ("2026-07-02", "income", "70"),
            ("2026-08-02", "income", "100"),
            ("2026-08-03", "expense", "40"),
            ("2026-09-02", "income", "200"),
            ("2026-09-03", "expense", "75"),
        )
        for index, (date, kind, amount) in enumerate(activity):
            response = self.client.post(
                "/api/transactions",
                json=self.transaction(
                    date=date,
                    type=kind,
                    amount=amount,
                    description=f"Trend item {index}",
                    category_id=(
                        self.income_category["category_id"]
                        if kind == "income" else category_id
                    ),
                ),
            )
            self.assertEqual(response.status_code, 201)

        response = self.client.get("/api/overview?month=2026-09")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["current_month_income"], "200.00")
        self.assertEqual(data["current_month_spending"], "75.00")
        self.assertEqual(data["net_cash_flow"], "125.00")
        self.assertEqual(data["saved_amount"], "125.00")
        self.assertEqual(data["income_percentage_change"], "100.0")
        self.assertEqual(data["expense_percentage_change"], "87.5")
        self.assertEqual(len(data["spending_trend"]), 6)
        self.assertEqual(data["spending_trend"][0]["month"], "2026-04")
        self.assertEqual(data["spending_trend"][-1]["month"], "2026-09")
        self.assertEqual(data["current_budget"]["amount_spent"], "75.00")
        self.assertEqual(data["recent_transactions"][0]["date"], "2026-09-03")


if __name__ == "__main__":
    unittest.main()
