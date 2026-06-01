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
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents?id=eq.{content_id}",
                headers={**_headers(), "Prefer": "return=minimal"},
                json={
                    "content_type": metadata.get("platform", "other"),
                    "title": metadata.get("title", ""),
                    "description": metadata.get("summary") or analysis.get("detailed_summary", ""),
                    "thumbnail_url": metadata.get("thumbnail", ""),
                    "author": metadata.get("author", ""),
                    "metadata": {
                        "date": metadata.get("date", ""),
                        "original_url": metadata.get("original_url", ""),
                    },
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
                    "thumbnail_description": thumbnail_description or None,
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
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/match_user_contents",
                headers=_headers(),
                json={
                    "query_embedding": query_embedding,
                    "user_id_param": user_id,
                    "match_count": limit * 3,
                },
            )
            response.raise_for_status()
            results = response.json()

        filtered = [r for r in results if r.get("similarity", 0) >= threshold]
        filtered = filtered[:limit]

        # thumbnail_url이 없는 항목만 별도 조회로 보완
        ids_missing = [r["id"] for r in filtered if r.get("id") and not r.get("thumbnail_url")]
        if ids_missing:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{SUPABASE_URL}/rest/v1/contents",
                        headers=_headers(),
                        params={
                            "id": f"in.({','.join(ids_missing)})",
                            "select": "id,thumbnail_url",
                        },
                    )
                    if resp.status_code == 200:
                        thumb_map = {row["id"]: row.get("thumbnail_url", "") for row in resp.json()}
                        for r in filtered:
                            if r.get("id") in thumb_map:
                                r["thumbnail_url"] = thumb_map[r["id"]]
            except Exception as e:
                print(f"[database] 썸네일 보완 조회 오류: {e}")

        return filtered

    except httpx.HTTPError as e:
        print(f"[database] 검색 오류: {e}")
        return []


# ── 마감기한 ──────────────────────────────────────────────────────────────────

async def get_deadlines(user_id: str) -> list[dict]:
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


async def rename_collection(collection_id: str, user_id: str, name: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/collections",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={
                    "id": f"eq.{collection_id}",
                    "user_id": f"eq.{user_id}",
                },
                json={"name": name, "is_user_renamed": True},
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] 폴더 이름 변경 오류: {e}")
        return False


async def delete_collection(collection_id: str, user_id: str) -> bool:
    """폴더만 삭제하고 내부 콘텐츠는 미분류(collection_id=null)로 보존"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 먼저 콘텐츠들의 collection_id를 null로 초기화
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={
                    "collection_id": f"eq.{collection_id}",
                    "user_id": f"eq.{user_id}",
                },
                json={"collection_id": None},
            )
            # 폴더 삭제
            response = await client.delete(
                f"{SUPABASE_URL}/rest/v1/collections",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={
                    "id": f"eq.{collection_id}",
                    "user_id": f"eq.{user_id}",
                },
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] 폴더 삭제 오류: {e}")
        return False


async def delete_contents_by_subcategory(user_id: str, category: str, subcategory: str) -> bool:
    """해당 대분류/중분류에 속한 콘텐츠 전체 영구 삭제"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 임베딩 삭제를 위해 먼저 id 목록 조회
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "category": f"eq.{category}",
                    "sub_category": f"eq.{subcategory}",
                    "select": "id",
                },
            )
            resp.raise_for_status()
            ids = [r["id"] for r in resp.json()]

            if not ids:
                return True

            # embeddings 삭제
            for cid in ids:
                await client.delete(
                    f"{SUPABASE_URL}/rest/v1/embeddings",
                    headers={**_headers(), "Prefer": "return=minimal"},
                    params={"content_id": f"eq.{cid}"},
                )

            # contents 삭제
            response = await client.delete(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={
                    "user_id": f"eq.{user_id}",
                    "category": f"eq.{category}",
                    "sub_category": f"eq.{subcategory}",
                },
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"[database] 중분류 삭제 오류: {e}")
        return False


async def find_similar_contents(user_id: str, embedding: list[float], threshold: float = 0.5, limit: int = 3) -> list[dict]:
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
        print(f"[database] 유사 콘텐츠 검색 오류: {e}")
        return []


# ── 삭제 / 이동 ────────────────────────────────────────────────────────────────

async def delete_content(content_id: str, user_id: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # embeddings 먼저 삭제
            await client.delete(
                f"{SUPABASE_URL}/rest/v1/embeddings",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={"content_id": f"eq.{content_id}"},
            )
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


async def update_deadline(content_id: str, user_id: str, has_deadline: bool, deadline_date: str | None, deadline_note: str | None) -> bool:
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
