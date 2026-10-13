"""Authenticated financial overview endpoint."""

from flask import Blueprint, g, jsonify, request

from utils.auth import login_required
from utils.finance import overview_data


overview_bp = Blueprint("overview", __name__, url_prefix="/api/overview")


@overview_bp.get("")
@login_required
def get_overview():
    try:
        data = overview_data(
            g.current_user["user_id"], request.args.get("month"),
            g.current_user.get("currency", "EUR"),
        )
    except ValueError as error:
        return (
            jsonify(
                success=False,
                message="Nederīgs mēnesis.",
                errors={"month": str(error)},
            ),
            400,
        )
    return jsonify(success=True, data=data)
