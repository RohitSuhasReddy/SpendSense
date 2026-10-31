from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import CATEGORIES, Transaction, User
from app.schemas import TransactionOut, TransactionUpdate
from app.services.classifier import classify_transaction, learn_mapping, mark_recurring

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    category: str | None = None,
    source: str | None = None,
    month: str | None = Query(default=None, description="YYYY-MM"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Transaction).filter(Transaction.user_id == user.id)
    if category:
        query = query.filter(Transaction.category == category)
    if source:
        query = query.filter(Transaction.source == source)
    if month:
        try:
            start = datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM") from exc
        if start.month == 12:
            end = datetime(start.year + 1, 1, 1)
        else:
            end = datetime(start.year, start.month + 1, 1)
        query = query.filter(Transaction.txn_date >= start, Transaction.txn_date < end)
    return query.order_by(Transaction.txn_date.desc()).all()


@router.get("/categories")
def categories():
    return CATEGORIES


@router.patch("/{txn_id}", response_model=TransactionOut)
def correct_transaction(
    txn_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Unknown category")
    txn = (
        db.query(Transaction)
        .filter(Transaction.id == txn_id, Transaction.user_id == user.id)
        .one_or_none()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.category = payload.category
    txn.is_corrected = True
    txn.classification_method = "user"
    txn.confidence = 1.0
    learn_mapping(db, user.id, txn.raw_description, txn.merchant, payload.category)

    siblings = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user.id,
            Transaction.merchant == txn.merchant,
            Transaction.is_corrected.is_(False),
        )
        .all()
    )
    for sibling in siblings:
        sibling.category = payload.category
        sibling.classification_method = "mapping"
        sibling.confidence = 0.99

    mark_recurring(db, user.id)
    db.commit()
    db.refresh(txn)
    return txn


@router.post("/reclassify")
def reclassify(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    txns = db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.is_corrected.is_(False)).all()
    updated = 0
    for txn in txns:
        category, method, confidence = classify_transaction(db, user.id, txn.merchant, txn.cleaned_description)
        if category != txn.category or method != txn.classification_method:
            txn.category = category
            txn.classification_method = method
            txn.confidence = confidence
            updated += 1
    mark_recurring(db, user.id)
    db.commit()
    return {"updated": updated}
