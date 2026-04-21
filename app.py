from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "expenses.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

app = Flask(__name__)


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema)
        conn.commit()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def to_cents(raw_amount: str) -> int:
    try:
        amount = Decimal(raw_amount)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Amount must be a valid number.") from exc
    if amount < 0:
        raise ValueError("Amount cannot be negative.")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_rupees(amount_cents: int) -> str:
    value = Decimal(amount_cents) / Decimal("100")
    return f"{value:.2f}"


def wants_json_response() -> bool:
    if request.is_json:
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept.lower()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "amount": row["amount"],
        "category": row["category"],
        "description": row["description"],
        "date": row["date"],
        "created_at": row["created_at"],
        "idempotency_key": row["idempotency_key"],
    }


@app.template_filter("inr")
def inr_filter(amount_cents: int) -> str:
    return f"\u20b9{format_rupees(amount_cents)}"


@app.get("/")
def home() -> Any:
    return redirect(url_for("list_expenses"))


@app.get("/expenses")
def list_expenses() -> Any:
    selected_category = request.args.get("category", "").strip()
    sort = request.args.get("sort", "date_desc").strip()

    query = (
        "SELECT id, amount, category, description, date, created_at, idempotency_key "
        "FROM expenses"
    )
    params: list[Any] = []

    if selected_category:
        query += " WHERE category = ?"
        params.append(selected_category)

    if sort == "date_asc":
        query += " ORDER BY date ASC, created_at ASC"
    else:
        sort = "date_desc"
        query += " ORDER BY date DESC, created_at DESC"

    with get_connection() as conn:
        expenses = conn.execute(query, params).fetchall()
        categories = conn.execute(
            "SELECT DISTINCT category FROM expenses ORDER BY category ASC"
        ).fetchall()

    total_cents = sum(row["amount"] for row in expenses)

    return render_template(
        "index.html",
        expenses=expenses,
        categories=[row["category"] for row in categories],
        selected_category=selected_category,
        sort=sort,
        total_cents=total_cents,
        message=request.args.get("message", ""),
        error=request.args.get("error", ""),
    )


@app.post("/expenses")
def create_expense() -> Any:
    idempotency_key = request.headers.get("X-Idempotency-Key", "").strip()

    payload: dict[str, Any]
    if request.is_json:
        payload = request.get_json(silent=True) or {}
    else:
        payload = request.form.to_dict(flat=True)

    if not idempotency_key:
        idempotency_key = str(payload.get("idempotency_key", "")).strip()

    if not idempotency_key:
        if wants_json_response():
            return jsonify({"error": "X-Idempotency-Key header is required."}), 400
        return redirect(
            url_for("list_expenses", error="Idempotency key is required."),
            code=303,
        )

    try:
        amount_cents = to_cents(str(payload.get("amount", "")).strip())
    except ValueError as exc:
        if wants_json_response():
            return jsonify({"error": str(exc)}), 400
        return redirect(url_for("list_expenses", error=str(exc)), code=303)

    category = str(payload.get("category", "")).strip()
    description = str(payload.get("description", "")).strip()
    expense_date = str(payload.get("date", "")).strip()

    if not category or not expense_date:
        message = "Category and date are required."
        if wants_json_response():
            return jsonify({"error": message}), 400
        return redirect(url_for("list_expenses", error=message), code=303)

    try:
        date.fromisoformat(expense_date)
    except ValueError:
        message = "Date must be in YYYY-MM-DD format."
        if wants_json_response():
            return jsonify({"error": message}), 400
        return redirect(url_for("list_expenses", error=message), code=303)

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, amount, category, description, date, created_at, idempotency_key "
            "FROM expenses WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()

        if existing is not None:
            if wants_json_response():
                return jsonify(row_to_dict(existing)), 200
            return redirect(
                url_for("list_expenses", message="Duplicate submission ignored."),
                code=303,
            )

        expense_id = str(uuid4())
        conn.execute(
            "INSERT INTO expenses (id, amount, category, description, date, idempotency_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (expense_id, amount_cents, category, description, expense_date, idempotency_key),
        )
        conn.commit()

        created = conn.execute(
            "SELECT id, amount, category, description, date, created_at, idempotency_key "
            "FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()

    if wants_json_response():
        return jsonify(row_to_dict(created)), 201

    return redirect(
        url_for("list_expenses", message="Expense added successfully."),
        code=303,
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
