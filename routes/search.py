# ── 자연어 검색 ──

import re
import json
from flask import Blueprint, request, jsonify, session
from database.db import get_db, row_to_item
from services.analyzer import client

search_bp = Blueprint('search', __name__)


@search_bp.route('/api/search', methods=['POST'])
def search():
    user_id = (session.get('user') or {}).get('id', '')
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    query_text = request.json.get('query', '').strip()

    db   = get_db()
    rows = (db.table('contents').select('*')
              .eq('user_id', user_id)
              .order('saved_at', desc=True)
              .execute().data)

    if not rows:
        return jsonify({'results': []})

    items = [row_to_item(r) for r in rows]
    summary_list = '\n'.join(
        f"ID:{i['id']} | {i['category']}/{i['subcategory']} | {i['title']} | {i['summary'] or ''}"
        for i in items
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"저장 목록:\n{summary_list}\n\n요청: \"{query_text}\"\n\n관련 항목 ID를 JSON 배열로만 응답. 없으면 []"
        }]
    )

    text  = resp.choices[0].message.content.strip()
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    ids   = json.loads(match.group() if match else '[]')

    results = [i for i in items if i['id'] in ids]
    return jsonify({'results': results})

# 로그인한 유저의 저장 목록을 OpenAI로 검색해 관련 자료 반환
