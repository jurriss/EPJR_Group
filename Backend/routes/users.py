"""Authenticated user profile routes."""

from flask import Blueprint, g, jsonify, request, session
from pymongo.errors import DuplicateKeyError, PyMongoError

import database
from utils.auth import login_required
from utils.users import (
    delete_user_and_related_data,
    find_duplicate_user,
    freeze_legacy_record_currencies,
    serialize_user,
)
from utils.validators import validate_profile_payload


users_bp = Blueprint("users", __name__, url_prefix="/api/users")


@users_bp.get("/me")
@login_required
def get_profile():
    return jsonify(success=True, data={"user": serialize_user(g.current_user)})


@users_bp.put("/me")
@login_required
def update_profile():
    updates, errors = validate_profile_payload(request.get_json(silent=True))
    if errors:
        return jsonify(success=False, message="Profila dati nav derīgi.", errors=errors), 400

    duplicate_field = find_duplicate_user(updates, g.current_user["user_id"])
    if duplicate_field:
        return (
            jsonify(
                success=False,
                message="Šis lietotājvārds vai e-pasts jau tiek izmantots.",
                errors={duplicate_field: "Šī vērtība jau tiek izmantota."},
            ),
            409,
        )

    try:
        if updates.get("currency") and updates["currency"] != g.current_user.get("currency"):
            freeze_legacy_record_currencies(
                g.current_user["user_id"], g.current_user.get("currency", "EUR")
            )
        database.users_collection.update_one(
            {"user_id": g.current_user["user_id"]}, {"$set": updates}
        )
    except DuplicateKeyError:
        return jsonify(success=False, message="Lietotājvārds vai e-pasts jau tiek izmantots."), 409
    except PyMongoError:
        return jsonify(success=False, message="Profila atjaunināšana pašlaik nav pieejama."), 503

    user = database.users_collection.find_one({"user_id": g.current_user["user_id"]})
    return jsonify(
        success=True,
        message="Profils ir veiksmīgi atjaunināts.",
        data={"user": serialize_user(user)},
    )


@users_bp.delete("/me")
@login_required
def delete_account():
    user_id = g.current_user["user_id"]
    try:
        delete_user_and_related_data(user_id)
    except PyMongoError:
        return jsonify(success=False, message="Konta dzēšana pašlaik nav pieejama."), 503
    session.clear()
    return jsonify(success=True, message="Konts un saistītie finanšu dati ir veiksmīgi dzēsti.")
