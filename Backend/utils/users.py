"""User serialization, duplicate checks, and account cleanup."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import database


def serialize_datetime(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def serialize_user(user: dict[str, Any]) -> dict[str, Any]:
    """Return the public user shape; passwords and MongoDB IDs stay private."""

    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "email": user.get("email"),
        "created_at": serialize_datetime(user.get("created_at")),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "age": user.get("age"),
        "currency": user.get("currency"),
        "role": user.get("role", "user"),
    }


def serialize_category(category: dict[str, Any]) -> dict[str, Any]:
    return {
        "category_id": category.get("category_id"),
        "title": category.get("title"),
        "type": category.get("type"),
    }


def freeze_legacy_record_currencies(user_id: int, currency: str) -> None:
    """Pin pre-conversion records to the currency used by the old application."""

    for collection in (
        database.income_collection,
        database.expenses_collection,
        database.transactions_collection,
        database.savings_goals_collection,
    ):
        collection.update_many(
            {
                "user_id": user_id,
                "$or": [{"currency": {"$exists": False}}, {"currency": None}],
            },
            {"$set": {"currency": currency, "currency_source": "legacy_profile"}},
        )


def find_duplicate_user(
    fields: dict[str, Any], exclude_user_id: int | None = None
) -> str | None:
    clauses = []
    for field in ("username", "email"):
        if field in fields:
            clauses.append(
                {
                    field: {
                        "$regex": f"^{re.escape(str(fields[field]))}$",
                        "$options": "i",
                    }
                }
            )
    if not clauses:
        return None

    query: dict[str, Any] = {"$or": clauses}
    if exclude_user_id is not None:
        query["user_id"] = {"$ne": exclude_user_id}
    duplicate = database.users_collection.find_one(query, {"username": 1, "email": 1})
    if duplicate is None:
        return None
    if "email" in fields and duplicate.get("email", "").lower() == fields["email"].lower():
        return "email"
    return "username"


def delete_user_and_related_data(user_id: int) -> dict[str, int]:
    """Delete a user and all user-owned records, leaving global categories."""

    results = {
        "income": database.income_collection.delete_many({"user_id": user_id}).deleted_count,
        "expenses": database.expenses_collection.delete_many({"user_id": user_id}).deleted_count,
        "transactions": database.transactions_collection.delete_many({"user_id": user_id}).deleted_count,
        "savings_goals": database.savings_goals_collection.delete_many({"user_id": user_id}).deleted_count,
    }
    results["users"] = database.users_collection.delete_one({"user_id": user_id}).deleted_count
    return results
