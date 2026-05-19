"""
아이템 자동지급 서비스

핵심 로직:
1. 콘텐츠 저장 시 topics[] → 카테고리 매핑
2. 해당 카테고리 카운트 +1
3. 카운트가 ITEM_THRESHOLD(5)에 도달하면 → pending 아이템 생성
4. 사용자가 확인 시 → claimed로 변경
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.gamification import Item, UserCategoryCount, UserItem
from schemas.gamification import ProcessContentResponse, UserItemResponse
from utils.category_mapper import ITEM_THRESHOLD, map_topics_to_category


# ─── 핵심 함수: 콘텐츠 저장 후 호출 ──────────────────────────

async def process_content_for_reward(
    db: AsyncSession,
    user_id: UUID,
    topics: list[str],
) -> ProcessContentResponse:
    """
    콘텐츠가 저장될 때마다 호출.
    카테고리 카운트를 올리고, 5개 달성 시 pending 아이템을 생성한다.

    Args:
        db:      AsyncSession
        user_id: 사용자 UUID
        topics:  AI 분석으로 추출된 topics 리스트

    Returns:
        ProcessContentResponse: 카운트 현황 + 새로 pending된 아이템 목록
    """
    # 1. topics → 카테고리 매핑
    category = map_topics_to_category(topics)

    if not category:
        return ProcessContentResponse(
            category=None,
            current_count=0,
            threshold=ITEM_THRESHOLD,
            newly_pending=[],
            message="카테고리를 분류할 수 없는 콘텐츠입니다.",
        )

    # 2. 카테고리 카운트 업데이트 (없으면 생성, 있으면 +1)
    current_count = await _upsert_category_count(db, user_id, category)

    # 3. ITEM_THRESHOLD 달성 시 pending 아이템 생성
    newly_pending: list[UserItem] = []
    if current_count == ITEM_THRESHOLD:
        newly_pending = await _grant_pending_item(db, user_id, category)

    await db.commit()

    # 4. 응답 메시지 생성
    message = _build_message(category, current_count, bool(newly_pending))

    return ProcessContentResponse(
        category=category,
        current_count=current_count,
        threshold=ITEM_THRESHOLD,
        newly_pending=[UserItemResponse.model_validate(ui) for ui in newly_pending],
        message=message,
    )


# ─── 카운트 업데이트 ──────────────────────────────────────

async def _upsert_category_count(
    db: AsyncSession,
    user_id: UUID,
    category: str,
) -> int:
    """카테고리 카운트 upsert 후 현재 카운트 반환"""
    result = await db.execute(
        select(UserCategoryCount).where(
            UserCategoryCount.user_id == user_id,
            UserCategoryCount.category == category,
        ).with_for_update()  # 동시성 충돌 방지
    )
    row = result.scalar_one_or_none()

    if row:
        row.count += 1
        row.last_updated = datetime.utcnow()
        current_count = row.count
    else:
        new_row = UserCategoryCount(
            user_id=user_id,
            category=category,
            count=1,
        )
        db.add(new_row)
        current_count = 1

    await db.flush()
    return current_count


# ─── 아이템 지급 ──────────────────────────────────────────

async def _grant_pending_item(
    db: AsyncSession,
    user_id: UUID,
    category: str,
) -> list[UserItem]:
    """
    해당 카테고리 아이템을 pending 상태로 생성.
    이미 지급된 아이템이면 스킵 (중복 지급 방지).
    """
    # 카테고리에 해당하는 아이템 조회
    item_result = await db.execute(
        select(Item).where(Item.category == category)
    )
    item = item_result.scalar_one_or_none()

    if not item:
        return []

    # 이미 지급(pending 또는 claimed)된 아이템인지 확인
    existing_result = await db.execute(
        select(UserItem).where(
            UserItem.user_id == user_id,
            UserItem.item_id == item.id,
        )
    )
    if existing_result.scalar_one_or_none():
        return []  # 이미 지급됨 → 스킵

    # pending 아이템 생성
    new_user_item = UserItem(
        user_id=user_id,
        item_id=item.id,
        category=category,
        status="pending",
    )
    db.add(new_user_item)
    await db.flush()

    # 관계(item) 포함해서 로드
    await db.refresh(new_user_item, attribute_names=["item"])
    return [new_user_item]


# ─── 조회 함수들 ──────────────────────────────────────────

async def get_pending_items(
    db: AsyncSession,
    user_id: UUID,
) -> list[UserItem]:
    """사용자의 미수령(pending) 아이템 목록"""
    result = await db.execute(
        select(UserItem)
        .where(UserItem.user_id == user_id, UserItem.status == "pending")
        .join(UserItem.item)
    )
    return list(result.scalars().all())


async def get_claimed_items(
    db: AsyncSession,
    user_id: UUID,
) -> list[UserItem]:
    """사용자가 수령 완료한 아이템 목록"""
    result = await db.execute(
        select(UserItem)
        .where(UserItem.user_id == user_id, UserItem.status == "claimed")
        .join(UserItem.item)
    )
    return list(result.scalars().all())


async def get_category_counts(
    db: AsyncSession,
    user_id: UUID,
) -> list[UserCategoryCount]:
    """사용자의 카테고리별 저장 카운트 목록 (많은 순)"""
    result = await db.execute(
        select(UserCategoryCount)
        .where(UserCategoryCount.user_id == user_id)
        .order_by(UserCategoryCount.count.desc())
    )
    return list(result.scalars().all())


# ─── 아이템 수령 ──────────────────────────────────────────

async def claim_items(
    db: AsyncSession,
    user_id: UUID,
    user_item_ids: list[UUID],
) -> list[UserItem]:
    """
    pending 아이템을 claimed로 변경 (사용자가 수령 버튼 클릭 시).

    Args:
        db:            AsyncSession
        user_id:       본인 확인용 (다른 사람 아이템 수령 방지)
        user_item_ids: 수령할 user_item id 목록
    """
    now = datetime.utcnow()

    await db.execute(
        update(UserItem)
        .where(
            UserItem.id.in_(user_item_ids),
            UserItem.user_id == user_id,
            UserItem.status == "pending",   # pending 상태만 수령 가능
        )
        .values(status="claimed", claimed_at=now)
    )
    await db.commit()

    # 수령된 아이템 목록 반환
    result = await db.execute(
        select(UserItem)
        .where(UserItem.id.in_(user_item_ids))
        .join(UserItem.item)
    )
    return list(result.scalars().all())


# ─── 메시지 생성 ──────────────────────────────────────────

def _build_message(category: str, count: int, item_granted: bool) -> str:
    """사용자에게 보여줄 피드백 메시지"""
    remaining = ITEM_THRESHOLD - count

    if item_granted:
        return f"🎉 [{category}] 카테고리 아이템을 획득했어요! 방을 꾸며보세요."
    elif remaining > 0:
        return f"[{category}] 카테고리 {count}/{ITEM_THRESHOLD} — 아이템까지 {remaining}개 남았어요!"
    else:
        return f"[{category}] 카테고리 저장 완료!"
