from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.reports import dashboard_stats, excel_report, monthly_summaries

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/dashboard")
def dashboard(
    month: str | None = Query(default=None, description="YYYY-MM"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return dashboard_stats(db, user.id, month=month)


@router.get("/monthly")
def monthly(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return monthly_summaries(db, user.id)


@router.get("/export.xlsx")
def export_excel(
    period: str = Query(
        default="current_month",
        description="selected_month | current_month | previous_month | last_6_months | last_12_months | custom",
    ),
    selected_month: str | None = Query(default=None, description="YYYY-MM"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        content, filename = excel_report(
            db,
            user.id,
            period=period,
            selected_month=selected_month,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
