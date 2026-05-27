# ── 아카이브 (URL 저장 / 카테고리 조회 / 아이템 조회) ──

import asyncio
import os
from flask import Blueprint, request, jsonify, session
from database.db import get_db, row_to_item
from services.category_mapper import map_topics_to_category

from backend.services.metadata.dispatcher import extract as dispatch
from backend.services.ai_classifier import classify, parse_user_input
from backend.services.embedding import run as embed, generate_embedding, build_embed_text
from backend.services.database import (
    save_content, update_content, mark_failed,
    check_duplicate, get_or_create_collection,
    find_similar_contents,
)

archive_bp = Blueprint('archive', __name__)


def _get_user_id():
    """세션 또는 .env에서 user_id 조회"""
    user = session.get('user', {})
    return user.get('id') or os.getenv('SUPABASE_USER_ID', '')


async def _ingest_pipeline(user_id: str, url: str, instruction: str, collection_id=None):
    """URL 저장 7단계 파이프라인 (비동기)"""

    # 1. 중복 체크
    existing = await check_duplicate(user_id, url)
    if existing:
        return {"duplicate": True, "item": {
            "id":          existing.get("id", ""),
            "url":         url,
            "title":       existing.get("title", ""),
            "category":    existing.get("category", "기타"),
            "subcategory": "",
            "summary":     "",
            "tags":        existing.get("hashtags", []),
            "thumbnail":   "",
        }}

    # 2. 즉시 저장 (processing 상태)
    saved = await save_content(user_id, url)
    if not saved:
        raise RuntimeError("초기 저장 실패")
    content_id = saved["id"]

    try:
        # 3. 메타데이터 추출 (URL 종류 자동 판별)
        metadata = await dispatch(url)

        # 4. AI 분류 (카테고리, 태그, 요약, 마감기한, 폴더명 추출)
        analysis = await classify(metadata, user_instruction=instruction)

        # 5. 폴더 처리 (사용자 지시 또는 AI 추천 폴더)
        if not collection_id and analysis.get("user_collection"):
            collection_id = await get_or_create_collection(
                user_id, analysis["user_collection"]
            )

        # 6. 임베딩 생성 + 저장 (벡터 검색용)
        await embed(content_id, metadata, analysis, "")

        # 6-1. 유사 콘텐츠 검색
        embed_text = build_embed_text(metadata, analysis, "")
        embedding  = await generate_embedding(embed_text)
        similar    = await find_similar_contents(user_id, embedding) if embedding else []

        # 7. DB 업데이트 (completed)
        await update_content(content_id, metadata, analysis, collection_id=collection_id)

        return {
            "success": True,
            "item": {
                "id":            content_id,
                "url":           url,
                "title":         metadata.get("title", ""),
                "thumbnail":     metadata.get("thumbnail", ""),
                "category":      analysis.get("category", "기타"),
                "subcategory":   analysis.get("sub_category", ""),
                "summary":       analysis.get("one_line_summary", ""),
                "tags":          analysis.get("tags", []),
                "has_deadline":  analysis.get("has_deadline", False),
                "deadline_date": analysis.get("deadline_date"),
                "deadline_note": analysis.get("deadline_note"),
            },
            "similar_contents": [
                {
                    "id":         s["id"],
                    "title":      s["title"],
                    "url":        s["url"],
                    "similarity": round(s.get("similarity", 0), 2),
                    "summary":    s.get("description", ""),
                }
                for s in similar
            ],
        }

    except Exception as e:
        await mark_failed(content_id)
        raise e


@archive_bp.route('/api/save', methods=['POST'])
def save():
    data          = request.json or {}
    raw_input     = data.get('raw_input', '').strip()  # "URL 지시사항" 통합 입력
    url           = data.get('url', '').strip()
    instruction   = data.get('instruction', '').strip()
    collection_id = data.get('collection_id') or None   # 프론트에서 선택한 폴더 ID

    # raw_input 으로 왔을 때 URL + 지시사항 분리
    if raw_input and not url:
        url, instruction = parse_user_input(raw_input)

    if not url:
        return jsonify({'error': 'URL을 입력해주세요'}), 400

    user_id = _get_user_id()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    try:
        result = asyncio.run(_ingest_pipeline(user_id, url, instruction, collection_id=collection_id))
    except Exception as e:
        return jsonify({'error': f'저장 중 오류: {str(e)}'}), 500

    return jsonify(result)


@archive_bp.route('/api/categories')
def categories():
    user_id = _get_user_id()
    db      = get_db()
    query   = db.table('contents').select('category, sub_category, metadata, topics')
    if user_id:
        query = query.eq('user_id', user_id)
    rows = query.execute().data

    cats = {}
    for row in rows:
        # 새 파이프라인 필드 우선, 없으면 기존 필드 폴백
        cat = row.get('category') \
              or (row.get('metadata') or {}).get('category') \
              or map_topics_to_category(row.get('topics') or [])
        sub = row.get('sub_category') or (row.get('topics') or ['기타'])[0]
        cats.setdefault(cat, {})
        cats[cat][sub] = cats[cat].get(sub, 0) + 1

    return jsonify({
        cat: [{'name': sub, 'count': cnt}
              for sub, cnt in sorted(subs.items(), key=lambda x: -x[1])]
        for cat, subs in cats.items()
    })


@archive_bp.route('/api/items')
def items():
    category    = request.args.get('category', '')
    subcategory = request.args.get('subcategory', '')
    user_id     = _get_user_id()

    db    = get_db()
    query = db.table('contents').select('*').order('saved_at', desc=True)
    if user_id:
        query = query.eq('user_id', user_id)
    rows = query.execute().data

    result = []
    for r in rows:
        item = row_to_item(r)
        # 새 파이프라인 필드 덮어쓰기
        if r.get('category'):
            item['category'] = r['category']
        if r.get('sub_category'):
            item['subcategory'] = r['sub_category']
        if item['category'] == category and item['subcategory'] == subcategory:
            result.append(item)

    return jsonify({'items': result})

# URL 저장(AI 7단계 파이프라인), 카테고리 목록 조회, 카테고리별 아이템 조회 라우트
