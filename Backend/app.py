"""Pennywise Flask application entry point."""

from __future__ import annotations

import logging
from pathlib import Path

import click
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from config import Config
from database import (
    check_connection,
    ensure_indexes,
    get_connection_status_message,
    init_database,
    seed_default_categories,
)
from routes import register_blueprints
from utils.exchange_rates import ExchangeRateError, exchange_rates


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "Frontend"


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_class)
    exchange_rates.api_url = app.config["EXCHANGE_RATE_API_URL"].rstrip("/")
    exchange_rates.ttl_seconds = app.config["EXCHANGE_RATE_CACHE_SECONDS"]
    exchange_rates.timeout = app.config["EXCHANGE_RATE_TIMEOUT_SECONDS"]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if app.config["SECRET_KEY_IS_EPHEMERAL"]:
        app.logger.warning(
            "SECRET_KEY is not set; an ephemeral development key is being used."
        )

    cors_origins = app.config.get("CORS_ORIGINS", [])
    if cors_origins:
        CORS(
            app,
            resources={r"/api/*": {"origins": cors_origins}},
            supports_credentials=True,
        )

    init_database(app)
    if ensure_indexes():
        created_categories = seed_default_categories()
        if created_categories:
            app.logger.info("Created %s default categories.", created_categories)
    register_blueprints(app)
    register_health_routes(app)
    register_frontend_routes(app)
    register_security_middleware(app)
    register_error_handlers(app)
    register_cli_commands(app)

    return app


def register_cli_commands(app: Flask) -> None:
    @app.cli.command("promote-admin")
    @click.argument("email")
    def promote_admin(email: str) -> None:
        """Promote an existing account to the initial administrator role."""

        import database

        result = database.users_collection.update_one(
            {"email": email.strip().lower()}, {"$set": {"role": "admin"}}
        )
        if result.matched_count == 0:
            raise click.ClickException("No Pennywise user has that email address.")
        click.echo("The user is now a Pennywise administrator.")


def register_health_routes(app: Flask) -> None:
    @app.get("/api/health")
    def health():
        return jsonify(success=True, message="Pennywise API darbojas")

    @app.get("/api/health/database")
    def database_health():
        connected = check_connection()
        status_code = 200 if connected else 503
        message = (
            "Pennywise ir savienots ar MongoDB"
            if connected
            else get_connection_status_message()
        )
        return jsonify(success=connected, message=message), status_code


def register_frontend_routes(app: Flask) -> None:
    @app.get("/")
    def frontend_index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<path:asset_path>")
    def frontend_asset(asset_path: str):
        return send_from_directory(FRONTEND_DIR, asset_path)


def register_security_middleware(app: Flask) -> None:
    """Apply browser request checks and conservative response headers."""

    unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}

    @app.before_request
    def reject_cross_site_api_writes():
        if not request.path.startswith("/api/") or request.method not in unsafe_methods:
            return None

        origin = request.headers.get("Origin", "").rstrip("/")
        allowed_origins = {
            request.host_url.rstrip("/"),
            *(item.rstrip("/") for item in app.config.get("CORS_ORIGINS", [])),
        }
        fetch_site = request.headers.get("Sec-Fetch-Site", "").lower()
        if origin and origin not in allowed_origins:
            return jsonify(success=False, message="Starpvietņu pieprasījums ir bloķēts."), 403
        if fetch_site == "cross-site" and origin not in allowed_origins:
            return jsonify(success=False, message="Starpvietņu pieprasījums ir bloķēts."), 403
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ExchangeRateError)
    def exchange_rate_error(error):
        if request.path.startswith("/api/"):
            return jsonify(success=False, message=str(error)), 503
        return str(error), 503

    api_messages = {
        400: "Nederīgs pieprasījums.",
        401: "Nepieciešama autentifikācija.",
        403: "Jums nav tiesību veikt šo darbību.",
        409: "Pieprasījums ir pretrunā ar esošajiem datiem.",
        413: "Pieprasījuma saturs ir pārāk liels.",
    }

    for status_code, message in api_messages.items():
        def api_http_error(error, code=status_code, safe_message=message):
            if request.path.startswith("/api/"):
                return jsonify(success=False, message=safe_message), code
            return error

        app.register_error_handler(status_code, api_http_error)

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify(success=False, message="API galapunkts nav atrasts."), 404
        return error

    @app.errorhandler(405)
    def method_not_allowed(error):
        if request.path.startswith("/api/"):
            return jsonify(success=False, message="Metode nav atļauta."), 405
        return error

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error, HTTPException):
            if request.path.startswith("/api/"):
                return (
                    jsonify(success=False, message="Pieprasījumu neizdevās izpildīt."),
                    error.code or 500,
                )
            return error

        app.logger.exception("Unhandled application error.")
        if request.path.startswith("/api/"):
            return jsonify(success=False, message="Iekšēja servera kļūda."), 500
        return "Iekšēja servera kļūda.", 500


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
