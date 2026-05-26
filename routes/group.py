# ── 사용자 그룹 생성 / 조회 / 수정 ──

import json
from flask import Blueprint, request, jsonify
from database.db import get_db, row_to_item

group_bp = Blueprint('group', __name__)


@group_bp.route('/api/groups', methods=['GET'])
def get_groups():
    db   = get_db()
    rows = db.table('groups').select('*').order('created_at', desc=True).execute().data
    for g in rows:
        if isinstance(g.get('item_ids'), str):
            g['item_ids'] = json.loads(g['item_ids'])
    return jsonify({'groups': rows})


@group_bp.route('/api/groups', methods=['POST'])
def create_group():
    data     = request.json
    name     = data.get('name', '').strip()
    item_ids = data.get('item_ids', [])
    if not name:
        return jsonify({'error': '그룹 이름이 필요합니다'}), 400

    db     = get_db()
    result = db.table('groups').insert({'name': name, 'item_ids': item_ids}).execute()
    group  = result.data[0] if result.data else {'name': name, 'item_ids': item_ids}
    return jsonify({'success': True, 'group': group})


@group_bp.route('/api/groups/<group_id>', methods=['PUT'])
def update_group(group_id):
    data     = request.json
    name     = data.get('name', '').strip()
    item_ids = data.get('item_ids', [])

    db = get_db()
    db.table('groups').update({'name': name, 'item_ids': item_ids}).eq('id', group_id).execute()
    return jsonify({'success': True})


@group_bp.route('/api/groups/<group_id>/items', methods=['GET'])
def get_group_items(group_id):
    db  = get_db()
    res = db.table('groups').select('*').eq('id', group_id).execute()
    if not res.data:
        return jsonify({'error': '그룹을 찾을 수 없습니다'}), 404

    group    = res.data[0]
    item_ids = group.get('item_ids') or []
    if isinstance(item_ids, str):
        item_ids = json.loads(item_ids)

    items = []
    for iid in item_ids:
        row_res = db.table('contents').select('*').eq('id', iid).execute()
        if row_res.data:
            items.append(row_to_item(row_res.data[0]))

    return jsonify({'group': group, 'items': items})

# 그룹 목록 조회, 생성, 수정, 그룹 내 아이템 조회 라우트
