# ── 리마인더 (마감기한 3일 이내 자료 알림) ──

from flask import Blueprint, jsonify
from datetime import datetime, timedelta
from database.db import get_db

reminder_bp = Blueprint('reminder', __name__)


@reminder_bp.route('/api/reminders')
def reminders():
    today = datetime.now().date()
    limit = today + timedelta(days=3)

    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, category, deadline, url FROM items "
        "WHERE deadline IS NOT NULL AND date(deadline) BETWEEN date(?) AND date(?) ORDER BY deadline",
        (str(today), str(limit))
    ).fetchall()
    conn.close()

    return jsonify([dict(r) for r in rows])

# 오늘부터 3일 이내 마감기한이 있는 저장 자료 목록 반환
