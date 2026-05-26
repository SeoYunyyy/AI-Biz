"""GET /api/report/monthly — 월간 취향 리포트."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.deps import get_current_user, CurrentUser
from app.services.report_generator import generate_monthly_report
from app.services.supabase_client import log_event


router = APIRouter()


@router.get("/report/monthly")
def monthly_report(
    user: CurrentUser = Depends(get_current_user),
    month: str | None = Query(None, description="YYYY-MM (없으면 이번 달)"),
):
    """월간 취향 리포트 — 내러티브 + 통계.

    Args:
        month: "2025-10" 형식. 미지정 시 현재 월.
    """
    if month is None:
        month = datetime.utcnow().strftime("%Y-%m")

    report = generate_monthly_report(user.id, month)
    log_event(user.id, "report", {"month": month})
    return {"month": month, **report}
