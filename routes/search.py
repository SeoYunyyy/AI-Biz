# ── 자연어 검색 ──

import os
import re
import json
from flask import Blueprint, request, jsonify
from database.db import get_db, row_to_item
from services.analyzer import client

search_bp = Blueprint('search', __name__)

USER_ID = os.getenv('SUPABASE_USER_ID')


@search_bp.route('/api/search', methods=['POST'])
def search():
    query_text = request.json.get('query', '').strip()

    db    = get_db()
    query = db.table('contents').select('*').order('saved_at', desc=True)
    if USER_ID:
        query = query.eq('user_id', USER_ID)
    rows = query.execute().data

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

# 사용자의 자연어 요청을 OpenAI로 해석해 저장된 항목 중 관련 자료 반환
