# ── LLM 채팅 — 의도 자동 파악 (검색 / 마감기한 / 폴더 / 정리) ──

import asyncio
import os
from flask import Blueprint, request, jsonify, session
from database.db import get_db

from backend.services.chat import process_chat

chat_bp = Blueprint('chat', __name__)


def _get_user_id():
    user = session.get('user', {})
    return user.get('id') or os.getenv('SUPABASE_USER_ID', '')


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    data    = request.json or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': '메시지를 입력해주세요'}), 400

    user_id = _get_user_id()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    try:
        result = asyncio.run(process_chat(user_id, message))
    except Exception as e:
        return jsonify({'error': f'처리 중 오류: {str(e)}'}), 500

    # eundaeun 응답 → 프론트 형식 변환
    intent  = result.get('intent', 'general')
    answer  = result.get('answer', '')
    results = result.get('results', [])

    # 검색 결과 items 형식으로 변환
    items = [
        {
            "id":          r.get("id", ""),
            "url":         r.get("url", ""),
            "title":       r.get("title", ""),
            "category":    r.get("category", ""),
            "subcategory": r.get("sub_category", ""),
            "summary":     r.get("one_line_summary") or r.get("description", ""),
            "tags":        r.get("hashtags", []),
            "thumbnail":   r.get("thumbnail_url", ""),
        }
        for r in results
    ]

    # 의도 → 프론트 type 매핑
    type_map = {
        "search":   "search_result",
        "deadline": "deadline",
        "folder":   "folder",
        "cleanup":  "cleanup",
        "general":  "text",
    }

    response = {
        "type":    type_map.get(intent, "text"),
        "message": answer,
        "items":   items,
        "intent":  intent,
    }

    # 폴더 확인 요청 데이터
    if result.get('needs_confirmation'):
        response['needs_confirmation'] = True
        response['confirmation_data']  = result.get('confirmation_data', {})

    # 마감 만료 목록
    if result.get('expired'):
        response['expired'] = result['expired']

    # 후속 질문
    if result.get('follow_up_questions'):
        response['follow_up_questions'] = result['follow_up_questions']

    return jsonify(response)

# 채팅 메시지 의도(검색/마감/폴더/정리) 파악 후 적절한 응답 반환
