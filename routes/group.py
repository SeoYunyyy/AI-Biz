# ── 사용자 그룹 생성 / 조회 / 수정 ──

import json
from flask import Blueprint, request, jsonify
from database.db import get_db

group_bp = Blueprint('group', __name__)


@group_bp.route('/api/groups', methods=['GET'])
def get_groups():
    conn = get_db()
    rows = conn.execute('SELECT * FROM groups ORDER BY created_at DESC').fetchall()
    conn.close()
    result = []
    for r in rows:
        g = dict(r)
        g['item_ids'] = json.loads(g['item_ids']) if g['item_ids'] else []
        result.append(g)
    return jsonify({'groups': result})


@group_bp.route('/api/groups', methods=['POST'])
def create_group():
    data = request.json
    name = data.get('name', '').strip()
    item_ids = data.get('item_ids', [])
    if not name:
        return jsonify({'error': '그룹 이름이 필요합니다'}), 400
    conn = get_db()
    cur = conn.execute(
        'INSERT INTO groups (name, item_ids) VALUES (?,?)',
        (name, json.dumps(item_ids, ensure_ascii=False))
    )
    group_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'group': {'id': group_id, 'name': name, 'item_ids': item_ids}})


@group_bp.route('/api/groups/<int:group_id>', methods=['PUT'])
def update_group(group_id):
    data = request.json
    name = data.get('name', '').strip()
    item_ids = data.get('item_ids', [])
    conn = get_db()
    conn.execute(
        'UPDATE groups SET name=?, item_ids=? WHERE id=?',
        (name, json.dumps(item_ids, ensure_ascii=False), group_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@group_bp.route('/api/groups/<int:group_id>/items', methods=['GET'])
def get_group_items(group_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '그룹을 찾을 수 없습니다'}), 404
    item_ids = json.loads(row['item_ids']) if row['item_ids'] else []
    items = []
    if item_ids:
        placeholders = ','.join('?' * len(item_ids))
        rows = conn.execute(f'SELECT * FROM items WHERE id IN ({placeholders})', item_ids).fetchall()
        items = [dict(r) for r in rows]
        for item in items:
            item['tags'] = json.loads(item['tags']) if item['tags'] else []
    conn.close()
    return jsonify({'group': dict(row), 'items': items})

# 그룹 목록 조회, 생성, 수정, 그룹 내 아이템 조회 라우트
