# ── 월간 취향 레포트 / 주간 레포트 ──

from flask import Blueprint, jsonify
from database.db import get_db
from services.analyzer import client
from datetime import datetime, timedelta

report_bp = Blueprint('report', __name__)

DAYS = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일']


@report_bp.route('/api/weekly-report')
def weekly_report():
    # 주간 통계 수집
    conn = get_db()

    # 이번 주 저장된 전체 링크 수
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM items WHERE created_at >= datetime('now', '-7 days')"
    ).fetchone()['cnt']

    if total == 0:
        conn.close()
        return jsonify({'empty': True, 'total': 0})

    # 가장 많이 저장한 세부 주제 (subcategory)
    top_sub = conn.execute(
        "SELECT subcategory, COUNT(*) as cnt FROM items "
        "WHERE created_at >= datetime('now', '-7 days') "
        "GROUP BY subcategory ORDER BY cnt DESC LIMIT 1"
    ).fetchone()

    # 가장 많이 저장한 대분류 카테고리
    top_cat = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM items "
        "WHERE created_at >= datetime('now', '-7 days') "
        "GROUP BY category ORDER BY cnt DESC LIMIT 1"
    ).fetchone()

    # 가장 많이 활동한 요일 (strftime %w: 0=일, 1=월 ... 6=토)
    top_day = conn.execute(
        "SELECT strftime('%w', created_at) as dow, COUNT(*) as cnt FROM items "
        "WHERE created_at >= datetime('now', '-7 days') "
        "GROUP BY dow ORDER BY cnt DESC LIMIT 1"
    ).fetchone()

    conn.close()

    top_topic     = top_sub['subcategory'] if top_sub else '-'
    top_topic_cnt = top_sub['cnt'] if top_sub else 0
    top_cat_name  = top_cat['category'] if top_cat else '-'
    top_cat_cnt   = top_cat['cnt'] if top_cat else 0
    top_day_name  = DAYS[int(top_day['dow'])] if top_day else '-'
    top_day_cnt   = top_day['cnt'] if top_day else 0

    # AI로 이번 주 키핏 닉네임 생성
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=60,
        messages=[{
            "role": "user",
            "content": (
                f"이번 주 사용자가 가장 많이 저장한 주제는 '{top_topic}'야. "
                "이 주제를 기반으로 '커피 한 잔의 여유를 아는 N' 처럼 "
                "'~하는 N' 형식의 창의적인 한국어 닉네임을 딱 하나만 만들어줘. "
                "N은 사람 이름이나 '유저'처럼 사람을 가리키는 말로 끝내. "
                "닉네임 텍스트만 출력해. 따옴표, 설명 없이."
            )
        }]
    )
    nickname = resp.choices[0].message.content.strip().strip('"').strip("'")

    return jsonify({
        'empty': False,
        'total': total,
        'top_topic': top_topic,
        'top_topic_cnt': top_topic_cnt,
        'top_category': top_cat_name,
        'top_category_cnt': top_cat_cnt,
        'top_day': top_day_name,
        'top_day_cnt': top_day_cnt,
        'nickname': nickname,
    })

# 이번 주(최근 7일) 저장 통계를 집계하고 AI로 키핏 닉네임 생성 후 반환


@report_bp.route('/api/weekly-stats')
def weekly_stats():
    conn = get_db()

    # Top 5 세부 주제 (막대 그래프 + 워드클라우드)
    top_topics = conn.execute(
        "SELECT subcategory, COUNT(*) as cnt FROM items "
        "WHERE created_at >= datetime('now', '-7 days') AND subcategory IS NOT NULL "
        "GROUP BY subcategory ORDER BY cnt DESC LIMIT 5"
    ).fetchall()

    # 워드클라우드용 전체 주제 (최대 30개)
    all_topics = conn.execute(
        "SELECT subcategory, COUNT(*) as cnt FROM items "
        "WHERE created_at >= datetime('now', '-7 days') AND subcategory IS NOT NULL "
        "GROUP BY subcategory ORDER BY cnt DESC LIMIT 30"
    ).fetchall()

    # 콘텐츠 타입별 분포
    content_types = conn.execute(
        "SELECT content_type, COUNT(*) as cnt FROM items "
        "WHERE created_at >= datetime('now', '-7 days') "
        "GROUP BY content_type ORDER BY cnt DESC"
    ).fetchall()

    # 이번 주 카테고리별 저장 현황 (새 파일 카드용)
    recent_categories = conn.execute(
        "SELECT category, COUNT(*) as cnt, MAX(created_at) as latest FROM items "
        "WHERE created_at >= datetime('now', '-7 days') "
        "GROUP BY category ORDER BY cnt DESC LIMIT 6"
    ).fetchall()

    # 일별 저장 횟수 (최근 7일, 빈 날도 0으로 채움)
    date_range = [
        (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        for i in range(6, -1, -1)
    ]
    daily_raw = conn.execute(
        "SELECT date(created_at) as day, COUNT(*) as cnt FROM items "
        "WHERE created_at >= datetime('now', '-7 days') GROUP BY day"
    ).fetchall()
    daily_map = {r['day']: r['cnt'] for r in daily_raw}

    WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']
    daily_counts = [
        {
            'day': d,
            'label': WEEKDAYS[datetime.strptime(d, '%Y-%m-%d').weekday()],
            'cnt': daily_map.get(d, 0)
        }
        for d in date_range
    ]

    conn.close()

    return jsonify({
        'top_topics':        [dict(r) for r in top_topics],
        'all_topics':        [dict(r) for r in all_topics],
        'content_types':     [dict(r) for r in content_types],
        'recent_categories': [dict(r) for r in recent_categories],
        'daily_counts':      daily_counts,
    })

# 이번 주 주제·콘텐츠 타입·일별 저장 통계를 집계해 차트 데이터로 반환


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
