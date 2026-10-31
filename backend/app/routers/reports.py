from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.reports import dashboard_stats, excel_report, monthly_summaries

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return dashboard_stats(db, user.id)


@router.get("/monthly")
def monthly(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return monthly_summaries(db, user.id)


@router.get("/export.xlsx")
def export_excel(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    content = excel_report(db, user.id)
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=spendsense-report.xlsx"},
    )
