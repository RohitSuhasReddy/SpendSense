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
            {"month": month, "total_debit": 0.0, "total_credit": 0.0, "by_category": defaultdict(float), "transaction_count": 0},
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
    frame = pd.DataFrame(
        [
            {
                "Date": txn.txn_date.date().isoformat(),
                "Merchant": txn.merchant,
                "Description": txn.cleaned_description or txn.raw_description,
                "Amount": txn.amount,
                "Direction": txn.direction,
                "Category": txn.category,
                "Source": txn.source,
                "Method": txn.classification_method,
                "Confidence": txn.confidence,
                "Corrected": txn.is_corrected,
                "Recurring": txn.is_recurring,
            }
            for txn in txns
        ]
    )
    summaries = monthly_summaries(db, user_id)
    summary_rows = []
    for item in summaries:
        row = {
            "Month": item["month"],
            "Debit": item["total_debit"],
            "Credit": item["total_credit"],
            "Transactions": item["transaction_count"],
        }
        row.update(item["by_category"])
        summary_rows.append(row)
    summary_frame = pd.DataFrame(summary_rows)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Transactions")
        summary_frame.to_excel(writer, index=False, sheet_name="Monthly Summary")
    return buffer.getvalue()
