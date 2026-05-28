# ── 자연어 검색 — 벡터 임베딩 기반 ──

import asyncio
import os
from flask import Blueprint, request, jsonify, session

from backend.services.embedding import generate_embedding
from backend.services.database import search_contents

search_bp = Blueprint('search', __name__)


def _get_user_id():
    user = session.get('user', {})
    return user.get('id') or os.getenv('SUPABASE_USER_ID', '')


@search_bp.route('/api/search', methods=['POST'])
def search():
    query_text = (request.json or {}).get('query', '').strip()
    if not query_text:
        return jsonify({'results': [], 'found': False}), 400

    user_id = _get_user_id()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    async def _run():
        embedding = await generate_embedding(query_text)
        if not embedding:
            return []
        return await search_contents(user_id, embedding, limit=5)

    try:
        rows = asyncio.run(_run())
    except Exception as e:
        return jsonify({'error': f'검색 중 오류: {str(e)}'}), 500

    results = [
        {
            "id":          r.get("id", ""),
            "url":         r.get("url", ""),
            "title":       r.get("title", ""),
            "category":    r.get("category", ""),
            "subcategory": r.get("sub_category", ""),
            "summary":     r.get("one_line_summary") or r.get("description", ""),
            "tags":        r.get("hashtags", []),
            "thumbnail":   r.get("thumbnail_url", ""),
            "similarity":  round(r.get("similarity", 0), 2),
        }
        for r in rows
    ]

    return jsonify({
        "results": results,
        "found":   len(results) > 0,
    })

# 자연어 검색어를 벡터 임베딩으로 변환 후 Supabase 벡터 유사도 검색 수행
