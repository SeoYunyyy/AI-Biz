# ── 리마인더 (마감기한 3일 이내 자료 알림) ──

import os
from flask import Blueprint, jsonify
from datetime import datetime, timedelta
from database.db import get_db, row_to_item

reminder_bp = Blueprint('reminder', __name__)

USER_ID = os.getenv('SUPABASE_USER_ID')


@reminder_bp.route('/api/reminders')
def reminders():
    today = datetime.now().date()
    limit = today + timedelta(days=3)

    db    = get_db()
    query = db.table('contents').select('id, title, metadata, url, saved_at')
    if USER_ID:
        query = query.eq('user_id', USER_ID)
    rows = query.execute().data

    # metadata->>'deadline' 이 today ~ limit 범위인 항목만 필터링
    result = []
    for row in rows:
        metadata = row.get('metadata') or {}
        deadline = metadata.get('deadline')
        if not deadline:
            continue
        try:
            dl = datetime.strptime(deadline[:10], '%Y-%m-%d').date()
            if today <= dl <= limit:
                result.append({
                    'id':       row['id'],
                    'title':    row.get('title', ''),
                    'deadline': deadline,
                    'url':      row.get('url', ''),
                })
        except ValueError:
            continue

    result.sort(key=lambda x: x['deadline'])
    return jsonify(result)

# 오늘부터 3일 이내 마감기한이 있는 저장 자료 목록 반환
