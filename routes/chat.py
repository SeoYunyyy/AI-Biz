# ── LLM 대화 및 그룹 생성 명령 처리 ──

import json
import re
from flask import Blueprint, request, jsonify
from database.db import get_db
from services.analyzer import client

chat_bp = Blueprint('chat', __name__)


def _all_items():
    conn = get_db()
    rows = conn.execute(
        'SELECT id, url, title, category, subcategory, summary, thumbnail FROM items ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'error': '메시지를 입력해주세요'}), 400

    items = _all_items()
    items_summary = '\n'.join(
        f"ID:{i['id']} | {i['category']}/{i['subcategory']} | {i['title']}"
        for i in items
    )

    resp = client.chat.completions.create(
        model='gpt-4o-mini',
        max_tokens=600,
        messages=[
            {
                'role': 'system',
                'content': f"""당신은 Keepit의 AI 어시스턴트입니다. 사용자의 아카이브 콘텐츠를 관리하고 그룹을 만들어드립니다.

저장된 콘텐츠:
{items_summary or '(저장된 콘텐츠 없음)'}

규칙:
- 그룹 생성 요청 → JSON만 응답: {{"type":"create_group","group_name":"그룹명","item_ids":[id,...],"message":"안내 문장"}}
- 콘텐츠 검색 요청 → JSON만 응답: {{"type":"search_result","item_ids":[id,...],"message":"안내 문장"}}
- 일반 대화 → 텍스트로 친근하게 답변"""
            },
            {'role': 'user', 'content': message}
        ]
    )

    text = resp.choices[0].message.content.strip()

    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            cmd = json.loads(match.group())
            cmd_type = cmd.get('type')

            if cmd_type == 'create_group':
                item_ids = cmd.get('item_ids', [])
                group_name = cmd.get('group_name', '새 그룹')
                conn = get_db()
                cur = conn.execute(
                    'INSERT INTO groups (name, item_ids) VALUES (?,?)',
                    (group_name, json.dumps(item_ids, ensure_ascii=False))
                )
                group_id = cur.lastrowid
                conn.commit()
                conn.close()
                matched = [i for i in items if i['id'] in item_ids]
                return jsonify({
                    'type': 'create_group',
                    'message': cmd.get('message', f'{group_name} 그룹을 만들었어요!'),
                    'group': {'id': group_id, 'name': group_name, 'item_ids': item_ids},
                    'items': matched
                })

            if cmd_type == 'search_result':
                item_ids = cmd.get('item_ids', [])
                matched = [i for i in items if i['id'] in item_ids]
                return jsonify({
                    'type': 'search_result',
                    'message': cmd.get('message', '관련 콘텐츠를 찾았어요.'),
                    'items': matched
                })
    except Exception:
        pass

    return jsonify({'type': 'text', 'message': text})

# OpenAI로 대화를 처리하고, 그룹 생성/검색 명령은 자동으로 실행 후 결과 반환
