"""Final security, resilience, and acceptance integration tests."""

from __future__ import annotations

import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson.decimal128 import Decimal128


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402
from app import app, create_app  # noqa: E402
from utils.users import delete_user_and_related_data  # noqa: E402


class Phase5FinalAuditTests(unittest.TestCase):
    prefix = "codex_phase5_"
    category_prefix = "Codex Phase 5 "

    @classmethod
    def setUpClass(cls) -> None:
        if not database.check_connection():
            raise unittest.SkipTest("MongoDB is not connected.")
        app.config.update(TESTING=True)
        cls.category = database.categories_collection.find_one({"type": "expense"})
        if cls.category is None:
            raise unittest.SkipTest("At least one category is required.")

    def setUp(self) -> None:
        self.client = app.test_client()
        self.suffix = uuid.uuid4().hex[:8]

    def tearDown(self) -> None:
        users = database.users_collection.find(
            {"username": {"$regex": f"^{self.prefix}"}}, {"user_id": 1}
        )
        for user in users:
            delete_user_and_related_data(user["user_id"])
        database.categories_collection.delete_many(
            {"title": {"$regex": f"^{self.category_prefix}"}}
        )

    def registration_data(self, label: str = "user") -> dict:
        unique = f"{self.suffix}_{label}"
        return {
            "username": f"{self.prefix}{unique}",
            "email": f"{self.prefix}{unique}@example.com",
            "password": "StrongTestPassword42",
            "first_name": "Final",
            "last_name": "Tester",
            "age": 19,
            "currency": "EUR",
        }

    def register(self, client=None, label: str = "user") -> dict:
        target = client or self.client
        response = target.post("/api/auth/register", json=self.registration_data(label))
        self.assertEqual(response.status_code, 201)
        return response.get_json()["data"]["user"]

    def transaction(self, **overrides) -> dict:
        payload = {
            "amount": "10.00",
            "type": "expense",
            "description": "Final audit item",
            "date": "2026-10-05",
            "category_id": self.category["category_id"],
        }
        payload.update(overrides)
        return payload

    def test_security_headers_safe_errors_and_admin_authorization(self) -> None:
        user = self.register()

        health = self.client.get("/api/health")
        self.assertEqual(health.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(health.headers["X-Frame-Options"], "DENY")
        self.assertEqual(health.headers["Cache-Control"], "no-store")
        self.assertIn("default-src 'self'", health.headers["Content-Security-Policy"])

        blocked = self.client.post(
            "/api/auth/logout",
            headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertFalse(blocked.get_json()["success"])

        category_title = f"{self.category_prefix}{self.suffix}"
        self.assertEqual(
            self.client.post("/api/categories", json={"title": category_title}).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/admin/users").status_code, 403)

        database.users_collection.update_one(
            {"user_id": user["user_id"]}, {"$set": {"role": "admin"}}
        )
        created = self.client.post("/api/categories", json={"title": category_title})
        self.assertEqual(created.status_code, 201)
        admin_users = self.client.get("/api/admin/users")
        self.assertEqual(admin_users.status_code, 200)
        self.assertNotIn("password", str(admin_users.get_json()).lower())

        not_found = self.client.get("/api/does-not-exist")
        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(not_found.content_type, "application/json")
        self.assertFalse(not_found.get_json()["success"])
        wrong_method = self.client.patch("/api/health")
        self.assertEqual(wrong_method.status_code, 405)
        self.assertEqual(wrong_method.content_type, "application/json")

        too_large = self.client.post(
            "/api/income", json={"amount": "1", "padding": "x" * 70000}
        )
        self.assertEqual(too_large.status_code, 413)
        self.assertEqual(too_large.content_type, "application/json")

        failure_app = create_app()
        failure_app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)

        @failure_app.get("/api/test-internal-error")
        def test_internal_error():
            raise RuntimeError("private diagnostic detail")

        failure = failure_app.test_client().get("/api/test-internal-error")
        self.assertEqual(failure.status_code, 500)
        self.assertEqual(failure.get_json()["message"], "Iekšēja servera kļūda.")
        self.assertNotIn("private diagnostic detail", failure.get_data(as_text=True))

    def test_empty_data_validation_and_goal_edge_cases(self) -> None:
        user = self.register()

        self.assertEqual(self.client.get("/api/income").get_json()["data"]["income"], [])
        empty_transactions = self.client.get("/api/transactions?search=").get_json()["data"]
        self.assertEqual(empty_transactions["transactions"], [])
        self.assertEqual(empty_transactions["pagination"]["total"], 0)
        empty_budget = self.client.get("/api/expenses?month=2026-10").get_json()["data"]
        self.assertEqual(empty_budget["total_limit"], "0.00")
        self.assertEqual(empty_budget["remaining"], "0.00")
        self.assertEqual(empty_budget["notifications"], [])
        empty_goals = self.client.get("/api/savings-goals").get_json()["data"]
        self.assertEqual(empty_goals["status"], "no_goals")
        empty_overview = self.client.get("/api/overview?month=2026-10").get_json()["data"]
        self.assertEqual(empty_overview["available_balance"], "0.00")
        self.assertEqual(empty_overview["saved_amount"], "0.00")

        invalid_date = self.client.post(
            "/api/transactions", json=self.transaction(date="2026-02-30")
        )
        self.assertEqual(invalid_date.status_code, 400)
        self.assertIn("date", invalid_date.get_json()["errors"])
        invalid_category = self.client.post(
            "/api/transactions", json=self.transaction(category_id=-987654321)
        )
        self.assertEqual(invalid_category.status_code, 400)
        self.assertIn("category_id", invalid_category.get_json()["errors"])
        too_large = self.client.post(
            "/api/transactions", json=self.transaction(amount="1000000000000.00")
        )
        self.assertEqual(too_large.status_code, 400)
        maximum = self.client.post(
            "/api/transactions", json=self.transaction(amount="999999999999.99")
        )
        self.assertEqual(maximum.status_code, 201)

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        past_goal = self.client.post(
            "/api/savings-goals",
            json={
                "name": "Past goal",
                "target_amount": "100",
                "current_amount": "0",
                "deadline": yesterday,
            },
        )
        self.assertEqual(past_goal.status_code, 400)
        self.assertIn("deadline", past_goal.get_json()["errors"])

        future = (datetime.now(timezone.utc) + timedelta(days=90)).date().isoformat()
        complete = self.client.post(
            "/api/savings-goals",
            json={
                "name": "Complete goal",
                "target_amount": "100",
                "current_amount": "100",
                "deadline": future,
            },
        )
        self.assertEqual(complete.status_code, 201)
        complete_goal = complete.get_json()["data"]["goal"]
        self.assertEqual(complete_goal["percentage_complete"], "100.0")
        self.assertEqual(complete_goal["remaining_amount"], "0.00")
        self.assertEqual(complete_goal["status"], "complete")

        database.savings_goals_collection.insert_one(
            {
                "savings_goals_id": database.generate_unique_numeric_id(
                    database.savings_goals_collection, "savings_goals_id"
                ),
                "name": "Overdue imported goal",
                "target_amount": Decimal128("100.00"),
                "current_amount": Decimal128("10.00"),
                "deadline": datetime.now(timezone.utc) - timedelta(days=2),
                "user_id": user["user_id"],
            }
        )
        statuses = {
            goal["status"]
            for goal in self.client.get("/api/savings-goals").get_json()["data"]["goals"]
        }
        self.assertIn("overdue", statuses)

    def test_budget_notifications_calculations_and_user_isolation(self) -> None:
        owner = self.register()
        category_id = self.category["category_id"]
        budget = self.client.post(
            "/api/expenses", json={"amount": "100", "category_id": category_id}
        )
        self.assertEqual(budget.status_code, 201)

        warning_transaction = self.client.post(
            "/api/transactions", json=self.transaction(amount="80")
        )
        self.assertEqual(warning_transaction.status_code, 201)
        warning = self.client.get("/api/expenses?month=2026-10").get_json()["data"]
        self.assertEqual(warning["status"], "warning")
        self.assertEqual(warning["notifications"][0]["type"], "warning")
        self.assertIn("tuvojas", warning["notifications"][0]["message"])

        exceeded_transaction = self.client.post(
            "/api/transactions", json=self.transaction(amount="40")
        )
        self.assertEqual(exceeded_transaction.status_code, 201)
        exceeded = self.client.get("/api/expenses?month=2026-10").get_json()["data"]
        self.assertEqual(exceeded["amount_spent"], "120.00")
        self.assertEqual(exceeded["remaining"], "-20.00")
        self.assertEqual(exceeded["percentage_used"], "120.0")
        self.assertEqual(exceeded["status"], "exceeded")
        self.assertEqual(exceeded["notifications"][0]["type"], "danger")
        self.assertIn("pārsniegts", exceeded["notifications"][0]["message"])

        overview = self.client.get("/api/overview?month=2026-10").get_json()["data"]
        self.assertEqual(overview["available_balance"], "-120.00")
        self.assertEqual(overview["current_month_income"], "0.00")
        self.assertEqual(overview["current_month_spending"], "120.00")
        self.assertEqual(overview["net_cash_flow"], "-120.00")
        self.assertEqual(overview["saved_amount"], "0.00")
        self.assertEqual(len(overview["spending_trend"]), 6)

        owner_income = self.client.post("/api/income", json={"amount": "50"})
        self.assertEqual(owner_income.status_code, 201)
        goal_deadline = (datetime.now(timezone.utc) + timedelta(days=60)).date().isoformat()
        owner_goal = self.client.post(
            "/api/savings-goals",
            json={
                "name": "Private goal",
                "target_amount": "500",
                "current_amount": "25",
                "deadline": goal_deadline,
            },
        )
        self.assertEqual(owner_goal.status_code, 201)

        outsider = app.test_client()
        self.register(outsider, "outsider")
        self.assertEqual(outsider.get("/api/income").get_json()["data"]["income"], [])
        self.assertEqual(
            outsider.get("/api/expenses?month=2026-10").get_json()["data"]["categories"],
            [],
        )
        self.assertEqual(
            outsider.get("/api/transactions").get_json()["data"]["transactions"], []
        )
        self.assertEqual(
            outsider.get("/api/savings-goals").get_json()["data"]["goals"], []
        )
        self.assertEqual(
            outsider.get(
                f"/api/transactions/{warning_transaction.get_json()['data']['transaction']['transaction_id']}"
            ).status_code,
            404,
        )
        self.assertEqual(
            database.transactions_collection.count_documents(
                {"user_id": owner["user_id"]}
            ),
            2,
        )

    def test_required_database_indexes_exist(self) -> None:
        def keys(collection):
            return {
                tuple(index["key"])
                for index in collection.index_information().values()
            }

        user_indexes = database.users_collection.index_information()
        self.assertIn((("user_id", 1),), keys(database.users_collection))
        self.assertIn((("username", 1),), keys(database.users_collection))
        self.assertIn((("email", 1),), keys(database.users_collection))
        for details in user_indexes.values():
            if details["key"] in (
                [("user_id", 1)],
                [("username", 1)],
                [("email", 1)],
            ):
                self.assertTrue(details.get("unique"))

        self.assertIn((("user_id", 1),), keys(database.transactions_collection))
        self.assertIn((("category_id", 1),), keys(database.transactions_collection))
        self.assertIn(
            (("user_id", 1), ("date", 1)), keys(database.transactions_collection)
        )
        self.assertIn((("user_id", 1),), keys(database.income_collection))
        self.assertIn((("user_id", 1),), keys(database.expenses_collection))
        self.assertIn((("category_id", 1),), keys(database.expenses_collection))
        self.assertIn((("user_id", 1),), keys(database.savings_goals_collection))
        self.assertIn((("category_id", 1),), keys(database.categories_collection))


if __name__ == "__main__":
    unittest.main(verbosity=2)
