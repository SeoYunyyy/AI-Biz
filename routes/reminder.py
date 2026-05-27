# ── 리마인더 (마감기한 3일 이내 자료 알림) ──

from flask import Blueprint, jsonify, session
from datetime import datetime, timedelta
from database.db import get_db

reminder_bp = Blueprint('reminder', __name__)


@reminder_bp.route('/api/reminders')
def reminders():
    user_id = (session.get('user') or {}).get('id', '')
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    today = datetime.now().date()
    limit = today + timedelta(days=3)

    db   = get_db()
    rows = (db.table('contents')
              .select('id, title, metadata, url, saved_at')
              .eq('user_id', user_id)
              .execute().data)

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

# 로그인한 유저의 오늘~3일 이내 마감기한 저장 자료 목록 반환
