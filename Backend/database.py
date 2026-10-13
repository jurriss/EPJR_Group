"""MongoDB client setup and Pennywise collection references."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from flask import Flask
from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError


logger = logging.getLogger(__name__)

mongo_client: MongoClient | None = None
db: Database | None = None

users_collection: Any = None
income_collection: Any = None
expenses_collection: Any = None
transactions_collection: Any = None
categories_collection: Any = None
savings_goals_collection: Any = None

_last_connection_error: str | None = None

DEFAULT_CATEGORIES = (
    ("Alga", "income"),
    ("Pašnodarbinātības ienākumi", "income"),
    ("Uzņēmējdarbības ienākumi", "income"),
    ("Īres ienākumi", "income"),
    ("Dividendes", "income"),
    ("Procentu ienākumi", "income"),
    ("Investīciju peļņa", "income"),
    ("Pabalsti un pensija", "income"),
    ("Stipendija", "income"),
    ("Mantojums", "income"),
    ("Dāvanas", "income"),
    ("Naudas atmaksa", "income"),
    ("Pārdoto preču ienākumi", "income"),
    ("Citi ienākumi", "income"),
    ("Mājoklis un īre", "expense"),
    ("Komunālie maksājumi", "expense"),
    ("Pārtika un pārtikas preces", "expense"),
    ("Transports", "expense"),
    ("Degviela", "expense"),
    ("Veselība un medicīna", "expense"),
    ("Apģērbs un apavi", "expense"),
    ("Izglītība", "expense"),
    ("Abonementi", "expense"),
    ("Izklaide", "expense"),
    ("Restorāni un kafejnīcas", "expense"),
    ("Sports un fitness", "expense"),
    ("Personīgā aprūpe", "expense"),
    ("Tehnoloģijas un elektronika", "expense"),
    ("Ceļojumi", "expense"),
    ("Apdrošināšana", "expense"),
    ("Kredīti un parādi", "expense"),
    ("Nodokļi", "expense"),
    ("Dāvanas un ziedojumi", "expense"),
    ("Mājdzīvnieki", "expense"),
    ("Mājsaimniecība", "expense"),
    ("Iepirkšanās", "expense"),
    ("Bankas komisijas", "expense"),
    ("Citi izdevumi", "expense"),
)
LEGACY_EXPENSE_CATEGORY_TITLES = (
    "Food & coffee", "Transport", "Education", "Fun & social",
    "Subscriptions", "Groceries", "Housing",
)


def init_database(app: Flask) -> None:
    """Initialize MongoDB without blocking application startup."""

    global mongo_client, db
    global users_collection, income_collection, expenses_collection
    global transactions_collection, categories_collection, savings_goals_collection
    global _last_connection_error

    mongo_uri = app.config.get("MONGO_URI")
    if not mongo_uri:
        _last_connection_error = "MONGO_URI nav konfigurēts."
        app.logger.warning(_last_connection_error)
        return

    try:
        mongo_client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=app.config["MONGO_TIMEOUT_MS"],
            connectTimeoutMS=app.config["MONGO_TIMEOUT_MS"],
            appname="Pennywise",
        )
        db = mongo_client[app.config["DATABASE_NAME"]]
        users_collection = db["users"]
        income_collection = db["income"]
        expenses_collection = db["expenses"]
        transactions_collection = db["transactions"]
        categories_collection = db["categories"]
        savings_goals_collection = db["savings_goals"]
        _last_connection_error = None
    except (PyMongoError, ValueError) as error:
        _last_connection_error = str(error)
        app.logger.error("MongoDB initialization failed. Check the configured connection settings.")


def check_connection() -> bool:
    """Ping MongoDB and return whether the database is reachable."""

    global _last_connection_error

    if mongo_client is None:
        if _last_connection_error is None:
            _last_connection_error = "MongoDB nav inicializēta."
        return False

    try:
        mongo_client.admin.command("ping")
        _last_connection_error = None
        return True
    except PyMongoError as error:
        _last_connection_error = str(error)
        logger.warning("MongoDB ping failed. Check Atlas availability and network access.")
        return False


def get_connection_status_message() -> str:
    """Return a safe status message without exposing credentials."""

    if _last_connection_error == "MONGO_URI nav konfigurēts.":
        return _last_connection_error
    if _last_connection_error:
        return "MongoDB nav pieejama. Pārbaudiet Atlas URI, tīkla piekļuvi un akreditācijas datus."
    return "MongoDB savienojums darbojas."


def generate_unique_numeric_id(collection: Any, field_name: str) -> int:
    """Generate a numeric business ID and verify it is unused."""

    for _ in range(20):
        candidate = secrets.randbelow(9_000_000_000) + 1_000_000_000
        if collection.find_one({field_name: candidate}, {"_id": 1}) is None:
            return candidate
    raise RuntimeError(f"Could not generate a unique {field_name}.")


def ensure_indexes() -> bool:
    """Create uniqueness and relationship indexes for business fields."""

    if not check_connection():
        return False

    index_definitions = (
        (users_collection, "user_id"),
        (income_collection, "income_id"),
        (expenses_collection, "expense_id"),
        (transactions_collection, "transaction_id"),
        (categories_collection, "category_id"),
        (savings_goals_collection, "savings_goals_id"),
    )
    try:
        for collection, field_name in index_definitions:
            collection.create_index([(field_name, ASCENDING)], unique=True)

        users_collection.create_index([("email", ASCENDING)], unique=True)
        users_collection.create_index([("username", ASCENDING)], unique=True)
        income_collection.create_index([("user_id", ASCENDING)])
        expenses_collection.create_index([("user_id", ASCENDING)])
        expenses_collection.create_index([("category_id", ASCENDING)])
        expenses_collection.create_index(
            [("user_id", ASCENDING), ("category_id", ASCENDING)], unique=True
        )
        transactions_collection.create_index([("user_id", ASCENDING)])
        transactions_collection.create_index([("category_id", ASCENDING)])
        transactions_collection.create_index(
            [("user_id", ASCENDING), ("date", ASCENDING)]
        )
        categories_collection.create_index([("title", ASCENDING)], unique=True)
        savings_goals_collection.create_index([("user_id", ASCENDING)])
        return True
    except PyMongoError:
        logger.error("MongoDB index creation failed.")
        return False


def seed_default_categories() -> int:
    """Insert the small default category set without creating duplicates."""

    if categories_collection is None or not check_connection():
        return 0

    created = 0
    categories_collection.update_many(
        {
            "title": {"$in": list(LEGACY_EXPENSE_CATEGORY_TITLES)},
            "type": {"$nin": ["income", "expense"]},
        },
        {"$set": {"type": "expense"}},
    )
    for title, category_type in DEFAULT_CATEGORIES:
        existing = categories_collection.find_one(
            {"title": {"$regex": f"^{title}$", "$options": "i"}},
            {"_id": 1, "type": 1},
        )
        if existing:
            if existing.get("type") not in {"income", "expense"}:
                categories_collection.update_one(
                    {"_id": existing["_id"]}, {"$set": {"type": category_type}}
                )
            continue
        try:
            categories_collection.insert_one(
                {
                    "category_id": generate_unique_numeric_id(
                        categories_collection, "category_id"
                    ),
                    "title": title,
                    "type": category_type,
                }
            )
            created += 1
        except DuplicateKeyError:
            continue
    return created
