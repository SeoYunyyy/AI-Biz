# ── 자연어 검색 ──

import re
import json
from flask import Blueprint, request, jsonify
from database.db import get_db
from services.analyzer import client

search_bp = Blueprint('search', __name__)


@search_bp.route('/api/search', methods=['POST'])
def search():
    query = request.json.get('query', '').strip()

    conn = get_db()
    rows = conn.execute('SELECT * FROM items ORDER BY created_at DESC').fetchall()
    conn.close()

    if not rows:
        return jsonify({'results': []})

    items = [dict(r) for r in rows]
    summary_list = '\n'.join(
        f"ID:{r['id']} | {r['category']}/{r['subcategory']} | {r['title']} | {r['summary'] or ''}"
        for r in items
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": f"저장 목록:\n{summary_list}\n\n요청: \"{query}\"\n\n관련 항목 ID를 JSON 배열로만 응답. 없으면 []"
        }]
    )

    text = resp.choices[0].message.content.strip()
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    ids = json.loads(match.group() if match else '[]')

    results = [r for r in items if r['id'] in ids]
    for r in results:
        r['tags'] = json.loads(r['tags']) if r['tags'] else []

    return jsonify({'results': results})

# 사용자의 자연어 요청을 OpenAI로 해석해 저장된 항목 중 관련 자료 반환
