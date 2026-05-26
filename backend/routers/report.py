from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.report import generate_report, generate_weekly_report

router = APIRouter(prefix="/report", tags=["report"])


@router.get("/monthly/{user_id}", summary="월간 리포트")
async def get_monthly_report(
    user_id: UUID,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
):
    return await generate_report(db, user_id, year, month)


@router.get("/weekly/{user_id}", summary="주간 리포트 (week: 1~5)")
async def get_weekly_report(
    user_id: UUID,
    year: int,
    month: int,
    week: int,
    db: AsyncSession = Depends(get_db),
):
    return await generate_weekly_report(db, user_id, year, month, week)
