# -*- coding: utf-8 -*-
"""
hyoju_connection.py
seoyun 프론트엔드(Flask) ↔ hyoju Supabase 연결 브릿지
/api/weekly-report, /api/weekly-stats 를 Supabase 데이터로 교체
"""

from flask import Blueprint, jsonify, request
from supabase import create_client
from openai import OpenAI
from datetime import datetime, timedelta
from collections import Counter
from dotenv import load_dotenv
import os

load_dotenv()

hyoju_bp = Blueprint('hyoju_connection', __name__)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
)
openai_client = OpenAI()

WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']


def _fetch_week_contents(user_id=None):
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()
    q = (
        supabase.table("contents")
        .select("topics, moods, hashtags, content_type, saved_at, title")
        .eq("analysis_status", "completed")
        .gte("saved_at", since)
    )
    if user_id:
        q = q.eq("user_id", user_id)
    return q.execute().data


@hyoju_bp.route('/api/weekly-report')
def weekly_report():
    user_id  = request.args.get("user_id")
    contents = _fetch_week_contents(user_id)
    total    = len(contents)

    if total == 0:
        return jsonify({'empty': True, 'total': 0})

    topic_counter = Counter()
    for c in contents:
        for t in (c.get("topics") or []):
            topic_counter[t] += 1
    top_topic, top_topic_cnt = topic_counter.most_common(1)[0] if topic_counter else ('-', 0)

    type_counter = Counter()
    for c in contents:
        type_counter[c.get("content_type", "other")] += 1
    top_cat, top_cat_cnt = type_counter.most_common(1)[0] if type_counter else ('-', 0)

    day_counter = Counter()
    for c in contents:
        saved_at = c.get("saved_at")
        if saved_at:
            dt = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
            day_counter[dt.weekday()] += 1
    top_day_idx, top_day_cnt = day_counter.most_common(1)[0] if day_counter else (0, 0)

    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=60,
        messages=[{
            "role": "user",
            "content": (
                f"이번 주 사용자가 가장 많이 저장한 주제는 '{top_topic}'야. "
                "이 주제를 기반으로 '커피 한 잔의 여유를 아는 N'처럼 "
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
        'top_category': top_cat,
        'top_category_cnt': top_cat_cnt,
        'top_day': WEEKDAYS[top_day_idx],
        'top_day_cnt': top_day_cnt,
        'nickname': nickname,
    })


@hyoju_bp.route('/api/weekly-stats')
def weekly_stats():
    user_id  = request.args.get("user_id")
    contents = _fetch_week_contents(user_id)

    if not contents:
        return jsonify({
            'top_topics': [], 'all_topics': [],
            'content_types': [], 'recent_categories': [], 'daily_counts': [],
        })

    topic_counter = Counter()
    for c in contents:
        for t in (c.get("topics") or []):
            topic_counter[t] += 1
    top_topics = [{"subcategory": t, "cnt": v} for t, v in topic_counter.most_common(5)]
    all_topics = [{"subcategory": t, "cnt": v} for t, v in topic_counter.most_common(30)]

    type_counter = Counter()
    for c in contents:
        type_counter[c.get("content_type", "other")] += 1
    content_types     = [{"content_type": k, "cnt": v} for k, v in type_counter.most_common()]
    recent_categories = [{"category": k, "cnt": v, "latest": None} for k, v in type_counter.most_common(6)]

    date_range = [
        (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
        for i in range(6, -1, -1)
    ]
    day_counter = Counter()
    for c in contents:
        saved_at = c.get("saved_at")
        if saved_at:
            dt = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
            day_counter[dt.strftime('%Y-%m-%d')] += 1

    daily_counts = [
        {
            'day':   d,
            'label': WEEKDAYS[datetime.strptime(d, '%Y-%m-%d').weekday()],
            'cnt':   day_counter.get(d, 0),
        }
        for d in date_range
    ]

    return jsonify({
        'top_topics':        top_topics,
        'all_topics':        all_topics,
        'content_types':     content_types,
        'recent_categories': recent_categories,
        'daily_counts':      daily_counts,
    })
