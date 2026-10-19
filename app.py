
import os
from datetime import date
from decimal import Decimal, InvalidOperation

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY", "local-demo-only-change-me"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

CATEGORIES = [
    "Food",
    "Transport",
    "Education",
    "Shopping",
    "Bills",
    "Entertainment",
    "Health",
    "Other",
]


def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        connect_timeout=10,
    )


@app.route("/")
def index():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, transaction_type, amount, category,
                       description, transaction_date
                FROM transactions
                ORDER BY transaction_date DESC, id DESC
            """)
            transactions = cur.fetchall()

            cur.execute("""
                SELECT
                    COALESCE(SUM(amount) FILTER (
                        WHERE transaction_type = 'income'
                    ), 0) AS income,
                    COALESCE(SUM(amount) FILTER (
                        WHERE transaction_type = 'expense'
                    ), 0) AS expenses
                FROM transactions
            """)
            totals = cur.fetchone()

            cur.execute("""
                SELECT category, SUM(amount) AS total
                FROM transactions
                WHERE transaction_type = 'expense'
                GROUP BY category
                ORDER BY total DESC
            """)
            category_rows = cur.fetchall()

    income = Decimal(str(totals["income"]))
    expenses = Decimal(str(totals["expenses"]))
    balance = income - expenses

    chart_labels = [row["category"] for row in category_rows]
    chart_values = [float(row["total"]) for row in category_rows]

    return render_template(
        "index.html",
        transactions=transactions,
        income=income,
        expenses=expenses,
        balance=balance,
        categories=CATEGORIES,
        chart_labels=chart_labels,
        chart_values=chart_values,
        today=date.today().isoformat(),
    )


@app.route("/add", methods=["POST"])
def add_transaction():
    transaction_type = request.form.get("transaction_type", "")
    category = request.form.get("category", "")
    description = request.form.get("description", "").strip()
    transaction_date = request.form.get("transaction_date", "")

    try:
        amount = Decimal(request.form.get("amount", ""))
    except (InvalidOperation, TypeError):
        flash("Enter a valid amount.", "error")
        return redirect(url_for("index"))

    if transaction_type not in ("income", "expense"):
        flash("Choose income or expense.", "error")
        return redirect(url_for("index"))

    if category not in CATEGORIES:
        flash("Choose a valid category.", "error")
        return redirect(url_for("index"))

    if (
        not amount.is_finite()
        or amount <= 0
        or amount > Decimal("1000000000")
    ):
        flash("Enter a valid positive amount within the limit.", "error")
        return redirect(url_for("index"))

    if amount.as_tuple().exponent < -2:
        flash("Use at most two decimal places.", "error")
        return redirect(url_for("index"))

    if len(description) > 200:
        flash("Description must be 200 characters or fewer.", "error")
        return redirect(url_for("index"))

    try:
        parsed_date = date.fromisoformat(transaction_date)
    except (ValueError, TypeError):
        flash("Enter a valid transaction date.", "error")
        return redirect(url_for("index"))

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO transactions
                        (transaction_type, amount, category,
                         description, transaction_date)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    transaction_type,
                    amount,
                    category,
                    description,
                    parsed_date,
                ))

        flash("Transaction added successfully.", "success")

    except Exception:
        app.logger.exception("Could not save transaction")
        flash(
            "Could not save the transaction. Check database settings.",
            "error",
        )

    return redirect(url_for("index"))


@app.route("/delete/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM transactions WHERE id = %s",
                    (transaction_id,),
                )
                deleted = cur.rowcount

        if deleted:
            flash("Transaction deleted.", "success")
        else:
            flash("Transaction not found.", "error")

    except Exception:
        app.logger.exception("Could not delete transaction")
        flash("Could not delete the transaction.", "error")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
