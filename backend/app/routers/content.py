"""GET /api/library, PATCH /api/contents/{id} — 콘텐츠 목록·수정."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.deps import get_current_user, CurrentUser
from app.services.supabase_client import supabase, log_event


router = APIRouter()


@router.get("/library")
def get_library(
    user: CurrentUser = Depends(get_current_user),
    category: str | None = Query(None, description="필터: FOOD, TRAVEL 등"),
    limit: int = Query(20, le=100),
    offset: int = 0,
):
    """저장 콘텐츠 목록 (최신순)."""
    q = (
        supabase.table("contents")
        .select("*, tags(tag)")
        .eq("user_id", user.id)
        .order("saved_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if category:
        q = q.eq("category", category)

    resp = q.execute()
    return {"items": resp.data, "limit": limit, "offset": offset}


class ContentUpdate(BaseModel):
    category: str | None = None
    tags: list[str] | None = None
    summary: str | None = None


@router.patch("/contents/{content_id}")
def update_content(
    content_id: str,
    update: ContentUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """사용자가 인라인으로 카테고리·태그 수정.

    수정된 데이터는 향후 few-shot 프롬프트 보강에도 활용 가능.
    """
    # 소유자 검증
    own = (
        supabase.table("contents")
        .select("id")
        .eq("id", content_id)
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not own.data:
        raise HTTPException(status_code=404, detail="Content not found")

    patch = {k: v for k, v in update.model_dump().items() if v is not None and k != "tags"}
    if patch:
        supabase.table("contents").update(patch).eq("id", content_id).execute()

    if update.tags is not None:
        supabase.table("tags").delete().eq("content_id", content_id).execute()
        if update.tags:
            supabase.table("tags").insert(
                [{"content_id": content_id, "tag": t} for t in update.tags]
            ).execute()

    log_event(user.id, "edit", {"content_id": content_id})
    return {"ok": True}
