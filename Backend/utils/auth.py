"""Authentication and authorization helpers for Pennywise sessions."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import g, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

import database


ViewFunction = TypeVar("ViewFunction", bound=Callable[..., Any])


def hash_password(password: str) -> str:
    """Hash a password with Werkzeug's secure default algorithm."""

    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a password against its stored hash."""

    return check_password_hash(password_hash, password)


def get_authenticated_user_id() -> int | None:
    """Read the server-managed user ID from the session."""

    user_id = session.get("user_id")
    return user_id if isinstance(user_id, int) else None


def get_authenticated_user() -> dict[str, Any] | None:
    """Resolve the session identity to a current database user."""

    cached_user = getattr(g, "current_user", None)
    if cached_user is not None:
        return cached_user

    user_id = get_authenticated_user_id()
    if user_id is None or database.users_collection is None:
        return None

    user = database.users_collection.find_one({"user_id": user_id})
    if user is not None:
        g.current_user = user
    return user


def login_required(view: ViewFunction) -> ViewFunction:
    """Protect a route without accepting identity from request data."""

    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        if get_authenticated_user() is None:
            session.clear()
            return jsonify(success=False, message="Nepieciešama autentifikācija."), 401
        return view(*args, **kwargs)

    return cast(ViewFunction, wrapped_view)


def admin_required(view: ViewFunction) -> ViewFunction:
    """Require a current user whose stored role is administrator."""

    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        user = get_authenticated_user()
        if user is None:
            session.clear()
            return jsonify(success=False, message="Nepieciešama autentifikācija."), 401
        if user.get("role", "user") != "admin":
            return jsonify(success=False, message="Nepieciešamas administratora piekļuves tiesības."), 403
        return view(*args, **kwargs)

    return cast(ViewFunction, wrapped_view)
