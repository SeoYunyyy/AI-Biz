from pydantic import BaseModel
from uuid import UUID
from datetime import date, datetime
from typing import Optional


# ─── 월간 캘린더 ──────────────────────────────────────────

class DayCount(BaseModel):
    """캘린더에서 날짜 점(dot) 표시용 - 해당 날짜 저장 개수"""
    date:  date
    count: int


class MonthlyCalendarResponse(BaseModel):
    """월간 캘린더 응답 - 콘텐츠가 있는 날짜 목록만 반환"""
    year:  int
    month: int
    days:  list[DayCount]   # 콘텐츠가 1개 이상인 날짜만 포함


# ─── 일별 콘텐츠 ──────────────────────────────────────────

class ContentSummary(BaseModel):
    """캘린더 날짜 클릭 시 보여줄 콘텐츠 카드"""
    id:            UUID
    url:           str
    title:         Optional[str]
    description:   Optional[str]
    thumbnail_url: Optional[str]
    content_type:  Optional[str]       # "youtube" | "blog" | "other"
    topics:        Optional[list[str]]
    hashtags:      Optional[list[str]]
    category:      Optional[str]       # topics → 카테고리 자동 매핑
    saved_at:      datetime

    class Config:
        from_attributes = True


class DailyContentsResponse(BaseModel):
    """특정 날짜의 저장 콘텐츠 목록"""
    date:     date
    total:    int
    contents: list[ContentSummary]
