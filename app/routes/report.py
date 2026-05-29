# ── 리포트 라우트 (주간/월간 통계) ──

import os
import json
import httpx
from datetime import datetime, timedelta, timezone
from collections import Counter
from fastapi import APIRouter, Query

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"

WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']
TIME_SLOTS = [
    ('새벽', 0, 6), ('오전', 6, 12),
    ('오후', 12, 18), ('저녁', 18, 22), ('심야', 22, 24),
]
CT_EMOJI = {
    'youtube': '▶️', 'blog': '📝', 'naver_blog': '📝',
    'news': '📰', 'naver_news': '📰', 'instagram': '📸',
    'web': '🔗', 'other': '🔗',
}
CT_LABEL = {
    'youtube': 'YouTube', 'blog': '블로그', 'naver_blog': '블로그',
    'news': '뉴스', 'naver_news': '뉴스', 'instagram': 'Instagram',
    'web': '웹', 'other': '기타',
}
AVG_MIN = {'youtube': 12, 'blog': 5, 'naver_blog': 5, 'news': 3, 'naver_news': 3, 'instagram': 2, 'web': 5, 'other': 5}


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def _fetch(user_id: str | None, since: str, until: str | None = None) -> list[dict]:
    params = {
        "analysis_status": "eq.completed",
        "select": "topics, content_type, saved_at, title, collection_id",
        "saved_at": f"gte.{since}",
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=_headers(),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        if until:
            data = [c for c in data if c.get("saved_at", "") <= until]
        return data

    except httpx.HTTPError:
        return []


def _analyze(contents: list[dict]) -> dict:
    topic_c: Counter = Counter()
    type_c: Counter = Counter()
    slot_c: Counter = Counter()
    day_c: Counter = Counter()
    dates = []

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

    total_min = sum(AVG_MIN.get(k, 5) * v for k, v in type_c.items())
    h, m = divmod(total_min, 60)

    return dict(
        topic_c=topic_c, type_c=type_c, slot_c=slot_c, day_c=day_c, dates=dates,
        estimated_display=f"{h}시간 {m}분" if h else f"{m}분",
        estimated_minutes=total_min,
    )


def _streak(dates: list) -> int:
    if not dates:
        return 0
    from datetime import date as ddate
    s = sorted(set(dates))
    cur = 0
    check = ddate.today()
    while check in set(s):
        cur += 1
        check -= timedelta(days=1)
    if cur == 0:
        check = ddate.today() - timedelta(days=1)
        while check in set(s):
            cur += 1
            check -= timedelta(days=1)
    return cur


async def _ai_analyze(top_topics: list, top_type: str, peak_slot: str, total: int, period: str = "주") -> dict | None:
    try:
        prompt = f"""
이번 {period} 저장 데이터: 총 {total}개
주요 주제: {', '.join(top_topics[:5])}
가장 많이 저장한 시간대: {peak_slot}
가장 많은 콘텐츠 유형: {top_type}

JSON으로 답해줘:
{{"personality_type":"취향 유형 이름(예: 밤의 미식가)","personality_emoji":"이모지 1~2개","personality_desc":"1~2문장 따뜻한 설명","ai_summary":"2~3문장 따뜻한 총평"}}
"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "max_tokens": 250,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            return json.loads(response.json()["choices"][0]["message"]["content"])
    except Exception:
        return None


@router.get("/api/weekly-report")
async def weekly_report(user_id: str = Query("")):
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()
    contents = await _fetch(user_id or None, since)
    total = len(contents)

    if total == 0:
        return {"empty": True, "total": 0}

    a = _analyze(contents)

    top_topic, top_topic_cnt = a['topic_c'].most_common(1)[0] if a['topic_c'] else ('-', 0)
    top_cat, top_cat_cnt = a['type_c'].most_common(1)[0] if a['type_c'] else ('-', 0)
    peak_slot = a['slot_c'].most_common(1)[0][0] if a['slot_c'] else '저녁'
    streak = _streak(a['dates'])
    coll_count = len(set(c.get('collection_id') for c in contents if c.get('collection_id')))

    # 전주 비교
    prev_since = (datetime.utcnow() - timedelta(days=14)).isoformat()
    prev_until = since
    prev_c = await _fetch(user_id or None, prev_since, prev_until)
    prev_topic_c: Counter = Counter()
    for c in prev_c:
        for t in (c.get("topics") or []):
            prev_topic_c[t] += 1

    comparison = []
    for topic, cnt in a['topic_c'].most_common(5):
        prev = prev_topic_c.get(topic, 0)
        if prev == 0:
            comparison.append({'topic': topic, 'change': 'new', 'pct': None})
        else:
            pct = round((cnt - prev) / prev * 100)
            comparison.append({'topic': topic, 'change': 'up' if pct > 0 else 'down', 'pct': pct})

    new_topics = [(t, c) for t, c in a['topic_c'].most_common() if prev_topic_c.get(t, 0) == 0]
    new_discovery = {'topic': new_topics[0][0], 'count': new_topics[0][1]} if new_topics else None

    slot_colors = {'새벽': '#e8d5c4', '오전': '#c8a890', '오후': '#a0724e', '저녁': '#6b3a2a', '심야': '#8b5e3c'}
    time_dist = [
        {
            'label': label, 'sub': f'{h0}-{h1}시',
            'count': a['slot_c'].get(label, 0),
            'color': slot_colors[label],
            'peak': label == peak_slot,
        }
        for label, h0, h1 in TIME_SLOTS
    ]

    ai = await _ai_analyze([t for t, _ in a['topic_c'].most_common(5)], top_cat, peak_slot, total)

    return {
        'empty': False, 'total': total,
        'collection_count': coll_count,
        'streak': streak,
        'estimated_time': a['estimated_display'],
        'top_topic': top_topic, 'top_topic_cnt': top_topic_cnt,
        'top_category': top_cat, 'top_category_cnt': top_cat_cnt,
        'nickname': (ai or {}).get('personality_type', top_topic + ' 탐험가'),
        'personality_type': (ai or {}).get('personality_type'),
        'personality_emoji': (ai or {}).get('personality_emoji', '✨'),
        'personality_desc': (ai or {}).get('personality_desc'),
        'ai_summary': (ai or {}).get('ai_summary'),
        'comparison': comparison,
        'new_discovery': new_discovery,
        'time_distribution': time_dist,
        'peak_slot': peak_slot,
    }


@router.get("/api/weekly-stats")
async def weekly_stats(user_id: str = Query("")):
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()
    contents = await _fetch(user_id or None, since)

    if not contents:
        return {'top_topics': [], 'all_topics': [], 'content_types': [], 'recent_categories': [], 'daily_counts': []}

    a = _analyze(contents)

    date_range = [(datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    daily_counts = [
        {'day': d, 'label': WEEKDAYS[datetime.strptime(d, '%Y-%m-%d').weekday()], 'cnt': a['day_c'].get(d, 0)}
        for d in date_range
    ]

    content_types = [
        {'content_type': k, 'cnt': v, 'emoji': CT_EMOJI.get(k, '🔗'), 'label': CT_LABEL.get(k, k)}
        for k, v in a['type_c'].most_common()
    ]

    return {
        'top_topics': [{'subcategory': t, 'cnt': v} for t, v in a['topic_c'].most_common(5)],
        'all_topics': [{'subcategory': t, 'cnt': v} for t, v in a['topic_c'].most_common(30)],
        'content_types': content_types,
        'recent_categories': [{'category': k, 'cnt': v} for k, v in a['type_c'].most_common(6)],
        'daily_counts': daily_counts,
    }


@router.get("/api/monthly-report")
async def monthly_report(user_id: str = Query(DEFAULT_USER_ID)):
    now = datetime.utcnow()
    since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    contents = await _fetch(user_id, since)

    if not contents:
        return {'report': '이번 달 저장된 자료가 아직 없어요.', 'stats': []}

    a = _analyze(contents)

    # category별 집계 (type_c 기반)
    stats = [{'category': k, 'subcategory': '', 'count': v} for k, v in a['type_c'].most_common()]
    top_topics = [t for t, _ in a['topic_c'].most_common(5)]
    stats_str = '\n'.join(f"{s['category']}: {s['count']}개" for s in stats)

    report_text = '이번 달 저장 내역을 불러왔어요.'
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "max_tokens": 250,
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"이번 달 저장 패턴:\n{stats_str}\n"
                            f"주요 주제: {', '.join(top_topics)}\n\n"
                            "사용자의 취향과 관심사를 분석한 친근한 월간 레포트를 한국어로 3~4문장 작성."
                        ),
                    }],
                },
            )
            response.raise_for_status()
            report_text = response.json()["choices"][0]["message"]["content"]
    except Exception:
        pass

    return {'report': report_text, 'stats': stats}
