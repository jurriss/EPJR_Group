"""Phase 4 savings-goal integration tests."""

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
from app import app  # noqa: E402
from utils.users import delete_user_and_related_data  # noqa: E402


class Phase4SavingsGoalTests(unittest.TestCase):
    prefix = "codex_phase4_"

    @classmethod
    def setUpClass(cls):
        if not database.check_connection():
            raise unittest.SkipTest("MongoDB is not connected.")
        app.config.update(TESTING=True)

    def setUp(self):
        self.client = app.test_client()
        self.suffix = uuid.uuid4().hex[:8]
        self.deadline = (datetime.now(timezone.utc) + timedelta(days=180)).date().isoformat()

    def tearDown(self):
        users = database.users_collection.find(
            {"username": {"$regex": f"^{self.prefix}"}}, {"user_id": 1}
        )
        for user in users:
            delete_user_and_related_data(user["user_id"])

    def register(self, client=None, label="usr"):
        target = client or self.client
        payload = {
            "username": f"{self.prefix}{self.suffix}_{label[:3]}",
            "email": f"{self.prefix}{self.suffix}_{label}@example.com",
            "password": "StrongTestPassword42",
            "first_name": "Phase",
            "last_name": "Four",
            "age": 20,
            "currency": "EUR",
        }
        response = target.post("/api/auth/register", json=payload)
        self.assertEqual(response.status_code, 201)
        return response.get_json()["data"]["user"]

    def test_goal_endpoints_require_authentication(self):
        self.assertEqual(self.client.get("/api/savings-goals").status_code, 401)
        self.assertEqual(self.client.post("/api/savings-goals", json={}).status_code, 401)
        self.assertEqual(self.client.get("/api/savings-goals/1").status_code, 401)

    def test_goal_crud_calculations_validation_and_owner_isolation(self):
        owner = self.register()
        created = self.client.post(
            "/api/savings-goals",
            json={
                "name": "New laptop",
                "target_amount": "1000",
                "current_amount": "250",
                "deadline": self.deadline,
                "user_id": -1,
            },
        )
        self.assertEqual(created.status_code, 201)
        goal = created.get_json()["data"]["goal"]
        self.assertEqual(goal["percentage_complete"], "25.0")
        self.assertEqual(goal["remaining_amount"], "750.00")
        self.assertEqual(goal["status"], "in_progress")

        stored = database.savings_goals_collection.find_one(
            {"savings_goals_id": goal["savings_goals_id"]}
        )
        self.assertIsInstance(stored["target_amount"], Decimal128)
        self.assertIsInstance(stored["current_amount"], Decimal128)
        self.assertEqual(stored["user_id"], owner["user_id"])
        self.assertNotIn("percentage_complete", stored)

        listing = self.client.get("/api/savings-goals").get_json()["data"]
        self.assertEqual(listing["total_target"], "1000.00")
        self.assertEqual(listing["total_saved"], "250.00")
        self.assertEqual(listing["overall_progress"], "25.0")
        self.assertEqual(listing["active_goal_count"], 1)

        invalid = self.client.put(
            f"/api/savings-goals/{goal['savings_goals_id']}",
            json={"current_amount": "1001"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("current_amount", invalid.get_json()["errors"])

        updated = self.client.put(
            f"/api/savings-goals/{goal['savings_goals_id']}",
            json={"current_amount": "500"},
        )
        self.assertEqual(updated.status_code, 200)
        updated_goal = updated.get_json()["data"]["goal"]
        self.assertEqual(updated_goal["percentage_complete"], "50.0")
        self.assertGreater(float(updated_goal["monthly_contribution"]), 0)

        outsider = app.test_client()
        self.register(outsider, "out")
        goal_id = goal["savings_goals_id"]
        self.assertEqual(outsider.get(f"/api/savings-goals/{goal_id}").status_code, 404)
        self.assertEqual(
            outsider.put(
                f"/api/savings-goals/{goal_id}", json={"current_amount": "1"}
            ).status_code,
            404,
        )
        self.assertEqual(outsider.delete(f"/api/savings-goals/{goal_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/savings-goals/{goal_id}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
