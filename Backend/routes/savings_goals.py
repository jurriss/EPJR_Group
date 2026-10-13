"""Authenticated savings-goal CRUD routes."""

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from pymongo.errors import PyMongoError

import database
from utils.auth import login_required
from utils.finance import (
    as_decimal,
    goals_summary,
    parse_date,
    serialize_goal,
    stored_money,
    stored_nonnegative_money,
)
from utils.exchange_rates import exchange_rates


savings_goals_bp = Blueprint(
    "savings_goals", __name__, url_prefix="/api/savings-goals"
)


def error_response(message, status=400, errors=None):
    return jsonify(success=False, message=message, errors=errors or {}), status


def validate_goal(payload, existing=None, current_currency="EUR"):
    existing = existing or {}
    errors = {}
    existing_values = dict(existing)
    money_changed = "target_amount" in payload or "current_amount" in payload
    existing_currency = existing.get("currency") or current_currency
    if existing and money_changed and existing_currency != current_currency:
        existing_values["target_amount"] = exchange_rates.convert(
            as_decimal(existing.get("target_amount")), existing_currency, current_currency
        )
        existing_values["current_amount"] = exchange_rates.convert(
            as_decimal(existing.get("current_amount")), existing_currency, current_currency
        )

    name = payload.get("name", existing_values.get("name"))
    if not isinstance(name, str) or not name.strip():
        errors["name"] = "Mērķa nosaukums ir obligāts."
    elif len(name.strip()) > 80:
        errors["name"] = "Mērķa nosaukums nedrīkst pārsniegt 80 rakstzīmes."
    else:
        name = name.strip()

    try:
        target_amount = stored_money(
            payload.get("target_amount", existing_values.get("target_amount"))
        )
    except ValueError as error:
        target_amount = None
        errors["target_amount"] = str(error)

    try:
        current_amount = stored_nonnegative_money(
            payload.get("current_amount", existing_values.get("current_amount", "0"))
        )
    except ValueError as error:
        current_amount = None
        errors["current_amount"] = str(error)

    deadline_supplied = "deadline" in payload or not existing
    if deadline_supplied:
        try:
            deadline = parse_date(payload.get("deadline"))
        except ValueError as error:
            deadline = None
            errors["deadline"] = str(error)
    else:
        deadline = existing.get("deadline")

    if target_amount is not None and current_amount is not None:
        if as_decimal(current_amount) > as_decimal(target_amount):
            errors["current_amount"] = "Uzkrātā summa nedrīkst pārsniegt mērķa summu."
    existing_deadline = existing.get("deadline")
    deadline_changed = (
        not existing
        or not isinstance(existing_deadline, datetime)
        or (deadline is not None and deadline.date() != existing_deadline.date())
    )
    if deadline_changed and deadline is not None:
        if deadline.date() < datetime.now(timezone.utc).date():
            errors["deadline"] = "Termiņš nevar būt pagātnē."

    fields = {
        "name": name,
        "target_amount": target_amount,
        "current_amount": current_amount,
        "deadline": deadline,
    }
    if not existing or "target_amount" in payload or "current_amount" in payload:
        fields["currency"] = current_currency
    return fields, errors


@savings_goals_bp.get("")
@login_required
def list_savings_goals():
    records = list(
        database.savings_goals_collection.find(
            {"user_id": g.current_user["user_id"]}
        ).sort([("deadline", 1), ("savings_goals_id", 1)])
    )
    currency = g.current_user.get("currency", "EUR")
    return jsonify(success=True, data=goals_summary(records, currency, currency))


@savings_goals_bp.post("")
@login_required
def create_savings_goal():
    currency = g.current_user.get("currency", "EUR")
    fields, errors = validate_goal(request.get_json(silent=True) or {}, current_currency=currency)
    if errors:
        return error_response("Lūdzu, izlabojiet norādītos laukus.", errors=errors)
    document = {
        "savings_goals_id": database.generate_unique_numeric_id(
            database.savings_goals_collection, "savings_goals_id"
        ),
        **fields,
        "user_id": g.current_user["user_id"],
    }
    try:
        database.savings_goals_collection.insert_one(document)
    except PyMongoError:
        return error_response("Uzkrājuma mērķi neizdevās saglabāt.", 500)
    return jsonify(success=True, data={"goal": serialize_goal(document, currency, currency)}), 201


@savings_goals_bp.get("/<int:savings_goals_id>")
@login_required
def get_savings_goal(savings_goals_id):
    goal = database.savings_goals_collection.find_one(
        {
            "savings_goals_id": savings_goals_id,
            "user_id": g.current_user["user_id"],
        }
    )
    if not goal:
        return error_response("Uzkrājuma mērķis nav atrasts.", 404)
    currency = g.current_user.get("currency", "EUR")
    return jsonify(success=True, data={"goal": serialize_goal(goal, currency, currency)})


@savings_goals_bp.put("/<int:savings_goals_id>")
@login_required
def update_savings_goal(savings_goals_id):
    owner_filter = {
        "savings_goals_id": savings_goals_id,
        "user_id": g.current_user["user_id"],
    }
    existing = database.savings_goals_collection.find_one(owner_filter)
    if not existing:
        return error_response("Uzkrājuma mērķis nav atrasts.", 404)
    payload = request.get_json(silent=True) or {}
    if not payload:
        return error_response("Norādiet vismaz vienu atjaunināmo lauku.")
    currency = g.current_user.get("currency", "EUR")
    fields, errors = validate_goal(payload, existing, currency)
    if errors:
        return error_response("Lūdzu, izlabojiet norādītos laukus.", errors=errors)
    updated = database.savings_goals_collection.find_one_and_update(
        owner_filter, {"$set": fields}, return_document=True
    )
    return jsonify(success=True, data={"goal": serialize_goal(updated, currency, currency)})


@savings_goals_bp.delete("/<int:savings_goals_id>")
@login_required
def delete_savings_goal(savings_goals_id):
    result = database.savings_goals_collection.delete_one(
        {
            "savings_goals_id": savings_goals_id,
            "user_id": g.current_user["user_id"],
        }
    )
    if not result.deleted_count:
        return error_response("Uzkrājuma mērķis nav atrasts.", 404)
    return jsonify(success=True, data={"savings_goals_id": savings_goals_id})
