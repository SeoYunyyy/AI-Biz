import httpx
import os
from datetime import datetime, timezone

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def save_content(user_id: str, url: str) -> dict | None:
    """1단계: URL만 즉시 저장 (analysis_status=processing)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers={**_headers(), "Prefer": "return=representation"},
                json={
                    "user_id": user_id,
                    "url": url,
                    "content_type": "other",
                    "analysis_status": "processing",
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            response.raise_for_status()
            data = response.json()
            return data[0] if data else None
    except httpx.HTTPError as e:
        print(f"[supabase_db] 초기 저장 오류: {e}")
        return None


async def update_content(content_id: str, metadata: dict, analysis: dict, collection_id: str | None = None, thumbnail_description: str = "") -> bool:
    """2단계: 분석 완료 후 전체 필드 업데이트"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents?id=eq.{content_id}",
                headers={**_headers(), "Prefer": "return=minimal"},
                json={
                    "content_type": metadata.get("platform", "other"),
                    "title": metadata.get("title", ""),
                    "description": metadata.get("summary", ""),
                    "thumbnail_url": metadata.get("thumbnail", ""),
                    "author": metadata.get("author", ""),
                    "metadata": {
                        "date": metadata.get("date", ""),
                        "original_url": metadata.get("original_url", ""),
                    },
                    "topics": analysis.get("tags", []),
                    "hashtags": [f"#{t}" for t in analysis.get("tags", [])],
                    "intent": [analysis.get("save_purpose", "")],
                    "category": analysis.get("category", "기타/알쓸신잡"),
                    "sub_category": analysis.get("sub_category", ""),
                    "has_deadline": analysis.get("has_deadline", False),
                    "deadline_date": analysis.get("deadline_date"),
                    "deadline_note": analysis.get("deadline_note"),
                    "thumbnail_description": thumbnail_description or None,
                    "analysis_status": "completed",
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "collection_id": collection_id,
                },
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[supabase_db] 업데이트 오류: {e}")
        return False


async def mark_failed(content_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents?id=eq.{content_id}",
                headers={**_headers(), "Prefer": "return=minimal"},
                json={"analysis_status": "failed"},
            )
    except httpx.HTTPError as e:
        print(f"[supabase_db] 실패 처리 오류: {e}")


async def check_duplicate(user_id: str, url: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "url": f"eq.{url}",
                    "select": "id,title,analysis_status,hashtags",
                    "limit": "1",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data[0] if data else None
    except httpx.HTTPError as e:
        print(f"[supabase_db] 중복 체크 오류: {e}")
        return None


async def get_or_create_collection(user_id: str, name: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/collections",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "name": f"eq.{name}",
                    "select": "id",
                    "limit": "1",
                },
            )
            response.raise_for_status()
            data = response.json()
            if data:
                return data[0]["id"]

            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/collections",
                headers={**_headers(), "Prefer": "return=representation"},
                json={"user_id": user_id, "name": name, "is_user_renamed": True},
            )
            response.raise_for_status()
            created = response.json()
            return created[0]["id"] if created else None
    except httpx.HTTPError as e:
        print(f"[supabase_db] 컬렉션 오류: {e}")
        return None


async def find_similar_contents(user_id: str, embedding: list, threshold: float = 0.5, limit: int = 3) -> list:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/match_user_contents",
                headers=_headers(),
                json={
                    "query_embedding": embedding,
                    "user_id_param": user_id,
                    "match_count": limit,
                },
            )
            response.raise_for_status()
            results = response.json()
            return [r for r in results if r.get("similarity", 0) >= threshold]
    except httpx.HTTPError as e:
        print(f"[supabase_db] 유사 콘텐츠 검색 오류: {e}")
        return []
