# ── 사용자 그룹 생성 / 조회 / 수정 ──

import json
from flask import Blueprint, request, jsonify, session
from database.db import get_db, row_to_item

group_bp = Blueprint('group', __name__)


def _uid():
    return (session.get('user') or {}).get('id', '')


@group_bp.route('/api/groups', methods=['GET'])
def get_groups():
    user_id = _uid()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    db   = get_db()
    rows = (db.table('groups').select('*')
              .eq('user_id', user_id)
              .order('created_at', desc=True)
              .execute().data)
    for g in rows:
        if isinstance(g.get('item_ids'), str):
            g['item_ids'] = json.loads(g['item_ids'])
    return jsonify({'groups': rows})


@group_bp.route('/api/groups', methods=['POST'])
def create_group():
    user_id = _uid()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    data     = request.json
    name     = data.get('name', '').strip()
    item_ids = data.get('item_ids', [])
    if not name:
        return jsonify({'error': '그룹 이름이 필요합니다'}), 400

    db     = get_db()
    result = db.table('groups').insert({'name': name, 'item_ids': item_ids, 'user_id': user_id}).execute()
    group  = result.data[0] if result.data else {'name': name, 'item_ids': item_ids}
    return jsonify({'success': True, 'group': group})


@group_bp.route('/api/groups/<group_id>', methods=['PUT'])
def update_group(group_id):
    user_id = _uid()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    data     = request.json
    name     = data.get('name', '').strip()
    item_ids = data.get('item_ids', [])

    db = get_db()
    # 본인 그룹인지 확인 후 수정
    db.table('groups').update({'name': name, 'item_ids': item_ids}).eq('id', group_id).eq('user_id', user_id).execute()
    return jsonify({'success': True})


@group_bp.route('/api/groups/<group_id>/items', methods=['GET'])
def get_group_items(group_id):
    user_id = _uid()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    db  = get_db()
    res = db.table('groups').select('*').eq('id', group_id).eq('user_id', user_id).execute()
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

@group_bp.route('/api/groups/<group_id>', methods=['DELETE'])
def delete_group(group_id):
    user_id = _uid()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    db = get_db()
    db.table('groups').delete().eq('id', group_id).eq('user_id', user_id).execute()
    return jsonify({'success': True, 'deleted_id': group_id})

# 로그인한 유저의 그룹 목록 조회, 생성, 수정, 삭제, 그룹 내 아이템 조회 라우트
