from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.calendar import DailyContentsResponse, MonthlyCalendarResponse
from services.calendar_service import get_daily_contents, get_monthly_calendar

router = APIRouter(prefix="/calendar", tags=["calendar"])


# ─── 1. 월간 캘린더 ──────────────────────────────────────

@router.get(
    "/{user_id}/{year}/{month}",
    response_model=MonthlyCalendarResponse,
    summary="월간 캘린더 조회",
    description=(
        "해당 월에 콘텐츠를 저장한 날짜와 개수를 반환. "
        "프론트엔드 캘린더에서 날짜 아래 점(dot) 표시에 사용."
    ),
)
async def monthly_calendar(
    user_id: UUID,
    year:    int = Path(..., ge=2020, le=2100, description="연도 (예: 2026)"),
    month:   int = Path(..., ge=1,    le=12,   description="월 (1~12)"),
    db: AsyncSession = Depends(get_db),
):
    return await get_monthly_calendar(db, user_id, year, month)


# ─── 2. 특정 날짜 콘텐츠 목록 ────────────────────────────

@router.get(
    "/{user_id}/{year}/{month}/{day}",
    response_model=DailyContentsResponse,
    summary="날짜별 저장 콘텐츠 조회",
    description="캘린더에서 특정 날짜 클릭 시 그 날 저장한 콘텐츠 목록 반환.",
)
async def daily_contents(
    user_id: UUID,
    year:    int = Path(..., ge=2020, le=2100),
    month:   int = Path(..., ge=1,    le=12),
    day:     int = Path(..., ge=1,    le=31),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_daily_contents(db, user_id, year, month, day)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{year}-{month:02d}-{day:02d} 는 유효하지 않은 날짜입니다.",
        )
