"""Authenticated monthly category-budget CRUD routes."""

from flask import Blueprint, g, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import database
from utils.auth import login_required
from utils.finance import budget_usage, serialize_budget, stored_money


expenses_bp = Blueprint("expenses", __name__, url_prefix="/api/expenses")


def error_response(message, status=400, errors=None):
    return jsonify(success=False, message=message, errors=errors or {}), status


def parse_payload(payload, existing=None):
    errors = {}
    try:
        amount = stored_money(payload.get("amount"))
    except ValueError as error:
        amount = None
        errors["amount"] = str(error)
    try:
        category_id = int(payload.get("category_id"))
    except (TypeError, ValueError):
        category_id = None
        errors["category_id"] = "Izvēlieties kategoriju."
    if category_id is not None:
        category = database.categories_collection.find_one({"category_id": category_id})
        if not category:
            errors["category_id"] = "Izvēlieties derīgu kategoriju."
        elif category.get("type") != "expense":
            unchanged_legacy = existing and category_id == existing.get("category_id") and not category.get("type")
            if not unchanged_legacy:
                errors["category_id"] = "Budžetam izvēlieties izdevumu kategoriju."
    return amount, category_id, errors


def category_map(category_id):
    category = database.categories_collection.find_one({"category_id": category_id})
    return {category_id: category["title"]} if category else {}


@expenses_bp.get("")
@login_required
def list_expenses():
    try:
        summary = budget_usage(g.current_user["user_id"], request.args.get("month"), g.current_user.get("currency", "EUR"))
    except ValueError as error:
        return error_response("Nederīgs mēnesis.", errors={"month": str(error)})
    return jsonify(success=True, data=summary)


@expenses_bp.post("")
@login_required
def create_expense():
    payload = request.get_json(silent=True) or {}
    amount, category_id, errors = parse_payload(payload)
    if errors:
        return error_response("Lūdzu, izlabojiet norādītos laukus.", errors=errors)
    if database.expenses_collection.find_one(
        {"user_id": g.current_user["user_id"], "category_id": category_id}
    ):
        return error_response(
            "Šai kategorijai jau ir izveidots mēneša budžets.",
            409,
            {"category_id": "Tā vietā rediģējiet esošo budžetu."},
        )

    document = {
        "expense_id": database.generate_unique_numeric_id(
            database.expenses_collection, "expense_id"
        ),
        "amount": amount,
        "user_id": g.current_user["user_id"],
        "category_id": category_id,
        "currency": g.current_user.get("currency", "EUR"),
    }
    try:
        database.expenses_collection.insert_one(document)
    except DuplicateKeyError:
        return error_response("Šai kategorijai jau ir izveidots mēneša budžets.", 409)
    except PyMongoError:
        return error_response("Budžetu neizdevās saglabāt.", 500)
    return (
        jsonify(
            success=True,
            data={"expense": serialize_budget(document, category_map(category_id), g.current_user.get("currency", "EUR"), g.current_user.get("currency", "EUR"))},
        ),
        201,
    )


@expenses_bp.put("/<int:expense_id>")
@login_required
def update_expense(expense_id):
    owner_filter = {
        "expense_id": expense_id,
        "user_id": g.current_user["user_id"],
    }
    existing = database.expenses_collection.find_one(owner_filter)
    if not existing:
        return error_response("Budžets nav atrasts.", 404)

    payload = request.get_json(silent=True) or {}
    amount, category_id, errors = parse_payload(payload, existing)
    if errors:
        return error_response("Lūdzu, izlabojiet norādītos laukus.", errors=errors)
    duplicate = database.expenses_collection.find_one(
        {
            "user_id": g.current_user["user_id"],
            "category_id": category_id,
            "expense_id": {"$ne": expense_id},
        }
    )
    if duplicate:
        return error_response("Šai kategorijai jau ir izveidots mēneša budžets.", 409)

    try:
        updated = database.expenses_collection.find_one_and_update(
            owner_filter,
            {"$set": {"amount": amount, "category_id": category_id, "currency": g.current_user.get("currency", "EUR")}},
            return_document=True,
        )
    except DuplicateKeyError:
        return error_response("Šai kategorijai jau ir izveidots mēneša budžets.", 409)
    return jsonify(
        success=True,
        data={"expense": serialize_budget(updated, category_map(category_id), g.current_user.get("currency", "EUR"), g.current_user.get("currency", "EUR"))},
    )


@expenses_bp.delete("/<int:expense_id>")
@login_required
def delete_expense(expense_id):
    result = database.expenses_collection.delete_one(
        {"expense_id": expense_id, "user_id": g.current_user["user_id"]}
    )
    if not result.deleted_count:
        return error_response("Budžets nav atrasts.", 404)
    return jsonify(success=True, data={"expense_id": expense_id})
