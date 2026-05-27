# app/services/database.py

import os
import logging
from datetime import datetime, timezone

from app.http_client import get_client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL_HERE")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "YOUR_SUPABASE_KEY_HERE")


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


# ── 저장 ──────────────────────────────────────────────────────────────────────

async def save_content(user_id: str, url: str) -> dict | None:
    """1단계: URL만 먼저 즉시 저장 (analysis_status = 'processing')"""
    try:
        client = get_client()
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
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None

    except Exception as e:
        logger.error(f"[database] 초기 저장 오류: {e}")
        return None


async def update_content(
    content_id: str,
    metadata: dict,
    analysis: dict,
    collection_id: str | None = None,
    thumbnail_description: str = "",
) -> bool:
    """2단계: AI 분석 완료 후 나머지 필드 업데이트 (analysis_status = 'completed')"""
    try:
        client = get_client()
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/contents?id=eq.{content_id}",
            headers={**_headers(), "Prefer": "return=minimal"},
            json={
                # 메타데이터
                "content_type": metadata.get("platform", "other"),
                "title": metadata.get("title", ""),
                "description": metadata.get("summary", ""),
                "thumbnail_url": metadata.get("thumbnail", ""),
                "author": metadata.get("author", ""),
                "metadata": {
                    "date": metadata.get("date", ""),
                    "original_url": metadata.get("original_url", ""),
                    "deadline_items": analysis.get("deadline_items", []),
                },
                # AI 분석 결과 (Fix 2: one_line_summary, detailed_summary 추가)
                "one_line_summary": analysis.get("one_line_summary", ""),
                "detailed_summary": analysis.get("detailed_summary", ""),
                "topics": analysis.get("tags", []),
                "hashtags": [f"#{t}" for t in analysis.get("tags", [])],
                "intent": [analysis.get("save_purpose", "")],
                "category": analysis.get("category", "기타/알쓸신잡"),
                "sub_category": analysis.get("sub_category", ""),
                "has_deadline": analysis.get("has_deadline", False),
                "deadline_date": analysis.get("deadline_date"),
                "deadline_note": analysis.get("deadline_note"),
                # 썸네일 Vision
                "thumbnail_description": thumbnail_description or None,
                # 상태
                "analysis_status": "completed",
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "collection_id": collection_id,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return True

    except Exception as e:
        logger.error(f"[database] 업데이트 오류: {e}")
        return False


async def mark_failed(content_id: str) -> None:
    """분석 실패 시 status만 failed로 업데이트"""
    try:
        client = get_client()
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/contents?id=eq.{content_id}",
            headers={**_headers(), "Prefer": "return=minimal"},
            json={"analysis_status": "failed"},
            timeout=10.0,
        )
    except Exception as e:
        logger.error(f"[database] 실패 처리 오류: {e}")


# ── 중복 체크 ──────────────────────────────────────────────────────────────────

async def check_duplicate(user_id: str, url: str) -> dict | None:
    """같은 유저가 같은 URL 저장하려 할 때 중복 감지"""
    try:
        client = get_client()
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/contents",
            headers=_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "url": f"eq.{url}",
                "select": "id,title,analysis_status,hashtags",
                "limit": "1",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None

    except Exception as e:
        logger.error(f"[database] 중복 체크 오류: {e}")
        return None


# ── 콘텐츠 단건 조회 ───────────────────────────────────────────────────────────

async def get_content(content_id: str, user_id: str | None = None) -> dict | None:
    """content_id로 단건 조회.
    user_id를 전달하면 소유권 검증 포함 — 타인의 콘텐츠는 None 반환.
    """
    try:
        client = get_client()
        params: dict = {
            "id": f"eq.{content_id}",
            "select": "id,title,thumbnail_url,platform,category,one_line_summary,tags,has_deadline,deadline_date,deadline_note,sub_category,analysis_status",
            "limit": "1",
        }
        if user_id:
            params["user_id"] = f"eq.{user_id}"
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/contents",
            headers=_headers(),
            params=params,
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None

    except Exception as e:
        logger.error(f"[database] 단건 조회 오류: {e}")
        return None


# ── 검색 ──────────────────────────────────────────────────────────────────────

async def get_contents_by_ids(content_ids: list[str]) -> dict[str, dict]:
    """ID 목록으로 콘텐츠 일괄 조회 → {id: content} 맵 반환 (Fix 2: 썸네일·해시태그 보강용)"""
    if not content_ids:
        return {}
    try:
        client = get_client()
        ids_str = f"({','.join(content_ids)})"
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/contents",
            headers=_headers(),
            params={
                "id": f"in.{ids_str}",
                "select": "id,title,thumbnail_url,hashtags,one_line_summary,url,content_type",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return {c["id"]: c for c in response.json()}
    except Exception as e:
        logger.error(f"[database] 일괄 조회 오류: {e}")
        return {}


async def search_contents(
    user_id: str,
    query_embedding: list[float],
    limit: int = 3,
    threshold: float = 0.3,
    exclude_ids: list[str] | None = None,
) -> list[dict]:
    """벡터 유사도 검색 후 썸네일·해시태그를 보강해 반환.
    exclude_ids: 이미 사용자에게 보여준 콘텐츠 ID — 결과에서 제외."""
    try:
        exclude_set = set(exclude_ids or [])
        # 제외 ID만큼 더 가져와 필터 후에도 limit개를 채울 수 있도록
        fetch_count = (limit + len(exclude_set)) * 3

        client = get_client()
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/match_user_contents",
            headers=_headers(),
            json={
                "query_embedding": query_embedding,
                "user_id_param": user_id,
                "match_count": fetch_count,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        results = response.json()

        filtered = [
            r for r in results
            if r.get("similarity", 0) >= threshold and r["id"] not in exclude_set
        ][:limit]

        # RPC 결과에 없는 thumbnail_url, hashtags 등을 별도 쿼리로 보강
        if filtered:
            ids = [r["id"] for r in filtered]
            enriched = await get_contents_by_ids(ids)
            for r in filtered:
                extra = enriched.get(r["id"], {})
                r.setdefault("thumbnail_url", extra.get("thumbnail_url", ""))
                r.setdefault("hashtags", extra.get("hashtags", []))
                r.setdefault("one_line_summary", extra.get("one_line_summary", ""))
                r.setdefault("url", extra.get("url", ""))

        return filtered

    except Exception as e:
        logger.error(f"[database] 검색 오류: {e}")
        return []


async def find_similar_contents(
    user_id: str,
    embedding: list[float],
    threshold: float = 0.5,
    limit: int = 3,
) -> list[dict]:
    """새로 저장하려는 콘텐츠와 유사한 기존 콘텐츠 검색"""
    try:
        client = get_client()
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/match_user_contents",
            headers=_headers(),
            json={
                "query_embedding": embedding,
                "user_id_param": user_id,
                "match_count": limit,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        results = response.json()
        return [r for r in results if r.get("similarity", 0) >= threshold]

    except Exception as e:
        logger.error(f"[database] 유사 콘텐츠 검색 오류: {e}")
        return []


# ── 마감기한 ───────────────────────────────────────────────────────────────────

async def fetch_deadlines(user_id: str) -> list[dict]:
    """마감기한 있는 콘텐츠를 마감일 오름차순으로 반환"""
    try:
        client = get_client()
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/contents",
            headers=_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "has_deadline": "eq.true",
                "select": "id,title,url,deadline_date,deadline_note,thumbnail_url",
                "order": "deadline_date.asc",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"[database] 마감기한 조회 오류: {e}")
        return []


# ── 컬렉션(폴더) ───────────────────────────────────────────────────────────────

async def get_or_create_collection(user_id: str, name: str) -> str | None:
    """폴더 이름으로 조회, 없으면 생성해서 collection_id 반환"""
    try:
        client = get_client()
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/collections",
            headers=_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "name": f"eq.{name}",
                "select": "id",
                "limit": "1",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        if data:
            return data[0]["id"]

        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/collections",
            headers={**_headers(), "Prefer": "return=representation"},
            json={
                "user_id": user_id,
                "name": name,
                "is_user_renamed": True,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        created = response.json()
        return created[0]["id"] if created else None

    except Exception as e:
        logger.error(f"[database] 컬렉션 오류: {e}")
        return None


async def get_collections(user_id: str) -> list[dict]:
    """사용자 폴더 목록 전체 조회"""
    try:
        client = get_client()
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/collections",
            headers=_headers(),
            params={
                "user_id": f"eq.{user_id}",
                "select": "id,name,emoji,content_count,created_at",
                "order": "created_at.asc",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"[database] 폴더 목록 조회 오류: {e}")
        return []


# ── 콘텐츠 삭제 ────────────────────────────────────────────────────────────────

async def delete_content(content_id: str, user_id: str) -> bool:
    """콘텐츠 삭제 (소유권 검증 포함)
    user_id 조건을 DELETE 쿼리에 함께 걸어 타인의 콘텐츠를 삭제하지 못하도록 보호.
    """
    try:
        client = get_client()
        response = await client.delete(
            f"{SUPABASE_URL}/rest/v1/contents",
            headers={**_headers(), "Prefer": "return=minimal"},
            params={
                "id": f"eq.{content_id}",
                "user_id": f"eq.{user_id}",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"[database] 콘텐츠 삭제 오류: {e}")
        return False


# ── 콘텐츠 목록 조회 (필터 + 페이지네이션) ────────────────────────────────────

async def list_contents(
    user_id: str,
    category: str | None = None,
    platform: str | None = None,
    collection_id: str | None = None,
    date_from: str | None = None,  # YYYY-MM-DD
    date_to: str | None = None,    # YYYY-MM-DD
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """필터·페이지네이션 적용 콘텐츠 목록 조회.
    날짜 범위처럼 동일 컬럼에 여러 조건이 붙을 수 있으므로 params를 튜플 리스트로 구성.
    """
    try:
        client = get_client()
        params: list[tuple[str, str]] = [
            ("user_id", f"eq.{user_id}"),
            (
                "select",
                "id,title,url,thumbnail_url,content_type,category,sub_category,"
                "one_line_summary,hashtags,analysis_status,saved_at,"
                "has_deadline,deadline_date,collection_id",
            ),
            ("order", "saved_at.desc"),
            ("limit", str(limit)),
            ("offset", str(offset)),
        ]
        if category:
            params.append(("category", f"eq.{category}"))
        if platform:
            params.append(("content_type", f"eq.{platform}"))
        if collection_id:
            params.append(("collection_id", f"eq.{collection_id}"))
        if date_from:
            params.append(("saved_at", f"gte.{date_from}"))
        if date_to:
            params.append(("saved_at", f"lte.{date_to}"))

        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/contents",
            headers=_headers(),
            params=params,
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"[database] 목록 조회 오류: {e}")
        return []


# ── 폴더별 콘텐츠 조회 ─────────────────────────────────────────────────────────

async def get_collection_contents(
    collection_id: str,
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """특정 폴더의 콘텐츠 목록 조회 (list_contents의 collection_id 필터 래퍼)"""
    return await list_contents(
        user_id=user_id,
        collection_id=collection_id,
        limit=limit,
        offset=offset,
    )


# ── 폴더 삭제·이름 변경 ────────────────────────────────────────────────────────

async def delete_collection(collection_id: str, user_id: str) -> bool:
    """폴더 삭제.
    FK 제약으로 인한 실패를 방지하기 위해 소속 콘텐츠의 collection_id를
    먼저 null로 해제한 뒤 폴더를 삭제한다.
    """
    try:
        client = get_client()
        # 1) 폴더 소속 콘텐츠의 collection_id → null 해제
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/contents",
            headers={**_headers(), "Prefer": "return=minimal"},
            params={
                "collection_id": f"eq.{collection_id}",
                "user_id": f"eq.{user_id}",
            },
            json={"collection_id": None},
            timeout=10.0,
        )
        # 2) 폴더 삭제 (소유권 검증 포함)
        response = await client.delete(
            f"{SUPABASE_URL}/rest/v1/collections",
            headers={**_headers(), "Prefer": "return=minimal"},
            params={
                "id": f"eq.{collection_id}",
                "user_id": f"eq.{user_id}",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"[database] 폴더 삭제 오류: {e}")
        return False


async def rename_collection(collection_id: str, user_id: str, name: str) -> bool:
    """폴더 이름 변경 (소유권 검증 포함). is_user_renamed=True 로 수동 변경 표시."""
    try:
        client = get_client()
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/collections",
            headers={**_headers(), "Prefer": "return=minimal"},
            params={
                "id": f"eq.{collection_id}",
                "user_id": f"eq.{user_id}",
            },
            json={"name": name, "is_user_renamed": True},
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"[database] 폴더 이름 변경 오류: {e}")
        return False


# ── 콘텐츠 부분 수정 ───────────────────────────────────────────────────────────

async def patch_content(content_id: str, user_id: str, updates: dict) -> bool:
    """폴더 재배정 등 부분 수정 (소유권 검증 포함).
    updates가 비어있으면 DB 호출 없이 즉시 True 반환.
    """
    if not updates:
        return True
    try:
        client = get_client()
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/contents",
            headers={**_headers(), "Prefer": "return=minimal"},
            params={
                "id": f"eq.{content_id}",
                "user_id": f"eq.{user_id}",
            },
            json=updates,
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"[database] 콘텐츠 수정 오류: {e}")
        return False
