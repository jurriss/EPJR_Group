"""Authenticated transaction CRUD, filtering, search, and pagination."""

from datetime import timedelta
import math
import re

from flask import Blueprint, g, jsonify, request
from pymongo.errors import PyMongoError

import database
from utils.auth import login_required
from utils.finance import (
    category_title_map,
    month_bounds,
    parse_date,
    serialize_transaction,
    stored_money,
)


transactions_bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")
TRANSACTION_TYPES = {"income", "expense"}


def error_response(message, status=400, errors=None):
    return jsonify(success=False, message=message, errors=errors or {}), status


def parse_positive_int(value, field, default, maximum=None):
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Laukam “{field}” jābūt veselam skaitlim.") from error
    if parsed < 1 or (maximum is not None and parsed > maximum):
        if maximum:
            raise ValueError(f"Lauka “{field}” vērtībai jābūt no 1 līdz {maximum}.")
        raise ValueError(f"Lauka “{field}” vērtībai jābūt lielākai par nulli.")
    return parsed


def validate_fields(payload, existing=None, current_currency="EUR"):
    errors = {}
    existing = existing or {}

    try:
        amount = stored_money(payload.get("amount", existing.get("amount")))
    except ValueError as error:
        amount = None
        errors["amount"] = str(error)

    transaction_type = payload.get("type", existing.get("type"))
    if transaction_type not in TRANSACTION_TYPES:
        errors["type"] = "Veidam jābūt ienākumiem vai izdevumiem."

    description = payload.get("description", existing.get("description"))
    if not isinstance(description, str) or not description.strip():
        errors["description"] = "Apraksts ir obligāts."
    elif len(description.strip()) > 160:
        errors["description"] = "Apraksts nedrīkst pārsniegt 160 rakstzīmes."
    else:
        description = description.strip()

    if "date" in payload or not existing:
        try:
            transaction_date = parse_date(payload.get("date"))
        except ValueError as error:
            transaction_date = None
            errors["date"] = str(error)
    else:
        transaction_date = existing.get("date")

    try:
        category_id = int(payload.get("category_id", existing.get("category_id")))
    except (TypeError, ValueError):
        category_id = None
        errors["category_id"] = "Izvēlieties kategoriju."
    category = None
    if category_id is not None:
        category = database.categories_collection.find_one({"category_id": category_id})
        if not category:
            errors["category_id"] = "Izvēlieties derīgu kategoriju."
        elif category.get("type") != transaction_type:
            unchanged_legacy = existing and category_id == existing.get("category_id") and transaction_type == existing.get("type") and not category.get("type")
            if not unchanged_legacy:
                errors["category_id"] = "Izvēlieties darījuma veidam atbilstošu kategoriju."

    fields = {
        "amount": amount,
        "type": transaction_type,
        "description": description,
        "date": transaction_date,
        "category_id": category_id,
    }
    if not existing or "amount" in payload:
        fields["currency"] = current_currency
    return fields, errors


def build_list_query():
    errors = {}
    try:
        page = parse_positive_int(request.args.get("page"), "page", 1)
        limit = parse_positive_int(request.args.get("limit"), "limit", 10, 100)
    except ValueError as error:
        return None, None, None, {"pagination": str(error)}

    query = {"user_id": g.current_user["user_id"]}
    search = (request.args.get("search") or "").strip()
    if len(search) > 100:
        errors["search"] = "Meklēšanas teksts nedrīkst pārsniegt 100 rakstzīmes."
    elif search:
        query["description"] = {"$regex": re.escape(search), "$options": "i"}

    transaction_type = request.args.get("type")
    if transaction_type:
        if transaction_type not in TRANSACTION_TYPES:
            errors["type"] = "Veidam jābūt ienākumiem vai izdevumiem."
        else:
            query["type"] = transaction_type

    category_value = request.args.get("category_id")
    if category_value:
        try:
            query["category_id"] = int(category_value)
        except ValueError:
            errors["category_id"] = "Kategorijai jābūt norādītai ar veselu skaitli."

    lower_bounds = []
    upper_bounds = []
    month = request.args.get("month")
    if month:
        try:
            start, end, _ = month_bounds(month)
            lower_bounds.append(start)
            upper_bounds.append(end)
        except ValueError as error:
            errors["month"] = str(error)

    from_value = request.args.get("from")
    if from_value:
        try:
            lower_bounds.append(parse_date(from_value))
        except ValueError as error:
            errors["from"] = str(error)
    to_value = request.args.get("to")
    if to_value:
        try:
            upper_bounds.append(parse_date(to_value) + timedelta(days=1))
        except ValueError as error:
            errors["to"] = str(error)

    if lower_bounds or upper_bounds:
        date_query = {}
        if lower_bounds:
            date_query["$gte"] = max(lower_bounds)
        if upper_bounds:
            date_query["$lt"] = min(upper_bounds)
        if date_query.get("$gte") and date_query.get("$lt") and date_query["$gte"] >= date_query["$lt"]:
            errors["date"] = "Atlasītais datumu diapazons ir tukšs."
        query["date"] = date_query

    return query, page, limit, errors


@transactions_bp.get("")
@login_required
def list_transactions():
    query, page, limit, errors = build_list_query()
    if errors:
        return error_response("Lūdzu, izlabojiet filtrus.", errors=errors)

    total = database.transactions_collection.count_documents(query)
    records = list(
        database.transactions_collection.find(query)
        .sort([("date", -1), ("transaction_id", -1)])
        .skip((page - 1) * limit)
        .limit(limit)
    )
    titles = category_title_map()
    return jsonify(
        success=True,
        data={
            "transactions": [
                serialize_transaction(record, titles, g.current_user.get("currency", "EUR"), g.current_user.get("currency", "EUR")) for record in records
            ],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": math.ceil(total / limit) if total else 0,
            },
        },
    )


@transactions_bp.post("")
@login_required
def create_transaction():
    fields, errors = validate_fields(request.get_json(silent=True) or {}, current_currency=g.current_user.get("currency", "EUR"))
    if errors:
        return error_response("Lūdzu, izlabojiet norādītos laukus.", errors=errors)
    document = {
        "transaction_id": database.generate_unique_numeric_id(
            database.transactions_collection, "transaction_id"
        ),
        **fields,
        "user_id": g.current_user["user_id"],
    }
    try:
        database.transactions_collection.insert_one(document)
    except PyMongoError:
        return error_response("Darījumu neizdevās saglabāt.", 500)
    return (
        jsonify(
            success=True,
            data={"transaction": serialize_transaction(document, target_currency=g.current_user.get("currency", "EUR"), legacy_currency=g.current_user.get("currency", "EUR"))},
        ),
        201,
    )


@transactions_bp.get("/<int:transaction_id>")
@login_required
def get_transaction(transaction_id):
    transaction = database.transactions_collection.find_one(
        {
            "transaction_id": transaction_id,
            "user_id": g.current_user["user_id"],
        }
    )
    if not transaction:
        return error_response("Darījums nav atrasts.", 404)
    return jsonify(
        success=True,
        data={"transaction": serialize_transaction(transaction, target_currency=g.current_user.get("currency", "EUR"), legacy_currency=g.current_user.get("currency", "EUR"))},
    )


@transactions_bp.put("/<int:transaction_id>")
@login_required
def update_transaction(transaction_id):
    owner_filter = {
        "transaction_id": transaction_id,
        "user_id": g.current_user["user_id"],
    }
    existing = database.transactions_collection.find_one(owner_filter)
    if not existing:
        return error_response("Darījums nav atrasts.", 404)
    payload = request.get_json(silent=True) or {}
    if not payload:
        return error_response("Norādiet vismaz vienu atjaunināmo lauku.")
    fields, errors = validate_fields(payload, existing, g.current_user.get("currency", "EUR"))
    if errors:
        return error_response("Lūdzu, izlabojiet norādītos laukus.", errors=errors)
    updated = database.transactions_collection.find_one_and_update(
        owner_filter, {"$set": fields}, return_document=True
    )
    return jsonify(
        success=True,
        data={"transaction": serialize_transaction(updated, target_currency=g.current_user.get("currency", "EUR"), legacy_currency=g.current_user.get("currency", "EUR"))},
    )


@transactions_bp.delete("/<int:transaction_id>")
@login_required
def delete_transaction(transaction_id):
    result = database.transactions_collection.delete_one(
        {
            "transaction_id": transaction_id,
            "user_id": g.current_user["user_id"],
        }
    )
    if not result.deleted_count:
        return error_response("Darījums nav atrasts.", 404)
    return jsonify(success=True, data={"transaction_id": transaction_id})
