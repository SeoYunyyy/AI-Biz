# ── 월간 취향 레포트 ──

from flask import Blueprint, jsonify
from database.db import get_db
from services.analyzer import client

report_bp = Blueprint('report', __name__)


@report_bp.route('/api/monthly-report')
def monthly_report():
    conn = get_db()
    stats = conn.execute(
        "SELECT category, subcategory, COUNT(*) as count FROM items "
        "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now') "
        "GROUP BY category, subcategory ORDER BY count DESC"
    ).fetchall()
    conn.close()

    stats_list = [dict(r) for r in stats]

    if not stats_list:
        return jsonify({'report': '이번 달 저장된 자료가 아직 없어요.', 'stats': []})

    stats_str = '\n'.join(
        f"{r['category']}/{r['subcategory']}: {r['count']}개" for r in stats_list
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=250,
        messages=[{
            "role": "user",
            "content": f"이번 달 저장 패턴:\n{stats_str}\n\n사용자의 취향과 관심사를 분석한 친근한 월간 레포트를 한국어로 3-4문장 작성."
        }]
    )

    return jsonify({'report': resp.choices[0].message.content, 'stats': stats_list})

# 이번 달 저장 패턴을 OpenAI로 분석해 취향 레포트 텍스트와 통계 반환
