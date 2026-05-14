"""Supabase 클라이언트 — 인증·DB·스토리지 통합 접근."""
from supabase import create_client, Client

from app.config import settings


# Service Role Key 는 서버에서만 사용 (RLS 우회 가능)
supabase: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_key,
)


def is_duplicate(user_id: str, url: str) -> bool:
    """동일 사용자가 같은 URL을 이미 저장했는지."""
    resp = (
        supabase.table("contents")
        .select("id")
        .eq("user_id", user_id)
        .eq("url", url)
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def save_content(state: dict) -> str:
    """save_agent 의 최종 state 를 DB에 INSERT.

    Args:
        state: { user_id, url, metadata, ai_result, embedding } 를 포함하는 dict

    Returns:
        생성된 content id (UUID 문자열)
    """
    meta = state["metadata"]
    ai = state["ai_result"]

    insert = {
        "user_id": state["user_id"],
        "url": state["url"],
        "platform": meta.get("platform"),
        "title": meta.get("title"),
        "description": meta.get("description"),
        "thumbnail_url": meta.get("thumbnail_url"),
        "category": ai.get("category"),
        "summary": ai.get("summary"),
        "mood": ai.get("mood"),
        "embedding": state["embedding"],
    }
    resp = supabase.table("contents").insert(insert).execute()
    content_id = resp.data[0]["id"]

    # 태그를 별도 테이블에 저장
    tags = ai.get("tags") or []
    if tags:
        supabase.table("tags").insert(
            [{"content_id": content_id, "tag": t} for t in tags]
        ).execute()

    return content_id


def log_event(user_id: str, event_type: str, payload: dict | None = None) -> None:
    """행동 로그 저장 — 비동기 fire-and-forget 권장."""
    try:
        supabase.table("events").insert({
            "user_id": user_id,
            "event_type": event_type,
            "payload": payload or {},
        }).execute()
    except Exception:
        pass  # 로깅 실패가 비즈니스에 영향을 주면 안 됨
