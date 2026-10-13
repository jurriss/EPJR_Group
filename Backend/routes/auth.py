"""Registration and session authentication routes."""

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request, session
from pymongo.errors import DuplicateKeyError, PyMongoError

import database
from utils.auth import hash_password, login_required, verify_password
from utils.users import find_duplicate_user, serialize_user
from utils.validators import validate_registration_payload


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.post("/register")
def register():
    cleaned, errors = validate_registration_payload(request.get_json(silent=True))
    if errors:
        return jsonify(success=False, message="Reģistrācijas dati nav derīgi.", errors=errors), 400

    duplicate_field = find_duplicate_user(cleaned)
    if duplicate_field:
        return (
            jsonify(
                success=False,
                message="Konts ar šādu lietotājvārdu vai e-pastu jau pastāv.",
                errors={duplicate_field: "Šī vērtība jau tiek izmantota."},
            ),
            409,
        )

    user = {
        "user_id": database.generate_unique_numeric_id(
            database.users_collection, "user_id"
        ),
        "username": cleaned["username"],
        "email": cleaned["email"],
        "password": hash_password(cleaned["password"]),
        "created_at": datetime.now(timezone.utc),
        "first_name": cleaned["first_name"],
        "last_name": cleaned["last_name"],
        "age": cleaned["age"],
        "currency": cleaned["currency"],
        "role": "user",
    }
    try:
        database.users_collection.insert_one(user)
    except DuplicateKeyError:
        return jsonify(success=False, message="Lietotājvārds vai e-pasts jau tiek izmantots."), 409
    except PyMongoError:
        return jsonify(success=False, message="Konta izveide pašlaik nav pieejama."), 503

    session.clear()
    session["user_id"] = user["user_id"]
    session.permanent = True
    return (
        jsonify(
            success=True,
            message="Konts ir veiksmīgi izveidots.",
            data={"user": serialize_user(user)},
        ),
        201,
    )


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, message="Nepieciešams JSON pieprasījuma saturs."), 400

    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password")
    if not email or not isinstance(password, str) or not password:
        return (
            jsonify(
                success=False,
                message="E-pasts un parole ir obligāti.",
                errors={"credentials": "Ievadiet savu e-pastu un paroli."},
            ),
            400,
        )

    user = database.users_collection.find_one({"email": email})
    if user is None or not verify_password(user.get("password", ""), password):
        return jsonify(success=False, message="Nepareizs e-pasts vai parole."), 401

    session.clear()
    session["user_id"] = user["user_id"]
    session.permanent = True
    return jsonify(
        success=True,
        message="Pieteikšanās ir veiksmīga.",
        data={"user": serialize_user(user)},
    )


@auth_bp.post("/logout")
@login_required
def logout():
    session.clear()
    return jsonify(success=True, message="Izrakstīšanās ir veiksmīga.")


@auth_bp.get("/me")
@login_required
def current_user():
    return jsonify(success=True, data={"user": serialize_user(g.current_user)})
