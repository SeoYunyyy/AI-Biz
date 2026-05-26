from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


# ─── 아이템 ───────────────────────────────────────────────

class ItemResponse(BaseModel):
    id:          UUID
    name:        str
    category:    str
    emoji:       Optional[str]
    description: Optional[str]

    class Config:
        from_attributes = True


# ─── 사용자 보유 아이템 ────────────────────────────────────

class UserItemResponse(BaseModel):
    id:         UUID
    user_id:    UUID
    item_id:    UUID
    category:   str
    status:     str           # "pending" | "claimed"
    earned_at:  datetime
    claimed_at: Optional[datetime]
    item:       ItemResponse

    class Config:
        from_attributes = True


# ─── 카테고리 진행 현황 ────────────────────────────────────

class CategoryProgressResponse(BaseModel):
    category:  str
    count:     int
    threshold: int            # 목표 (5)
    progress:  float          # 달성률 0.0 ~ 100.0
    completed: bool           # 5개 이상이면 True


# ─── 요청 / 응답 ─────────────────────────────────────────

class ProcessContentRequest(BaseModel):
    """콘텐츠 저장 후 아이템 지급 체크 요청"""
    user_id: UUID
    topics:  list[str]        # AI 분석으로 추출된 topics[]


class ClaimItemRequest(BaseModel):
    """pending 아이템 수령 요청"""
    user_id:       UUID
    user_item_ids: list[UUID]


class ProcessContentResponse(BaseModel):
    """아이템 지급 체크 결과"""
    category:      Optional[str]      # 매핑된 카테고리
    current_count: int                # 현재 카테고리 카운트
    threshold:     int                # 목표 카운트 (5)
    newly_pending: list[UserItemResponse]  # 이번에 새로 pending된 아이템
    message:       str                # 사용자에게 보여줄 메시지
