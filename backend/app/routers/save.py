"""POST /api/save — URL 저장."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from app.agents.save_agent import save_agent
from app.deps import get_current_user, CurrentUser
from app.services.supabase_client import log_event


router = APIRouter()


class SaveRequest(BaseModel):
    url: HttpUrl
    user_note: str | None = None


class SaveResponse(BaseModel):
    id: str | None
    title: str
    category: str
    tags: list[str]
    summary: str
    thumbnail_url: str | None
    is_duplicate: bool


@router.post("/save", response_model=SaveResponse)
def save_content_endpoint(
    req: SaveRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """URL 저장 + 자동 분류 → 결과 반환."""
    initial: dict = {
        "user_id": user.id,
        "url": str(req.url),
    }

    result = save_agent.invoke(initial)

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    if result.get("is_duplicate"):
        return SaveResponse(
            id=None,
            title="",
            category="",
            tags=[],
            summary="이미 저장된 콘텐츠입니다.",
            thumbnail_url=None,
            is_duplicate=True,
        )

    log_event(user.id, "save", {"content_id": str(result["content_id"])})

    return SaveResponse(
        id=str(result["content_id"]),
        title=result["metadata"]["title"],
        category=result["ai_result"]["category"],
        tags=result["ai_result"]["tags"],
        summary=result["ai_result"]["summary"],
        thumbnail_url=result["metadata"].get("thumbnail_url"),
        is_duplicate=False,
    )
