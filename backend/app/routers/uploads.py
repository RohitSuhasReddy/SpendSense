from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Transaction, UploadedFile, User
from app.schemas import UploadResult
from app.services.classifier import classify_transactions, mark_recurring
from app.services.pdf_parser import parse_statement_pdf

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/pdf", response_model=UploadResult)
async def upload_pdf(
    file: UploadFile = File(...),
    source_type: str = Form("auto"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF statement")

    content = await file.read()
    if len(content) < 20:
        raise HTTPException(status_code=400, detail="Empty PDF")

    parsed = parse_statement_pdf(content, source_type)
    if not parsed["transactions"]:
        raise HTTPException(
            status_code=422,
            detail="Could not extract transactions. Share a sample statement so we can tune the parser.",
        )

    upload = UploadedFile(
        user_id=user.id,
        filename=file.filename,
        source_type=parsed["source_type"],
        bank_hint=parsed["bank_hint"],
        transaction_count=0,
    )
    db.add(upload)
    db.flush()

    skipped = 0
    new_items: list[dict] = []
    for item in parsed["transactions"]:
        duplicate = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user.id,
                Transaction.txn_date == item["txn_date"],
                Transaction.amount == item["amount"],
                Transaction.raw_description == item["raw_description"],
            )
            .one_or_none()
        )
        if duplicate:
            skipped += 1
        else:
            new_items.append(item)

    classifications = classify_transactions(
        db,
        user.id,
        [
            {
                "merchant": item["merchant"],
                "description": item["cleaned_description"],
            }
            for item in new_items
        ],
    )

    classified: dict[str, int] = {}
    for item, (category, method, confidence) in zip(new_items, classifications):
        db.add(
            Transaction(
                user_id=user.id,
                upload_id=upload.id,
                txn_date=item["txn_date"],
                amount=item["amount"],
                direction=item["direction"],
                raw_description=item["raw_description"],
                cleaned_description=item["cleaned_description"],
                merchant=item["merchant"],
                category=category,
                source=item["source"],
                classification_method=method,
                confidence=confidence,
            )
        )
        classified[method] = classified.get(method, 0) + 1

    imported = len(new_items)
    upload.transaction_count = imported
    mark_recurring(db, user.id)
    db.commit()
    return UploadResult(
        upload_id=upload.id,
        filename=file.filename,
        source_type=parsed["source_type"],
        bank_hint=parsed["bank_hint"],
        imported=imported,
        skipped=skipped,
        classified=classified,
    )
