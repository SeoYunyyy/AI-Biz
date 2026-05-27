# -*- coding: utf-8 -*-
"""
hyoju_connection.py
seoyun Flask 프론트 ↔ hyoju Supabase 연결 브릿지
"""

from flask import Blueprint, jsonify, request
from supabase import create_client
from openai import OpenAI
from datetime import datetime, timedelta
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv
import os, json

load_dotenv(Path(__file__).parent / '.env', override=True)

hyoju_bp = Blueprint('hyoju_connection', __name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://irrsxjjraqihjxnhsaxb.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
supabase     = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

WEEKDAYS     = ['월', '화', '수', '목', '금', '토', '일']
TIME_SLOTS   = [
    ('새벽', 0, 6),  ('오전', 6, 12),
    ('오후', 12, 18), ('저녁', 18, 22), ('심야', 22, 24),
]
CT_EMOJI = {'youtube':'▶️','blog':'📝','naver_blog':'📝','news':'📰','naver_news':'📰','instagram':'📸','other':'🔗'}
CT_LABEL = {'youtube':'YouTube','blog':'블로그','naver_blog':'블로그','news':'뉴스','naver_news':'뉴스','instagram':'Instagram','other':'기타'}


# ── 공통 ───────────────────────────────────────────────────────
def _fetch(user_id, since):
    q = (supabase.table("contents")
         .select("topics, moods, hashtags, content_type, saved_at, title, collection_id")
         .eq("analysis_status", "completed")
         .gte("saved_at", since))
    if user_id:
        q = q.eq("user_id", user_id)
    return q.execute().data


def _analyze(contents):
    topic_c = Counter()
    type_c  = Counter()
    slot_c  = Counter()
    day_c   = Counter()
    dates   = []

    for c in contents:
        for t in (c.get("topics") or []):
            topic_c[t] += 1
        type_c[c.get("content_type") or "other"] += 1
        s = c.get("saved_at")
        if s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            for label, h0, h1 in TIME_SLOTS:
                if h0 <= dt.hour < h1:
                    slot_c[label] += 1
                    break
            day_c[dt.strftime("%Y-%m-%d")] += 1
            dates.append(dt.date())

    avg_min = {'youtube':12,'blog':5,'naver_blog':5,'news':3,'naver_news':3,'instagram':2,'other':5}
    total_min = sum(avg_min.get(k,5)*v for k,v in type_c.items())
    h, m = divmod(total_min, 60)

    return dict(
        topic_c=topic_c, type_c=type_c, slot_c=slot_c, day_c=day_c, dates=dates,
        estimated_display=f"{h}시간 {m}분" if h else f"{m}분",
        estimated_minutes=total_min,
    )


def _streak(dates):
    if not dates:
        return 0
    from datetime import date as ddate
    s = sorted(set(dates))
    cur = 0
    check = ddate.today()
    while check in set(s):
        cur += 1; check -= timedelta(days=1)
    if cur == 0:
        check = ddate.today() - timedelta(days=1)
        while check in set(s):
            cur += 1; check -= timedelta(days=1)
    return cur


def _ai(top_topics, top_type, peak_slot, total, period="주"):
    """OpenAI 호출 — 실패 시 None 반환"""
    try:
        prompt = f"""
이번 {period} 저장 데이터: 총 {total}개
주요 주제: {', '.join(top_topics[:5])}
가장 많이 저장한 시간대: {peak_slot}
가장 많은 콘텐츠 유형: {top_type}

JSON으로 답해줘:
{{"personality_type":"취향 유형 이름(예: 밤의 미식가)","personality_emoji":"이모지 1~2개","personality_desc":"1~2문장 따뜻한 설명","ai_summary":"2~3문장 따뜻한 총평"}}
"""
        r = openai_client.chat.completions.create(
            model="gpt-4o-mini", max_tokens=250,
            messages=[{"role":"user","content":prompt}],
            response_format={"type":"json_object"},
        )
        return json.loads(r.choices[0].message.content)
    except Exception:
        return None


# ── seoyun 호환 엔드포인트 ─────────────────────────────────────
@hyoju_bp.route('/api/weekly-report')
def weekly_report():
    user_id = request.args.get("user_id")
    since   = (datetime.utcnow() - timedelta(days=7)).isoformat()
    contents = _fetch(user_id, since)
    total   = len(contents)

    if total == 0:
        return jsonify({'empty': True, 'total': 0})

    a = _analyze(contents)

    top_topic, top_topic_cnt = a['topic_c'].most_common(1)[0] if a['topic_c'] else ('-', 0)
    top_cat, top_cat_cnt     = a['type_c'].most_common(1)[0]  if a['type_c']  else ('-', 0)
    peak_slot                = a['slot_c'].most_common(1)[0][0] if a['slot_c'] else '저녁'
    streak                   = _streak(a['dates'])
    coll_count               = len(set(c.get('collection_id') for c in contents if c.get('collection_id')))

    # 전주 비교
    prev_since = (datetime.utcnow() - timedelta(days=14)).isoformat()
    prev_end   = (datetime.utcnow() - timedelta(days=7)).isoformat()
    prev_q = (supabase.table("contents")
              .select("topics, content_type, saved_at")
              .eq("analysis_status", "completed")
              .gte("saved_at", prev_since).lte("saved_at", prev_end))
    if user_id: prev_q = prev_q.eq("user_id", user_id)
    prev_c = prev_q.execute().data
    prev_topic_c = Counter()
    for c in prev_c:
        for t in (c.get("topics") or []): prev_topic_c[t] += 1

    comparison = []
    for topic, cnt in a['topic_c'].most_common(5):
        prev = prev_topic_c.get(topic, 0)
        if prev == 0:
            comparison.append({'topic': topic, 'change': 'new', 'pct': None})
        else:
            pct = round((cnt - prev) / prev * 100)
            comparison.append({'topic': topic, 'change': 'up' if pct > 0 else 'down', 'pct': pct})

    new_discovery = None
    new_topics = [(t, c) for t, c in a['topic_c'].most_common() if prev_topic_c.get(t, 0) == 0]
    if new_topics: new_discovery = {'topic': new_topics[0][0], 'count': new_topics[0][1]}

    # 시간대 분포
    time_dist = []
    slot_colors = {'새벽':'#e8d5c4','오전':'#c8a890','오후':'#a0724e','저녁':'#6b3a2a','심야':'#8b5e3c'}
    for label, h0, h1 in TIME_SLOTS:
        time_dist.append({
            'label': label, 'sub': f'{h0}-{h1}시',
            'count': a['slot_c'].get(label, 0),
            'color': slot_colors[label], 'peak': label == peak_slot,
        })

    ai = _ai([t for t, _ in a['topic_c'].most_common(5)], top_cat, peak_slot, total)

    return jsonify({
        'empty': False, 'total': total,
        'collection_count': coll_count,
        'streak': streak,
        'estimated_time': a['estimated_display'],
        'top_topic': top_topic, 'top_topic_cnt': top_topic_cnt,
        'top_category': top_cat, 'top_category_cnt': top_cat_cnt,
        'top_day': WEEKDAYS[(datetime.utcnow() - timedelta(days=1)).weekday()],
        'top_day_cnt': 0,
        'nickname': (ai or {}).get('personality_type', top_topic + ' 탐험가'),
        'personality_type':  (ai or {}).get('personality_type'),
        'personality_emoji': (ai or {}).get('personality_emoji', '✨'),
        'personality_desc':  (ai or {}).get('personality_desc'),
        'ai_summary':        (ai or {}).get('ai_summary'),
        'comparison':   comparison,
        'new_discovery': new_discovery,
        'time_distribution': time_dist,
        'peak_slot': peak_slot,
    })


@hyoju_bp.route('/api/weekly-stats')
def weekly_stats():
    user_id  = request.args.get("user_id")
    since    = (datetime.utcnow() - timedelta(days=7)).isoformat()
    contents = _fetch(user_id, since)

    if not contents:
        return jsonify({'top_topics':[],'all_topics':[],'content_types':[],'recent_categories':[],'daily_counts':[]})

    a = _analyze(contents)

    date_range = [(datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6,-1,-1)]
    daily_counts = [{'day':d,'label':WEEKDAYS[datetime.strptime(d,'%Y-%m-%d').weekday()],'cnt':a['day_c'].get(d,0)} for d in date_range]

    content_types = [{'content_type':k,'cnt':v,'emoji':CT_EMOJI.get(k,'🔗'),'label':CT_LABEL.get(k,k)} for k,v in a['type_c'].most_common()]

    return jsonify({
        'top_topics':  [{'subcategory':t,'cnt':v} for t,v in a['topic_c'].most_common(5)],
        'all_topics':  [{'subcategory':t,'cnt':v} for t,v in a['topic_c'].most_common(30)],
        'content_types': content_types,
        'recent_categories': [{'category':k,'cnt':v,'latest':None} for k,v in a['type_c'].most_common(6)],
        'daily_counts': daily_counts,
    })
