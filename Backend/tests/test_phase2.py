"""Phase 2 integration tests against the configured MongoDB database."""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import database  # noqa: E402
from app import app  # noqa: E402
from utils.users import delete_user_and_related_data  # noqa: E402


class Phase2IntegrationTests(unittest.TestCase):
    prefix = "codex_phase2_"
    category_prefix = "Codex Phase 2 "

    @classmethod
    def setUpClass(cls) -> None:
        if not database.check_connection():
            raise unittest.SkipTest("MongoDB is not connected.")
        app.config.update(TESTING=True)

    def setUp(self) -> None:
        self.client = app.test_client()
        self.suffix = uuid.uuid4().hex[:6]

    def tearDown(self) -> None:
        users = list(
            database.users_collection.find(
                {"username": {"$regex": f"^{self.prefix}"}}, {"user_id": 1}
            )
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
            "first_name": "Phase",
            "last_name": "Tester",
            "age": 19,
            "currency": "EUR",
        }

    def register(self, client=None, label: str = "user"):
        target_client = client or self.client
        payload = self.registration_data(label)
        response = target_client.post("/api/auth/register", json=payload)
        return response, payload

    def test_registration_login_logout_and_session(self) -> None:
        response, payload = self.register()
        self.assertEqual(response.status_code, 201)
        response_data = response.get_json()
        self.assertNotIn("password", str(response_data).lower())

        stored_user = database.users_collection.find_one({"email": payload["email"]})
        self.assertIsNotNone(stored_user)
        self.assertNotEqual(stored_user["password"], payload["password"])
        self.assertEqual(stored_user["role"], "user")

        duplicate = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

        wrong_password = self.client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": "DefinitelyWrong"},
        )
        self.assertEqual(wrong_password.status_code, 401)

        login = self.client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_profile_update_and_account_deletion_cascade(self) -> None:
        response, _ = self.register()
        user_id = response.get_json()["data"]["user"]["user_id"]

        update = self.client.put(
            "/api/users/me",
            json={
                "username": f"{self.prefix}{self.suffix}_updated",
                "email": f"{self.prefix}{self.suffix}_updated@example.com",
                "first_name": "Updated",
                "last_name": "Student",
                "age": 20,
                "currency": "USD",
            },
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.get_json()["data"]["user"]["first_name"], "Updated")

        database.income_collection.insert_one({"income_id": database.generate_unique_numeric_id(database.income_collection, "income_id"), "amount": 10, "user_id": user_id})
        database.expenses_collection.insert_one({"expense_id": database.generate_unique_numeric_id(database.expenses_collection, "expense_id"), "amount": 2, "user_id": user_id, "category_id": 0})
        database.transactions_collection.insert_one({"transaction_id": database.generate_unique_numeric_id(database.transactions_collection, "transaction_id"), "amount": 2, "user_id": user_id, "category_id": 0})
        database.savings_goals_collection.insert_one({"savings_goals_id": database.generate_unique_numeric_id(database.savings_goals_collection, "savings_goals_id"), "name": "Test", "target_amount": 5, "current_amount": 0, "user_id": user_id})

        category_count_before = database.categories_collection.count_documents({})
        deletion = self.client.delete("/api/users/me")
        self.assertEqual(deletion.status_code, 200)
        self.assertIsNone(database.users_collection.find_one({"user_id": user_id}))
        for collection in (
            database.income_collection,
            database.expenses_collection,
            database.transactions_collection,
            database.savings_goals_collection,
        ):
            self.assertEqual(collection.count_documents({"user_id": user_id}), 0)
        self.assertEqual(
            database.categories_collection.count_documents({}), category_count_before
        )
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_category_create_update_use_guard_and_delete(self) -> None:
        response, _ = self.register()
        user_id = response.get_json()["data"]["user"]["user_id"]
        self.assertEqual(
            self.client.post("/api/categories", json={"title": "Not allowed"}).status_code,
            403,
        )
        database.users_collection.update_one(
            {"user_id": user_id}, {"$set": {"role": "admin"}}
        )
        title = f"{self.category_prefix}{self.suffix}"
        created = self.client.post("/api/categories", json={"title": title})
        self.assertEqual(created.status_code, 201)
        category_id = created.get_json()["data"]["category"]["category_id"]

        duplicate = self.client.post("/api/categories", json={"title": title.lower()})
        self.assertEqual(duplicate.status_code, 409)

        updated_title = f"{title} Updated"
        updated = self.client.put(
            f"/api/categories/{category_id}", json={"title": updated_title}
        )
        self.assertEqual(updated.status_code, 200)

        transaction_id = database.generate_unique_numeric_id(
            database.transactions_collection, "transaction_id"
        )
        database.transactions_collection.insert_one(
            {"transaction_id": transaction_id, "category_id": category_id, "user_id": -1}
        )
        in_use = self.client.delete(f"/api/categories/{category_id}")
        self.assertEqual(in_use.status_code, 409)
        database.transactions_collection.delete_one({"transaction_id": transaction_id})

        deleted = self.client.delete(f"/api/categories/{category_id}")
        self.assertEqual(deleted.status_code, 200)

    def test_admin_authorization_and_user_management(self) -> None:
        admin_response, _ = self.register(label="admin")
        admin_id = admin_response.get_json()["data"]["user"]["user_id"]

        self.assertEqual(self.client.get("/api/admin/users").status_code, 403)
        database.users_collection.update_one(
            {"user_id": admin_id}, {"$set": {"role": "admin"}}
        )
        self.assertEqual(self.client.get("/api/admin/statistics").status_code, 200)

        managed_client = app.test_client()
        managed_response, _ = self.register(client=managed_client, label="managed")
        managed_id = managed_response.get_json()["data"]["user"]["user_id"]

        users_response = self.client.get("/api/admin/users")
        self.assertEqual(users_response.status_code, 200)
        self.assertNotIn("password", str(users_response.get_json()).lower())
        self.assertEqual(
            self.client.get(f"/api/admin/users/{managed_id}").status_code, 200
        )
        self.assertEqual(
            self.client.put(
                f"/api/admin/users/{managed_id}", json={"role": "admin"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete(f"/api/admin/users/{managed_id}").status_code, 200
        )
        self.assertIsNone(database.users_collection.find_one({"user_id": managed_id}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
