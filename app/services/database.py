# app/services/database.py

import httpx
import os
from datetime import datetime, timezone

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
    """
    1단계: URL만 먼저 즉시 저장 (분석 전)
    analysis_status = 'processing' 으로 시작
    → 사용자를 기다리게 하지 않기 위해 분리
    """
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
        print(f"[database] 초기 저장 오류: {e}")
        return None


async def update_content(content_id: str, metadata: dict, analysis: dict, collection_id: str | None = None, thumbnail_description: str = "") -> bool:
    """
    2단계: 크롤링 + AI 분석 완료 후 나머지 필드 업데이트
    analysis_status = 'completed'
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents?id=eq.{content_id}",
                headers={**_headers(), "Prefer": "return=minimal"},
                json={
                    # 메타데이터 추출 결과
                    "content_type": metadata.get("platform", "other"),
                    "title": metadata.get("title", ""),
                    "description": metadata.get("summary") or analysis.get("detailed_summary", ""),
                    "thumbnail_url": metadata.get("thumbnail", ""),
                    "author": metadata.get("author", ""),
                    "metadata": {
                        "date": metadata.get("date", ""),
                        "original_url": metadata.get("original_url", ""),
                    },
                    # AI 분석 결과
                    "one_line_summary": analysis.get("one_line_summary", ""),
                    "detailed_summary": analysis.get("detailed_summary", ""),
                    "save_purpose": analysis.get("save_purpose", ""),
                    "topics": analysis.get("tags", []),
                    "hashtags": [f"#{t}" for t in analysis.get("tags", [])],
                    "intent": [analysis.get("save_purpose", "")],
                    "category": analysis.get("category", "기타/알쓸신잡"),
                    "sub_category": analysis.get("sub_category", ""),
                    "has_deadline": analysis.get("has_deadline", False),
                    "deadline_date": analysis.get("deadline_date"),
                    "deadline_note": analysis.get("deadline_note"),
                    # 썸네일 Vision 분석 결과
                    "thumbnail_description": thumbnail_description or None,
                    # 상태 업데이트
                    "analysis_status": "completed",
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "collection_id": collection_id if collection_id and collection_id != "null" else None,
                },
            )
            response.raise_for_status()
            return True

    except httpx.HTTPError as e:
        print(f"[database] 업데이트 오류: {e}")
        try:
            print(f"[database] Supabase 응답: {e.response.text}")
        except Exception:
            pass
        return False


async def mark_failed(content_id: str) -> None:
    """분석 실패 시 status만 failed로 업데이트"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents?id=eq.{content_id}",
                headers={**_headers(), "Prefer": "return=minimal"},
                json={"analysis_status": "failed"},
            )
    except httpx.HTTPError as e:
        print(f"[database] 실패 처리 오류: {e}")


# ── 중복 체크 ──────────────────────────────────────────────────────────────────

async def check_duplicate(user_id: str, url: str) -> dict | None:
    """
    같은 유저가 같은 URL 저장하려 할 때 중복 감지
    있으면 기존 데이터 반환, 없으면 None
    """
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
        print(f"[database] 중복 체크 오류: {e}")
        return None


# ── 검색 ──────────────────────────────────────────────────────────────────────

async def search_contents(user_id: str, query_embedding: list[float], limit: int = 3, threshold: float = 0.3) -> list[dict]:
    """
    벡터 유사도 검색 (schema.sql의 match_user_contents RPC 호출)
    threshold 이상인 결과만 반환, 상위 limit개 제한
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/match_user_contents",
                headers=_headers(),
                json={
                    "query_embedding": query_embedding,
                    "user_id_param": user_id,
                    "match_count": limit * 3,  # threshold 필터링 후 limit개 남도록 넉넉히 요청
                },
            )
            response.raise_for_status()
            results = response.json()

        filtered = [r for r in results if r.get("similarity", 0) >= threshold]
        return filtered[:limit]

    except httpx.HTTPError as e:
        print(f"[database] 검색 오류: {e}")
        return []

# 마감기한 조회 함수
async def get_deadlines(user_id: str) -> list[dict]:
    """마감기한 있는 콘텐츠를 마감일 오름차순으로 반환"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "has_deadline": "eq.true",
                    "select": "id,title,url,deadline_date,deadline_note,thumbnail_url",
                    "order": "deadline_date.asc",
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        print(f"[database] 마감기한 조회 오류: {e}")
        return []
    

# ── 컬렉션(폴더) ───────────────────────────────────────────────────────────────

async def get_or_create_collection(user_id: str, name: str) -> str | None:
    """폴더 이름으로 조회, 없으면 생성해서 collection_id 반환"""
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
                json={
                    "user_id": user_id,
                    "name": name,
                    "is_user_renamed": True,
                },
            )
            response.raise_for_status()
            created = response.json()
            return created[0]["id"] if created else None

    except httpx.HTTPError as e:
        print(f"[database] 컬렉션 오류: {e}")
        return None


async def get_collections(user_id: str) -> list[dict]:
    """사용자 폴더 목록 전체 조회"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/collections",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "select": "id,name,emoji,content_count,created_at",
                    "order": "created_at.asc",
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        print(f"[database] 폴더 목록 조회 오류: {e}")
        return []
    
async def get_collection_items(user_id: str, collection_id: str) -> list[dict]:
    """특정 폴더의 콘텐츠 목록 조회 (폴더 컨텍스트 검색용)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "collection_id": f"eq.{collection_id}",
                    "analysis_status": "eq.completed",
                    "select": "id,title,url,one_line_summary,thumbnail_url,collection_id",
                    "order": "saved_at.desc",
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        print(f"[database] 폴더 아이템 조회 오류: {e}")
        return []


async def find_similar_contents(user_id: str, embedding: list[float], threshold: float = 0.5, limit: int = 3) -> list[dict]:
    """
    새로 저장하려는 콘텐츠와 유사한 기존 콘텐츠 검색
    threshold: 유사도 기준 (0.85 이상이면 비슷한 내용으로 판단)
    """
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
            # threshold 이상인 것만 필터링
            return [r for r in results if r.get("similarity", 0) >= threshold]

    except httpx.HTTPError as e:
        print(f"[database] 유사 콘텐츠 검색 오류: {e}")
        return []


async def get_user_contents(user_id: str) -> list[dict]:
    """유저의 완료된 콘텐츠 전체 조회 (재분류용)"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "analysis_status": "eq.completed",
                    "select": "id,title,category,sub_category,one_line_summary",
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        print(f"[database] 전체 콘텐츠 조회 오류: {e}")
        return []


async def update_subcategory(content_id: str, sub_category: str) -> bool:
    """소분류 업데이트"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{content_id}"},
                json={"sub_category": sub_category},
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] 소분류 업데이트 오류: {e}")
        return False


# ── 삭제 ──────────────────────────────────────────────────────────────────────

async def delete_content(content_id: str, user_id: str) -> bool:
    """콘텐츠 삭제 (본인 소유 확인 후 삭제)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={
                    "id": f"eq.{content_id}",
                    "user_id": f"eq.{user_id}",
                },
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] 삭제 오류: {e}")
        return False


async def move_content_collection(content_id: str, user_id: str, collection_id: str | None) -> bool:
    """콘텐츠의 폴더(collection_id) 변경"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={
                    "id": f"eq.{content_id}",
                    "user_id": f"eq.{user_id}",
                },
                json={"collection_id": collection_id},
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] 폴더 이동 오류: {e}")
        return False


async def get_all_contents_for_reclassify(user_id: str) -> list[dict]:
    """재분류용 전체 콘텐츠 조회"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "analysis_status": "eq.completed",
                    "select": "id,title,content_type,description,url,metadata",
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        print(f"[database] 전체 조회 오류: {e}")
        return []


async def update_ai_fields(content_id: str, analysis: dict) -> bool:
    """AI 분류 결과 필드만 업데이트 (재분류용)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents?id=eq.{content_id}",
                headers={**_headers(), "Prefer": "return=minimal"},
                json={
                    "category": analysis.get("category", "기타/알쓸신잡"),
                    "sub_category": analysis.get("sub_category", ""),
                    "one_line_summary": analysis.get("one_line_summary", ""),
                    "detailed_summary": analysis.get("detailed_summary", ""),
                    "save_purpose": analysis.get("save_purpose", ""),
                    "topics": analysis.get("tags", []),
                    "hashtags": [f"#{t}" for t in analysis.get("tags", [])],
                    "has_deadline": analysis.get("has_deadline", False),
                    "deadline_date": analysis.get("deadline_date"),
                    "deadline_note": analysis.get("deadline_note"),
                },
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] AI 필드 업데이트 오류: {e}")
        return False


async def get_old_contents(user_id: str, days: int = 365) -> list[dict]:
    """저장한 지 days일 이상 지난 콘텐츠 반환"""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "saved_at": f"lt.{cutoff}",
                    "select": "id,title,url,saved_at,category",
                    "order": "saved_at.asc",
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        print(f"[database] 오래된 콘텐츠 조회 오류: {e}")
        return []


async def get_contents_by_ids(user_id: str, content_ids: list[str]) -> list[dict]:
    """ID 목록으로 콘텐츠 조회 (이동 확인용)"""
    if not content_ids:
        return []
    try:
        ids_str = ','.join(content_ids)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "id": f"in.({ids_str})",
                    "select": "id,title,url,one_line_summary,thumbnail_url",
                },
            )
            response.raise_for_status()
            return [{**d, "similarity": 1.0} for d in response.json()]
    except httpx.HTTPError as e:
        print(f"[database] ID 조회 오류: {e}")
        return []


async def delete_collection(collection_id: str, user_id: str) -> bool:
    """폴더 삭제 — 콘텐츠는 유지하고 collection_id만 해제 후 폴더 삭제"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. 해당 폴더에 속한 콘텐츠의 collection_id 해제
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={"user_id": f"eq.{user_id}", "collection_id": f"eq.{collection_id}"},
                json={"collection_id": None},
            )
            # 2. 폴더 삭제
            response = await client.delete(
                f"{SUPABASE_URL}/rest/v1/collections",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{collection_id}", "user_id": f"eq.{user_id}"},
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] 폴더 삭제 오류: {e}")
        return False


async def update_collection_emoji(collection_id: str, user_id: str, emoji: str | None) -> bool:
    """컬렉션 이모티콘 업데이트"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/collections",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{collection_id}", "user_id": f"eq.{user_id}"},
                json={"emoji": emoji},
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] 이모티콘 업데이트 오류: {e}")
        return False


async def update_deadline(content_id: str, user_id: str, has_deadline: bool, deadline_date: str | None, deadline_note: str | None) -> bool:
    """마감기한 수정 (채팅에서 사용자가 정정할 때)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={
                    "id": f"eq.{content_id}",
                    "user_id": f"eq.{user_id}",
                },
                json={
                    "has_deadline": has_deadline,
                    "deadline_date": deadline_date,
                    "deadline_note": deadline_note,
                },
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] 마감기한 수정 오류: {e}")
        return False