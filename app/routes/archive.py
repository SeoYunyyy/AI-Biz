# ── 아카이브 조회 라우트 (카테고리, 아이템) ──

import os
import httpx
from fastapi import APIRouter, Query

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


@router.get("/api/categories")
async def categories(user_id: str = Query(DEFAULT_USER_ID)):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "analysis_status": "eq.completed",
                    "select": "category,sub_category",
                },
            )
            response.raise_for_status()
            rows = response.json()

        cats: dict = {}
        for row in rows:
            cat = row.get("category") or "기타/알쓸신잡"
            sub = row.get("sub_category") or "기타"
            if cat not in cats:
                cats[cat] = {}
            cats[cat][sub] = cats[cat].get(sub, 0) + 1

        return {
            cat: [{"name": sub, "count": cnt} for sub, cnt in subs.items()]
            for cat, subs in cats.items()
        }

    except httpx.HTTPError:
        return {}


@router.get("/api/collections/{collection_id}/items")
async def collection_items(
    collection_id: str,
    user_id: str = Query(DEFAULT_USER_ID),
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params={
                    "user_id": f"eq.{user_id}",
                    "collection_id": f"eq.{collection_id}",
                    "analysis_status": "eq.completed",
                    "select": "id,url,title,category,sub_category,one_line_summary,content_type,topics,thumbnail_url,saved_at",
                    "order": "saved_at.desc",
                },
            )
            response.raise_for_status()
            rows = response.json()

        return {
            "items": [
                {
                    "id": r.get("id"),
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "category": r.get("category", ""),
                    "subcategory": r.get("sub_category", ""),
                    "summary": r.get("one_line_summary", ""),
                    "content_type": r.get("content_type", "other"),
                    "tags": r.get("topics") or [],
                    "thumbnail": r.get("thumbnail_url", ""),
                }
                for r in rows
            ]
        }

    except httpx.HTTPError:
        return {"items": []}


@router.get("/api/items")
async def items(
    category: str = Query(""),
    subcategory: str = Query(""),
    user_id: str = Query(DEFAULT_USER_ID),
):
    params = {
        "user_id": f"eq.{user_id}",
        "analysis_status": "eq.completed",
        "select": "id,url,title,category,sub_category,one_line_summary,content_type,topics,thumbnail_url,has_deadline,deadline_date,deadline_note,saved_at",
        "order": "saved_at.desc",
    }
    if category:
        params["category"] = f"eq.{category}"
    if subcategory:
        params["sub_category"] = f"eq.{subcategory}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params=params,
            )
            response.raise_for_status()
            rows = response.json()

        return {
            "items": [
                {
                    "id": r.get("id"),
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "category": r.get("category", ""),
                    "subcategory": r.get("sub_category", ""),
                    "summary": r.get("one_line_summary", ""),
                    "content_type": r.get("content_type", "other"),
                    "tags": r.get("topics") or [],
                    "thumbnail": r.get("thumbnail_url", ""),
                    "has_deadline": r.get("has_deadline", False),
                    "deadline_date": r.get("deadline_date"),
                    "deadline_note": r.get("deadline_note"),
                }
                for r in rows
            ]
        }

    except httpx.HTTPError:
        return {"items": []}
