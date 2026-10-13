"""Decimal-safe finance serialization and calculation helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import ceil
from typing import Any

from bson.decimal128 import Decimal128

import database
from utils.exchange_rates import exchange_rates


MONEY_QUANTUM = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_MONEY = Decimal("999999999999.99")


def decimal_amount(value: Any) -> Decimal:
    """Convert supported values to a two-decimal positive monetary amount."""

    if isinstance(value, Decimal128):
        amount = value.to_decimal()
    elif isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError("Summai jābūt derīgam skaitlim.") from error

    if not amount.is_finite() or amount <= 0 or amount > MAX_MONEY:
        raise ValueError("Summai jābūt lielākai par nulli un atbalstītajā diapazonā.")
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def stored_money(value: Any) -> Decimal128:
    return Decimal128(decimal_amount(value))


def decimal_nonnegative_amount(value: Any) -> Decimal:
    """Convert a value to money while allowing a zero balance."""

    if isinstance(value, Decimal128):
        amount = value.to_decimal()
    elif isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError("Summai jābūt derīgam skaitlim.") from error
    if not amount.is_finite() or amount < ZERO or amount > MAX_MONEY:
        raise ValueError("Summa nedrīkst būt negatīva vai pārsniegt atbalstīto diapazonu.")
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def stored_nonnegative_money(value: Any) -> Decimal128:
    return Decimal128(decimal_nonnegative_amount(value))


def as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal128):
        value = value.to_decimal()
    elif not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return ZERO
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def money_text(value: Any) -> str:
    return format(as_decimal(value), ".2f")


def record_currency(record: dict[str, Any], legacy_currency: str | None = None) -> str:
    currency = record.get("currency") or legacy_currency
    if not currency:
        raise ValueError("Ierakstam nav norādīta sākotnējā valūta.")
    return str(currency).upper()


def converted_money(
    record: dict[str, Any], field: str, target_currency: str,
    legacy_currency: str | None = None,
) -> Decimal:
    source_currency = record_currency(record, legacy_currency)
    return exchange_rates.convert(as_decimal(record.get(field)), source_currency, target_currency)


def percentage_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), ".1f")


def parse_date(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Datumam jābūt formātā GGGG-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Ievadiet derīgu datumu formātā GGGG-MM-DD.") from error
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def month_bounds(value: str | None = None) -> tuple[datetime, datetime, str]:
    if value is None:
        today = datetime.now(timezone.utc)
        year, month = today.year, today.month
    else:
        try:
            parsed = datetime.strptime(value, "%Y-%m")
        except (TypeError, ValueError) as error:
            raise ValueError("Mēnesim jābūt formātā GGGG-MM.") from error
        year, month = parsed.year, parsed.month

    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end, f"{year:04d}-{month:02d}"


def shifted_month(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = year * 12 + (month - 1) + offset
    return month_index // 12, month_index % 12 + 1


def category_title_map() -> dict[int, str]:
    return {
        category["category_id"]: category["title"]
        for category in database.categories_collection.find(
            {}, {"_id": 0, "category_id": 1, "title": 1}
        )
    }


def serialize_income(record: dict[str, Any], target_currency: str | None = None,
                     legacy_currency: str | None = None) -> dict[str, Any]:
    original_currency = record_currency(record, legacy_currency) if target_currency else record.get("currency")
    display = converted_money(record, "amount", target_currency, legacy_currency) if target_currency else as_decimal(record.get("amount"))
    return {
        "income_id": record.get("income_id"),
        "amount": money_text(record.get("amount")),
        "currency": original_currency,
        "converted_amount": money_text(display),
        "display_currency": target_currency or original_currency,
    }


def serialize_budget(
    record: dict[str, Any], category_titles: dict[int, str] | None = None,
    target_currency: str | None = None, legacy_currency: str | None = None,
) -> dict[str, Any]:
    titles = category_titles or category_title_map()
    original_currency = record_currency(record, legacy_currency) if target_currency else record.get("currency")
    display = converted_money(record, "amount", target_currency, legacy_currency) if target_currency else as_decimal(record.get("amount"))
    return {
        "expense_id": record.get("expense_id"),
        "amount": money_text(record.get("amount")),
        "currency": original_currency,
        "converted_amount": money_text(display),
        "display_currency": target_currency or original_currency,
        "category_id": record.get("category_id"),
        "category": titles.get(record.get("category_id"), "Nezināma kategorija"),
    }


def serialize_transaction(
    record: dict[str, Any], category_titles: dict[int, str] | None = None,
    target_currency: str | None = None, legacy_currency: str | None = None,
) -> dict[str, Any]:
    titles = category_titles or category_title_map()
    transaction_date = record.get("date")
    if isinstance(transaction_date, datetime):
        date_text = transaction_date.date().isoformat()
    else:
        date_text = None
    original_currency = record_currency(record, legacy_currency) if target_currency else record.get("currency")
    display = converted_money(record, "amount", target_currency, legacy_currency) if target_currency else as_decimal(record.get("amount"))
    return {
        "transaction_id": record.get("transaction_id"),
        "amount": money_text(record.get("amount")),
        "currency": original_currency,
        "converted_amount": money_text(display),
        "display_currency": target_currency or original_currency,
        "type": record.get("type"),
        "description": record.get("description"),
        "date": date_text,
        "category_id": record.get("category_id"),
        "category": titles.get(record.get("category_id"), "Nezināma kategorija"),
    }


def serialize_goal(record: dict[str, Any], target_currency: str | None = None,
                   legacy_currency: str | None = None) -> dict[str, Any]:
    target = as_decimal(record.get("target_amount"))
    current = as_decimal(record.get("current_amount"))
    remaining = max(target - current, ZERO)
    percentage = current / target * Decimal("100") if target else ZERO
    deadline = record.get("deadline")
    if isinstance(deadline, datetime):
        deadline_date = deadline.date()
    elif isinstance(deadline, date):
        deadline_date = deadline
    elif isinstance(deadline, str):
        try:
            deadline_date = date.fromisoformat(deadline)
        except ValueError:
            deadline_date = None
    else:
        deadline_date = None

    today = datetime.now(timezone.utc).date()
    days_remaining = max((deadline_date - today).days, 0) if deadline_date else 0
    months_remaining = max(ceil(days_remaining / 30.4375), 1)
    monthly_contribution = remaining / Decimal(months_remaining) if remaining else ZERO
    if current >= target and target:
        status = "complete"
    elif deadline_date and deadline_date < today:
        status = "overdue"
    else:
        status = "in_progress"

    original_currency = record_currency(record, legacy_currency) if target_currency else record.get("currency")
    display_target = converted_money(record, "target_amount", target_currency, legacy_currency) if target_currency else target
    display_current = converted_money(record, "current_amount", target_currency, legacy_currency) if target_currency else current
    display_remaining = max(display_target - display_current, ZERO)
    display_monthly = display_remaining / Decimal(months_remaining) if display_remaining else ZERO
    return {
        "savings_goals_id": record.get("savings_goals_id"),
        "name": record.get("name"),
        "target_amount": money_text(target),
        "current_amount": money_text(current),
        "currency": original_currency,
        "display_currency": target_currency or original_currency,
        "converted_target_amount": money_text(display_target),
        "converted_current_amount": money_text(display_current),
        "deadline": deadline_date.isoformat() if deadline_date else None,
        "percentage_complete": percentage_text(percentage),
        "remaining_amount": money_text(remaining),
        "monthly_contribution": money_text(monthly_contribution),
        "converted_remaining_amount": money_text(display_remaining),
        "converted_monthly_contribution": money_text(display_monthly),
        "days_remaining": days_remaining,
        "status": status,
    }


def goals_summary(records: list[dict[str, Any]], target_currency: str | None = None,
                  legacy_currency: str | None = None) -> dict[str, Any]:
    if target_currency:
        total_target = sum((converted_money(record, "target_amount", target_currency, legacy_currency) for record in records), ZERO)
        total_saved = sum((converted_money(record, "current_amount", target_currency, legacy_currency) for record in records), ZERO)
    else:
        total_target = sum((as_decimal(record.get("target_amount")) for record in records), ZERO)
        total_saved = sum((as_decimal(record.get("current_amount")) for record in records), ZERO)
    overall = total_saved / total_target * Decimal("100") if total_target else ZERO
    serialized = [serialize_goal(record, target_currency, legacy_currency) for record in records]
    active_count = sum(goal["status"] == "in_progress" for goal in serialized)
    if not records:
        status = "no_goals"
    elif all(goal["status"] == "complete" for goal in serialized):
        status = "complete"
    elif any(goal["status"] == "overdue" for goal in serialized):
        status = "attention_needed"
    else:
        status = "in_progress"
    return {
        "total_target": money_text(total_target),
        "total_saved": money_text(total_saved),
        "remaining_amount": money_text(max(total_target - total_saved, ZERO)),
        "overall_progress": percentage_text(overall),
        "goal_count": len(records),
        "active_goal_count": active_count,
        "status": status,
        "goals": serialized,
        "currency": target_currency,
    }


def transaction_totals(
    user_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    target_currency: str | None = None,
    legacy_currency: str | None = None,
) -> tuple[Decimal, Decimal]:
    query: dict[str, Any] = {"user_id": user_id}
    if start is not None or end is not None:
        date_query: dict[str, datetime] = {}
        if start is not None:
            date_query["$gte"] = start
        if end is not None:
            date_query["$lt"] = end
        query["date"] = date_query

    income = ZERO
    expenses = ZERO
    for transaction in database.transactions_collection.find(
        query, {"_id": 0, "amount": 1, "type": 1, "currency": 1}
    ):
        amount = (
            converted_money(transaction, "amount", target_currency, legacy_currency)
            if target_currency else as_decimal(transaction.get("amount"))
        )
        if transaction.get("type") == "income":
            income += amount
        elif transaction.get("type") == "expense":
            expenses += amount
    return income, expenses


def monthly_income(user_id: int, month: str | None = None, target_currency: str | None = None) -> Decimal:
    start, end, _ = month_bounds(month)
    income, _ = transaction_totals(user_id, start, end, target_currency, target_currency)
    return income


def monthly_expenses(user_id: int, month: str | None = None, target_currency: str | None = None) -> Decimal:
    start, end, _ = month_bounds(month)
    _, expenses = transaction_totals(user_id, start, end, target_currency, target_currency)
    return expenses


def available_balance(user_id: int, target_currency: str | None = None) -> Decimal:
    income, expenses = transaction_totals(user_id, target_currency=target_currency, legacy_currency=target_currency)
    return income - expenses


def net_cash_flow(user_id: int, month: str | None = None, target_currency: str | None = None) -> Decimal:
    return monthly_income(user_id, month, target_currency) - monthly_expenses(user_id, month, target_currency)


def savings_amount(user_id: int, month: str | None = None, target_currency: str | None = None) -> Decimal:
    return max(net_cash_flow(user_id, month, target_currency), ZERO)


def budget_status(percentage: Decimal) -> str:
    if percentage >= Decimal("100"):
        return "exceeded"
    if percentage >= Decimal("80"):
        return "warning"
    return "on_track"


def budget_usage(user_id: int, month: str | None = None, target_currency: str | None = None) -> dict[str, Any]:
    start, end, month_key = month_bounds(month)
    titles = category_title_map()
    spent_by_category: dict[int, Decimal] = {}
    for transaction in database.transactions_collection.find(
        {
            "user_id": user_id,
            "type": "expense",
            "date": {"$gte": start, "$lt": end},
        },
        {"_id": 0, "amount": 1, "category_id": 1, "currency": 1},
    ):
        category_id = transaction.get("category_id")
        amount = converted_money(transaction, "amount", target_currency, target_currency) if target_currency else as_decimal(transaction.get("amount"))
        spent_by_category[category_id] = spent_by_category.get(category_id, ZERO) + amount

    breakdown = []
    total_limit = ZERO
    total_spent = ZERO
    budgets = database.expenses_collection.find({"user_id": user_id}).sort("category_id", 1)
    for budget in budgets:
        limit = converted_money(budget, "amount", target_currency, target_currency) if target_currency else as_decimal(budget.get("amount"))
        spent = spent_by_category.get(budget.get("category_id"), ZERO)
        remaining = limit - spent
        percentage = (spent / limit * Decimal("100")) if limit else ZERO
        total_limit += limit
        total_spent += spent
        breakdown.append(
            {
                **serialize_budget(budget, titles, target_currency, target_currency),
                "limit": money_text(limit),
                "spent": money_text(spent),
                "remaining": money_text(remaining),
                "percentage_used": percentage_text(percentage),
                "status": budget_status(percentage),
            }
        )

    remaining_total = total_limit - total_spent
    overall_percentage = (total_spent / total_limit * Decimal("100")) if total_limit else ZERO
    notifications = []
    for category in breakdown:
        if category["status"] == "exceeded":
            notifications.append(
                {
                    "type": "danger",
                    "message": f'Kategorijas “{category["category"]}” budžets ir pārsniegts.',
                    "category_id": category["category_id"],
                }
            )
        elif category["status"] == "warning":
            notifications.append(
                {
                    "type": "warning",
                    "message": f'Kategorijas “{category["category"]}” budžets tuvojas limitam.',
                    "category_id": category["category_id"],
                }
            )
    return {
        "month": month_key,
        "total_limit": money_text(total_limit),
        "amount_spent": money_text(total_spent),
        "remaining": money_text(remaining_total),
        "percentage_used": percentage_text(overall_percentage),
        "status": budget_status(overall_percentage),
        "categories": breakdown,
        "notifications": notifications,
        "currency": target_currency,
    }


def percentage_change(current: Decimal, previous: Decimal) -> str:
    if previous == ZERO:
        return "100.0" if current > ZERO else "0.0"
    return percentage_text((current - previous) / previous * Decimal("100"))


def six_month_trend(user_id: int, selected_month: str | None = None,
                    target_currency: str | None = None) -> list[dict[str, str]]:
    current_start, _, _ = month_bounds(selected_month)
    trend = []
    for offset in range(-5, 1):
        year, month = shifted_month(current_start.year, current_start.month, offset)
        start, end, key = month_bounds(f"{year:04d}-{month:02d}")
        income, expenses = transaction_totals(user_id, start, end, target_currency, target_currency)
        trend.append(
            {
                "month": key,
                "income": money_text(income),
                "expenses": money_text(expenses),
                "net": money_text(income - expenses),
            }
        )
    return trend


def overview_data(user_id: int, selected_month: str | None = None,
                  target_currency: str | None = None) -> dict[str, Any]:
    start, end, month_key = month_bounds(selected_month)
    current_income, current_expenses = transaction_totals(user_id, start, end, target_currency, target_currency)
    previous_year, previous_month = shifted_month(start.year, start.month, -1)
    previous_start, previous_end, _ = month_bounds(
        f"{previous_year:04d}-{previous_month:02d}"
    )
    previous_income, previous_expenses = transaction_totals(
        user_id, previous_start, previous_end, target_currency, target_currency
    )
    titles = category_title_map()
    recent = database.transactions_collection.find({"user_id": user_id}).sort(
        [("date", -1), ("transaction_id", -1)]
    ).limit(5)
    current_budget = budget_usage(user_id, month_key, target_currency)

    return {
        "month": month_key,
        "available_balance": money_text(available_balance(user_id, target_currency)),
        "current_month_income": money_text(current_income),
        "current_month_spending": money_text(current_expenses),
        "net_cash_flow": money_text(current_income - current_expenses),
        "saved_amount": money_text(max(current_income - current_expenses, ZERO)),
        "income_percentage_change": percentage_change(current_income, previous_income),
        "expense_percentage_change": percentage_change(
            current_expenses, previous_expenses
        ),
        "spending_trend": six_month_trend(user_id, month_key, target_currency),
        "current_budget": current_budget,
        "category_budget_breakdown": current_budget["categories"],
        "recent_transactions": [
            serialize_transaction(transaction, titles, target_currency, target_currency) for transaction in recent
        ],
        "currency": target_currency,
    }
