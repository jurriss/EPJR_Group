"""Authenticated monthly income CRUD routes."""

from decimal import Decimal

from flask import Blueprint, g, jsonify, request
from pymongo.errors import PyMongoError

import database
from utils.auth import login_required
from utils.finance import as_decimal, money_text, serialize_income, stored_money


income_bp = Blueprint("income", __name__, url_prefix="/api/income")


def error_response(message, status=400, errors=None):
    return jsonify(success=False, message=message, errors=errors or {}), status


@income_bp.get("")
@login_required
def list_income():
    records = list(
        database.income_collection.find({"user_id": g.current_user["user_id"]}).sort(
            "income_id", -1
        )
    )
    currency = g.current_user.get("currency", "EUR")
    serialized = [serialize_income(record, currency, currency) for record in records]
    total = sum((as_decimal(record["converted_amount"]) for record in serialized), Decimal("0.00"))
    return jsonify(
        success=True,
        data={
            "income": serialized,
            "summary": {
                "monthly_income": money_text(total),
                "record_count": len(records),
            },
        },
    )


@income_bp.post("")
@login_required
def create_income():
    payload = request.get_json(silent=True) or {}
    try:
        amount = stored_money(payload.get("amount"))
    except ValueError as error:
        return error_response(
            "Lūdzu, izlabojiet norādītos laukus.", errors={"amount": str(error)}
        )

    document = {
        "income_id": database.generate_unique_numeric_id(
            database.income_collection, "income_id"
        ),
        "amount": amount,
        "user_id": g.current_user["user_id"],
        "currency": g.current_user.get("currency", "EUR"),
    }
    try:
        database.income_collection.insert_one(document)
    except PyMongoError:
        return error_response("Ienākumu ierakstu neizdevās saglabāt.", 500)
    currency = g.current_user.get("currency", "EUR")
    return jsonify(success=True, data={"income": serialize_income(document, currency, currency)}), 201


@income_bp.put("/<int:income_id>")
@login_required
def update_income(income_id):
    payload = request.get_json(silent=True) or {}
    try:
        amount = stored_money(payload.get("amount"))
    except ValueError as error:
        return error_response(
            "Lūdzu, izlabojiet norādītos laukus.", errors={"amount": str(error)}
        )

    updated = database.income_collection.find_one_and_update(
        {"income_id": income_id, "user_id": g.current_user["user_id"]},
        {"$set": {"amount": amount, "currency": g.current_user.get("currency", "EUR")}},
        return_document=True,
    )
    if not updated:
        return error_response("Ienākumu ieraksts nav atrasts.", 404)
    currency = g.current_user.get("currency", "EUR")
    return jsonify(success=True, data={"income": serialize_income(updated, currency, currency)})


@income_bp.delete("/<int:income_id>")
@login_required
def delete_income(income_id):
    result = database.income_collection.delete_one(
        {"income_id": income_id, "user_id": g.current_user["user_id"]}
    )
    if not result.deleted_count:
        return error_response("Ienākumu ieraksts nav atrasts.", 404)
    return jsonify(success=True, data={"income_id": income_id})
