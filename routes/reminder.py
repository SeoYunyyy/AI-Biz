# ── 리마인더 (마감기한 있는 자료 전체 알림) ──

import os
from flask import Blueprint, jsonify
from database.db import get_db

reminder_bp = Blueprint('reminder', __name__)

USER_ID = os.getenv('SUPABASE_USER_ID')


@reminder_bp.route('/api/reminders')
def reminders():
    db    = get_db()
    query = (
        db.table('contents')
        .select('id, title, url, deadline_date, deadline_note')
        .eq('has_deadline', True)
        .order('deadline_date', desc=False)
    )
    if USER_ID:
        query = query.eq('user_id', USER_ID)
    rows = query.execute().data

    result = [
        {
            'id':            r['id'],
            'title':         r.get('title', ''),
            'url':           r.get('url', ''),
            'deadline_date': r.get('deadline_date', ''),
            'deadline_note': r.get('deadline_note', ''),
        }
        for r in rows
    ]
    return jsonify(result)

# 마감기한 있는 모든 저장 자료를 날짜 오름차순으로 반환
