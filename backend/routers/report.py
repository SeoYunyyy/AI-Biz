from fastapi import APIRouter
from services.report import generate_report, generate_weekly_report

router = APIRouter(prefix="/report", tags=["report"])


@router.get("/monthly/{user_id}")
async def get_monthly_report(user_id: str, year: int, month: int):
    """월간 리포트"""
    return await generate_report(user_id, year, month)


@router.get("/weekly/{user_id}")
async def get_weekly_report(user_id: str, year: int, month: int, week: int):
    """주간 리포트 (week: 1~5)"""
    return await generate_weekly_report(user_id, year, month, week)
