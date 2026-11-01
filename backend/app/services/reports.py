from __future__ import annotations

from collections import defaultdict
from io import BytesIO

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Transaction


def monthly_summaries(db: Session, user_id: int) -> list[dict]:
    txns = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    buckets: dict[str, dict] = {}
    for txn in txns:
        month = txn.txn_date.strftime("%Y-%m")
        bucket = buckets.setdefault(
            month,
            {
                "month": month,
                "total_debit": 0.0,
                "total_credit": 0.0,
                "by_category": defaultdict(float),
                "transaction_count": 0,
            },
        )
        bucket["transaction_count"] += 1
        if txn.direction == "credit":
            bucket["total_credit"] += txn.amount
        else:
            bucket["total_debit"] += txn.amount
            bucket["by_category"][txn.category] += txn.amount
    rows = []
    for month in sorted(buckets):
        item = buckets[month]
        item["by_category"] = dict(item["by_category"])
        item["total_debit"] = round(item["total_debit"], 2)
        item["total_credit"] = round(item["total_credit"], 2)
        rows.append(item)
    return rows


def dashboard_stats(db: Session, user_id: int) -> dict:
    summaries = monthly_summaries(db, user_id)
    latest = summaries[-1] if summaries else None
    return {
        "months": summaries,
        "latest": latest,
        "total_transactions": db.query(Transaction).filter(Transaction.user_id == user_id).count(),
    }


def excel_report(db: Session, user_id: int) -> bytes:
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.txn_date.desc())
        .all()
    )

    # --- Clean transactions sheet ---
    txn_rows = []
    for txn in txns:
        txn_rows.append(
            {
                "Date": txn.txn_date.date().isoformat(),
                "Month": txn.txn_date.strftime("%Y-%m"),
                "Merchant": txn.merchant,
                "Description": txn.cleaned_description or txn.raw_description,
                "Amount": round(txn.amount, 2),
                "Direction": txn.direction,
                "Category": txn.category,
                "Source": txn.source,
                "Method": txn.classification_method,
                "Confidence": txn.confidence,
                "Corrected": txn.is_corrected,
                "Recurring": txn.is_recurring,
            }
        )
    txn_frame = pd.DataFrame(txn_rows)

    # --- Monthly Overview ---
    summaries = monthly_summaries(db, user_id)
    overview_rows = []
    for item in summaries:
        overview_rows.append(
            {
                "Month": item["month"],
                "Total Spent (Debit)": item["total_debit"],
                "Total Credited": item["total_credit"],
                "Net": round(item["total_credit"] - item["total_debit"], 2),
                "Transactions": item["transaction_count"],
            }
        )
    overview_frame = pd.DataFrame(overview_rows)

    # --- Category x Month pivot (only debits) ---
    debit_txns = [t for t in txns if t.direction == "debit"]
    if debit_txns:
        cat_month = defaultdict(lambda: defaultdict(float))
        for t in debit_txns:
            month = t.txn_date.strftime("%Y-%m")
            cat_month[t.category][month] += t.amount

        all_months = sorted({t.txn_date.strftime("%Y-%m") for t in debit_txns})
        pivot_rows = []
        for category in sorted(cat_month.keys()):
            row = {"Category": category}
            total = 0.0
            for m in all_months:
                val = round(cat_month[category].get(m, 0.0), 2)
                row[m] = val
                total += val
            row["Total"] = round(total, 2)
            pivot_rows.append(row)
        # Total row
        total_row = {"Category": "TOTAL"}
        grand = 0.0
        for m in all_months:
            s = sum(cat_month[c].get(m, 0.0) for c in cat_month)
            total_row[m] = round(s, 2)
            grand += s
        total_row["Total"] = round(grand, 2)
        pivot_rows.append(total_row)
        pivot_frame = pd.DataFrame(pivot_rows)
    else:
        pivot_frame = pd.DataFrame([{"Category": "No debit transactions yet"}])

    # --- Category totals (all time, debits only) ---
    cat_totals: dict[str, float] = defaultdict(float)
    for t in debit_txns:
        cat_totals[t.category] += t.amount
    cat_total_rows = [
        {"Category": cat, "Total Spent": round(amt, 2)}
        for cat, amt in sorted(cat_totals.items(), key=lambda x: -x[1])
    ]
    if cat_total_rows:
        cat_total_rows.append({"Category": "TOTAL", "Total Spent": round(sum(cat_totals.values()), 2)})
    cat_total_frame = pd.DataFrame(cat_total_rows)

    # --- Top merchants ---
    merchant_totals: dict[str, float] = defaultdict(float)
    for t in debit_txns:
        name = t.merchant or "Unknown"
        merchant_totals[name] += t.amount
    top_merchant_rows = [
        {"Merchant": m, "Total Spent": round(a, 2)}
        for m, a in sorted(merchant_totals.items(), key=lambda x: -x[1])[:30]
    ]
    top_merchant_frame = pd.DataFrame(top_merchant_rows)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        overview_frame.to_excel(writer, index=False, sheet_name="Monthly Overview")
        pivot_frame.to_excel(writer, index=False, sheet_name="Category by Month")
        cat_total_frame.to_excel(writer, index=False, sheet_name="Category Totals")
        top_merchant_frame.to_excel(writer, index=False, sheet_name="Top Merchants")
        txn_frame.to_excel(writer, index=False, sheet_name="All Transactions")
    return buffer.getvalue()
