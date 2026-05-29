# ── 자연어 검색 (벡터 임베딩 기반) ──

from flask import Blueprint, request, jsonify, session
from database.db import search_contents, row_to_item
from services.embedding import generate_embedding
from services.query_expander import expand_query

search_bp = Blueprint('search', __name__)

SEARCH_FOLLOWUPS = [
    "혹시 유튜브 영상이었나요, 아니면 블로그/뉴스 글이었나요?",
    "어떤 주제였는지 조금 더 기억나시나요? (예: 요리, 여행, IT 등)",
    "언제쯤 저장하셨는지 기억나시나요?",
    "제목에 특정 단어가 포함됐었나요?",
]


@search_bp.route('/api/search', methods=['POST'])
def search():
    """
    자연어로 저장된 콘텐츠 검색.
    쿼리 확장 → 벡터 임베딩 → pgvector 유사도 검색.
    결과 없으면 유도 질문 제공.
    """
    user_id = (session.get('user') or {}).get('id', '')
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    data       = request.json or {}
    query_text = (data.get('query') or '').strip()
    limit      = int(data.get('limit', 5))

    if not query_text:
        return jsonify({'error': '검색어를 입력해주세요'}), 400

    expanded        = expand_query(query_text)
    query_embedding = generate_embedding(expanded)

    if not query_embedding:
        return jsonify({'error': '검색어 임베딩 실패'}), 500

    raw_results = search_contents(user_id, query_embedding, limit=limit)
    results     = [row_to_item(r) for r in raw_results]

    if not results:
        return jsonify({
            'results':             [],
            'found':               False,
            'message':             '저장된 콘텐츠 중 찾지 못했어요. 아래 힌트를 참고해서 다시 검색해보세요.',
            'follow_up_questions': SEARCH_FOLLOWUPS,
        })

    return jsonify({
        'results':             results,
        'found':               True,
        'message':             None,
        'follow_up_questions': [],
    })

# 검색 쿼리를 GPT로 확장 후 pgvector 유사도 검색, 결과 없으면 유도 질문 반환
