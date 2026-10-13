"""Blueprint registration for the Pennywise API."""

from __future__ import annotations

from flask import Flask

from .admin import admin_bp
from .auth import auth_bp
from .categories import categories_bp
from .expenses import expenses_bp
from .income import income_bp
from .overview import overview_bp
from .savings_goals import savings_goals_bp
from .transactions import transactions_bp
from .users import users_bp


def register_blueprints(app: Flask) -> None:
    for blueprint in (
        auth_bp,
        users_bp,
        categories_bp,
        transactions_bp,
        income_bp,
        expenses_bp,
        overview_bp,
        savings_goals_bp,
        admin_bp,
    ):
        app.register_blueprint(blueprint)

