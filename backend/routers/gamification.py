from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.gamification import (
    CategoryProgressResponse,
    ClaimItemRequest,
    ProcessContentRequest,
    ProcessContentResponse,
    UserItemResponse,
)
from services.item_service import (
    claim_items,
    get_category_counts,
    get_claimed_items,
    get_pending_items,
    process_content_for_reward,
)
from utils.category_mapper import ITEM_THRESHOLD

router = APIRouter(prefix="/gamification", tags=["gamification"])


# ─── 1. 콘텐츠 저장 후 아이템 체크 (핵심 API) ────────────────

@router.post(
    "/process-content",
    response_model=ProcessContentResponse,
    summary="콘텐츠 저장 후 아이템 지급 체크",
    description=(
        "콘텐츠가 저장·분석된 직후 호출. "
        "topics[]를 카테고리로 매핑하고, 카운트가 5에 도달하면 pending 아이템을 생성한다."
    ),
)
async def process_content(
    request: ProcessContentRequest,
    db: AsyncSession = Depends(get_db),
):
    return await process_content_for_reward(db, request.user_id, request.topics)


# ─── 2. 미수령 아이템 조회 ────────────────────────────────

@router.get(
    "/items/pending/{user_id}",
    response_model=list[UserItemResponse],
    summary="미수령(pending) 아이템 목록",
)
async def get_pending(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await get_pending_items(db, user_id)


# ─── 3. 수령 완료 아이템 조회 ─────────────────────────────

@router.get(
    "/items/{user_id}",
    response_model=list[UserItemResponse],
    summary="수령 완료 아이템 목록 (방 꾸미기용)",
)
async def get_items(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await get_claimed_items(db, user_id)


# ─── 4. 아이템 수령 처리 ──────────────────────────────────

@router.post(
    "/items/claim",
    response_model=list[UserItemResponse],
    summary="pending 아이템 수령",
    description="사용자가 '수령하기' 버튼 클릭 시 호출. pending → claimed로 변경.",
)
async def claim(
    request: ClaimItemRequest,
    db: AsyncSession = Depends(get_db),
):
    if not request.user_item_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수령할 아이템 id가 없습니다.",
        )
    return await claim_items(db, request.user_id, request.user_item_ids)


# ─── 5. 카테고리별 진행 현황 ──────────────────────────────

@router.get(
    "/categories/{user_id}",
    response_model=list[CategoryProgressResponse],
    summary="카테고리별 저장 현황 (진행률 포함)",
)
async def get_categories(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    counts = await get_category_counts(db, user_id)
    return [
        CategoryProgressResponse(
            category=c.category,
            count=c.count,
            threshold=ITEM_THRESHOLD,
            progress=round(min(c.count / ITEM_THRESHOLD * 100, 100.0), 1),
            completed=c.count >= ITEM_THRESHOLD,
        )
        for c in counts
    ]
