"""Authenticated category management routes."""

import re

from flask import Blueprint, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import database
from utils.auth import admin_required, login_required
from utils.users import serialize_category
from utils.validators import validate_category_title


categories_bp = Blueprint("categories", __name__, url_prefix="/api/categories")


def _find_category_by_title(title: str, exclude_id: int | None = None):
    query = {"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}}
    if exclude_id is not None:
        query["category_id"] = {"$ne": exclude_id}
    return database.categories_collection.find_one(query, {"_id": 1})


@categories_bp.get("")
@login_required
def list_categories():
    query = {}
    category_type = request.args.get("type")
    if category_type:
        if category_type not in {"income", "expense"}:
            return jsonify(success=False, message="Nederīgs kategorijas veids."), 400
        query["type"] = category_type
    categories = database.categories_collection.find(query).sort("title", 1)
    return jsonify(
        success=True,
        data={"categories": [serialize_category(category) for category in categories]},
    )


@categories_bp.post("")
@admin_required
def create_category():
    payload = request.get_json(silent=True)
    title, error = validate_category_title(payload.get("title") if isinstance(payload, dict) else None)
    category_type = payload.get("type", "expense") if isinstance(payload, dict) else None
    if error:
        return jsonify(success=False, message=error, errors={"title": error}), 400
    if category_type not in {"income", "expense"}:
        error = "Izvēlieties kategorijas veidu."
        return jsonify(success=False, message=error, errors={"type": error}), 400
    if _find_category_by_title(title):
        return jsonify(success=False, message="Kategorija ar šādu nosaukumu jau pastāv."), 409

    category = {
        "category_id": database.generate_unique_numeric_id(
            database.categories_collection, "category_id"
        ),
        "title": title,
        "type": category_type,
    }
    try:
        database.categories_collection.insert_one(category)
    except DuplicateKeyError:
        return jsonify(success=False, message="Kategorija ar šādu nosaukumu jau pastāv."), 409
    except PyMongoError:
        return jsonify(success=False, message="Kategorijas izveide pašlaik nav pieejama."), 503
    return (
        jsonify(
            success=True,
            message="Kategorija ir veiksmīgi izveidota.",
            data={"category": serialize_category(category)},
        ),
        201,
    )


@categories_bp.put("/<int:category_id>")
@admin_required
def update_category(category_id: int):
    payload = request.get_json(silent=True)
    existing = database.categories_collection.find_one({"category_id": category_id})
    if existing is None:
        return jsonify(success=False, message="Kategorija nav atrasta."), 404
    title, error = validate_category_title(payload.get("title") if isinstance(payload, dict) else None)
    category_type = payload.get("type", existing.get("type") or "expense") if isinstance(payload, dict) else None
    if error:
        return jsonify(success=False, message=error, errors={"title": error}), 400
    if category_type not in {"income", "expense"}:
        error = "Izvēlieties kategorijas veidu."
        return jsonify(success=False, message=error, errors={"type": error}), 400
    if category_type != existing.get("type"):
        conflicting_transactions = database.transactions_collection.count_documents(
            {"category_id": category_id, "type": {"$ne": category_type}}, limit=1
        )
        budget_uses = database.expenses_collection.count_documents(
            {"category_id": category_id}, limit=1
        )
        if conflicting_transactions or (category_type == "income" and budget_uses):
            return (
                jsonify(
                    success=False,
                    message="Kategorijas veidu nevar mainīt, kamēr tā tiek izmantota neatbilstošos darījumos vai budžetos.",
                ),
                409,
            )
    if _find_category_by_title(title, category_id):
        return jsonify(success=False, message="Kategorija ar šādu nosaukumu jau pastāv."), 409

    try:
        result = database.categories_collection.update_one(
            {"category_id": category_id}, {"$set": {"title": title, "type": category_type}}
        )
    except DuplicateKeyError:
        return jsonify(success=False, message="Kategorija ar šādu nosaukumu jau pastāv."), 409
    except PyMongoError:
        return jsonify(success=False, message="Kategorijas atjaunināšana pašlaik nav pieejama."), 503
    category = database.categories_collection.find_one({"category_id": category_id})
    return jsonify(
        success=True,
        message="Kategorija ir veiksmīgi atjaunināta.",
        data={"category": serialize_category(category)},
    )


@categories_bp.delete("/<int:category_id>")
@admin_required
def delete_category(category_id: int):
    category = database.categories_collection.find_one({"category_id": category_id})
    if category is None:
        return jsonify(success=False, message="Kategorija nav atrasta."), 404

    transaction_uses = database.transactions_collection.count_documents(
        {"category_id": category_id}, limit=1
    )
    budget_uses = database.expenses_collection.count_documents(
        {"category_id": category_id}, limit=1
    )
    if transaction_uses or budget_uses:
        return (
            jsonify(
                success=False,
                message="Šī kategorija pašlaik tiek izmantota darījumos vai budžetos, tāpēc to nevar dzēst.",
            ),
            409,
        )

    try:
        database.categories_collection.delete_one({"category_id": category_id})
    except PyMongoError:
        return jsonify(success=False, message="Kategorijas dzēšana pašlaik nav pieejama."), 503
    return jsonify(success=True, message="Kategorija ir veiksmīgi dzēsta.")
