"""Administrator-only user management and system statistics."""

from flask import Blueprint, g, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import database
from utils.auth import admin_required
from utils.users import (
    delete_user_and_related_data,
    find_duplicate_user,
    freeze_legacy_record_currencies,
    serialize_user,
)
from utils.validators import validate_profile_payload


admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.get("/users")
@admin_required
def list_users():
    users = database.users_collection.find().sort("created_at", -1)
    return jsonify(
        success=True,
        data={"users": [serialize_user(user) for user in users]},
    )


@admin_bp.get("/users/<int:user_id>")
@admin_required
def get_user(user_id: int):
    user = database.users_collection.find_one({"user_id": user_id})
    if user is None:
        return jsonify(success=False, message="Lietotājs nav atrasts."), 404
    return jsonify(success=True, data={"user": serialize_user(user)})


@admin_bp.put("/users/<int:user_id>")
@admin_required
def update_user(user_id: int):
    user = database.users_collection.find_one({"user_id": user_id})
    if user is None:
        return jsonify(success=False, message="Lietotājs nav atrasts."), 404

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, message="Nepieciešams JSON pieprasījuma saturs."), 400

    updates = {}
    profile_payload = {
        key: payload[key]
        for key in ("username", "email", "first_name", "last_name", "age", "currency")
        if key in payload
    }
    errors = {}
    if profile_payload:
        updates, errors = validate_profile_payload(profile_payload)

    if "role" in payload:
        role = str(payload["role"]).strip().lower()
        if role not in {"user", "admin"}:
            errors["role"] = "Lomai jābūt lietotājam vai administratoram."
        elif user_id == g.current_user["user_id"] and role != "admin":
            errors["role"] = "Jūs nevarat noņemt pats savu administratora lomu."
        else:
            updates["role"] = role

    if not profile_payload and "role" not in payload:
        errors["request"] = "Norādiet vismaz vienu rediģējamu lietotāja lauku."
    if errors:
        return jsonify(success=False, message="Lietotāja dati nav derīgi.", errors=errors), 400

    duplicate_field = find_duplicate_user(updates, user_id)
    if duplicate_field:
        return jsonify(success=False, message="Šis lietotājvārds vai e-pasts jau tiek izmantots."), 409

    try:
        if updates.get("currency") and updates["currency"] != user.get("currency"):
            freeze_legacy_record_currencies(user_id, user.get("currency", "EUR"))
        database.users_collection.update_one({"user_id": user_id}, {"$set": updates})
    except DuplicateKeyError:
        return jsonify(success=False, message="Lietotājvārds vai e-pasts jau tiek izmantots."), 409
    except PyMongoError:
        return jsonify(success=False, message="Lietotāja atjaunināšana pašlaik nav pieejama."), 503
    updated_user = database.users_collection.find_one({"user_id": user_id})
    return jsonify(
        success=True,
        message="Lietotājs ir veiksmīgi atjaunināts.",
        data={"user": serialize_user(updated_user)},
    )


@admin_bp.delete("/users/<int:user_id>")
@admin_required
def delete_user(user_id: int):
    if user_id == g.current_user["user_id"]:
        return jsonify(success=False, message="Administrators šeit nevar dzēst savu kontu."), 400
    if database.users_collection.find_one({"user_id": user_id}, {"_id": 1}) is None:
        return jsonify(success=False, message="Lietotājs nav atrasts."), 404
    try:
        delete_user_and_related_data(user_id)
    except PyMongoError:
        return jsonify(success=False, message="Lietotāja dzēšana pašlaik nav pieejama."), 503
    return jsonify(success=True, message="Lietotājs un saistītie finanšu dati ir veiksmīgi dzēsti.")


@admin_bp.get("/statistics")
@admin_required
def statistics():
    return jsonify(
        success=True,
        data={
            "statistics": {
                "total_users": database.users_collection.count_documents({}),
                "total_transactions": database.transactions_collection.count_documents({}),
                "total_income_records": database.income_collection.count_documents({}),
                "total_expense_records": database.expenses_collection.count_documents({}),
                "total_savings_goals": database.savings_goals_collection.count_documents({}),
                "number_of_categories": database.categories_collection.count_documents({}),
            }
        },
    )
