import json
import asyncio
from flask import Blueprint, request, jsonify
from database.db import get_db
from services.fetcher import fetch_url_content
from services.analyzer import analyze_content
from services.metadata.dispatcher import extract as dispatch
from services.ai_classifier import classify
from services.embedding import run as embed
from services.thumbnail_vision import analyze_thumbnail
from services.supabase_db import (
    save_content, update_content, mark_failed,
    check_duplicate, get_or_create_collection,
)
import os
from supabase import create_client

archive_bp = Blueprint('archive', __name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"

def _sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── URL 저장 (구 방식 호환 — 내부적으로 새 파이프라인 사용) ──
async def _ingest_async(url, user_id, instruction, collection_id):
    existing = await check_duplicate(user_id, url)
    if existing:
        return {"success": True, "item": existing, "duplicate": True}

    saved = await save_content(user_id, url)
    if not saved:
        raise Exception("초기 저장 실패")
    content_id = saved["id"]

    try:
        metadata = await dispatch(url)
        thumbnail_description = await analyze_thumbnail(
            metadata.get("thumbnail", ""), metadata.get("title", "")
        )
        analysis = await classify(metadata, user_instruction=instruction)

        final_collection_id = collection_id
        if not final_collection_id and analysis.get("user_collection"):
            final_collection_id = await get_or_create_collection(
                user_id, analysis["user_collection"]
            )

        await embed(content_id, metadata, analysis, thumbnail_description)
        await update_content(content_id, metadata, analysis,
                             collection_id=final_collection_id,
                             thumbnail_description=thumbnail_description)

        tags = analysis.get("tags", [])
        return {
            "success": True,
            "item": {
                "id": content_id,
                "url": url,
                "title": metadata.get("title", ""),
                "category": analysis.get("category", ""),
                "subcategory": analysis.get("sub_category", ""),
                "summary": analysis.get("one_line_summary", ""),
                "content_type": metadata.get("platform", "other"),
                "tags": tags,
                "thumbnail": metadata.get("thumbnail", ""),
                "has_deadline": analysis.get("has_deadline", False),
                "deadline_date": analysis.get("deadline_date"),
                "deadline_note": analysis.get("deadline_note"),
            }
        }
    except Exception as e:
        await mark_failed(content_id)
        raise e


@archive_bp.route('/api/save', methods=['POST'])
def save():
    data = request.json or {}
    url = data.get('url', '').strip()
    user_id = data.get('user_id', DEFAULT_USER_ID)
    instruction = data.get('instruction', '')
    collection_id = data.get('collection_id')

    if not url:
        return jsonify({'error': 'URL을 입력해주세요'}), 400

    try:
        result = asyncio.run(_ingest_async(url, user_id, instruction, collection_id))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'분석 중 오류: {str(e)}'}), 500


# ── 카테고리 목록 (Supabase) ──
@archive_bp.route('/api/categories')
def categories():
    user_id = request.args.get('user_id', DEFAULT_USER_ID)
    try:
        rows = _sb().table("contents") \
            .select("category, sub_category") \
            .eq("user_id", user_id) \
            .eq("analysis_status", "completed") \
            .execute().data

        cats = {}
        for row in rows:
            cat = row.get("category") or "기타/알쓸신잡"
            sub = row.get("sub_category") or "기타"
            if cat not in cats:
                cats[cat] = {}
            cats[cat][sub] = cats[cat].get(sub, 0) + 1

        result = {
            cat: [{"name": sub, "count": cnt} for sub, cnt in subs.items()]
            for cat, subs in cats.items()
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({}), 200


# ── 카테고리별 아이템 (Supabase) ──
@archive_bp.route('/api/items')
def items():
    category = request.args.get('category', '')
    subcategory = request.args.get('subcategory', '')
    user_id = request.args.get('user_id', DEFAULT_USER_ID)

    try:
        q = _sb().table("contents") \
            .select("id, url, title, category, sub_category, description, content_type, topics, thumbnail_url, has_deadline, deadline_date, deadline_note") \
            .eq("user_id", user_id) \
            .eq("analysis_status", "completed")

        if category:
            q = q.eq("category", category)
        if subcategory:
            q = q.eq("sub_category", subcategory)

        rows = q.order("saved_at", desc=True).execute().data

        result = []
        for r in rows:
            result.append({
                "id": r.get("id"),
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "category": r.get("category", ""),
                "subcategory": r.get("sub_category", ""),
                "summary": r.get("description", ""),
                "content_type": r.get("content_type", "other"),
                "tags": r.get("topics") or [],
                "thumbnail": r.get("thumbnail_url", ""),
                "has_deadline": r.get("has_deadline", False),
                "deadline_date": r.get("deadline_date"),
                "deadline_note": r.get("deadline_note"),
            })

        return jsonify({"items": result})
    except Exception as e:
        return jsonify({"items": []}), 200
