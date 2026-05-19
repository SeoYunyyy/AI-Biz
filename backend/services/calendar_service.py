"""
캘린더 서비스

주요 기능:
1. 월간 캘린더: 해당 월에 콘텐츠가 있는 날짜 + 개수 반환 (캘린더 점 표시용)
2. 일별 콘텐츠: 특정 날짜에 저장한 콘텐츠 목록 반환
"""

from datetime import date
from uuid import UUID

from sqlalchemy import func, extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.content import Content
from schemas.calendar import ContentSummary, DayCount, DailyContentsResponse, MonthlyCalendarResponse
from utils.category_mapper import map_topics_to_category


# ─── 1. 월간 캘린더 데이터 ────────────────────────────────

async def get_monthly_calendar(
    db: AsyncSession,
    user_id: UUID,
    year: int,
    month: int,
) -> MonthlyCalendarResponse:
    """
    해당 월에 콘텐츠를 저장한 날짜 목록과 개수를 반환.
    프론트엔드 캘린더에서 날짜 아래 점(dot) 표시에 사용.

    예시 응답:
        year: 2026, month: 5
        days: [
            {date: "2026-05-01", count: 2},
            {date: "2026-05-15", count: 5},
        ]
    """
    result = await db.execute(
        select(
            func.date(Content.saved_at).label("day"),
            func.count(Content.id).label("count"),
        )
        .where(
            Content.user_id == user_id,
            extract("year",  Content.saved_at) == year,
            extract("month", Content.saved_at) == month,
        )
        .group_by(func.date(Content.saved_at))
        .order_by(func.date(Content.saved_at))
    )
    rows = result.all()

    days = [DayCount(date=row.day, count=row.count) for row in rows]

    return MonthlyCalendarResponse(year=year, month=month, days=days)


# ─── 2. 일별 콘텐츠 목록 ──────────────────────────────────

async def get_daily_contents(
    db: AsyncSession,
    user_id: UUID,
    year: int,
    month: int,
    day: int,
) -> DailyContentsResponse:
    """
    특정 날짜에 저장한 콘텐츠 목록 반환.
    캘린더에서 날짜를 클릭했을 때 호출.
    """
    target_date = date(year, month, day)

    result = await db.execute(
        select(Content)
        .where(
            Content.user_id == user_id,
            func.date(Content.saved_at) == target_date,
        )
        .order_by(Content.saved_at.desc())   # 최신 저장순
    )
    contents = list(result.scalars().all())

    # topics → 카테고리 자동 매핑
    summaries = [
        ContentSummary(
            id=c.id,
            url=c.url,
            title=c.title,
            description=c.description,
            thumbnail_url=c.thumbnail_url,
            content_type=c.content_type,
            topics=c.topics,
            hashtags=c.hashtags,
            category=map_topics_to_category(c.topics or []),
            saved_at=c.saved_at,
        )
        for c in contents
    ]

    return DailyContentsResponse(
        date=target_date,
        total=len(summaries),
        contents=summaries,
    )
