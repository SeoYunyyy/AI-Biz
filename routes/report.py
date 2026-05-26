# ── 주간/월간 레포트 — backend services/report.py 완전 포팅 ──

import os
import json
import calendar as cal_module
from collections import Counter
from datetime import datetime, timedelta, date, timezone

from flask import Blueprint, request, jsonify
from database.db import get_db
from services.analyzer import client
from services.category_mapper import map_topics_to_category

report_bp = Blueprint('report', __name__)

WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']
USER_ID  = os.getenv('SUPABASE_USER_ID')


# ── 유틸 (backend _get_week_range / _get_month_range 동일) ──

def _get_time_slot(hour: int) -> str:
    if 5 <= hour < 12:    return "오전"
    elif 12 <= hour < 17: return "오후"
    elif 17 <= hour < 21: return "저녁"
    else:                 return "심야"


def _get_week_range(year: int, month: int, week: int):
    """week: 1=1~7일, 2=8~14일, 3=15~21일, 4=22~28일, 5=29일~말일"""
    start_day = (week - 1) * 7 + 1
    end_day   = min(week * 7, cal_module.monthrange(year, month)[1])
    return (datetime(year, month, start_day, tzinfo=timezone.utc),
            datetime(year, month, end_day, 23, 59, 59, tzinfo=timezone.utc))


def _get_month_range(year: int, month: int):
    last_day = cal_module.monthrange(year, month)[1]
    return (datetime(year, month, 1, tzinfo=timezone.utc),
            datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc))


def _calc_streak(dates: list) -> dict:
    if not dates:
        return {"current_streak": 0, "max_streak": 0}
    unique = sorted(set(dates))
    max_s = cur = 1
    for i in range(1, len(unique)):
        if (unique[i] - unique[i - 1]).days == 1:
            cur += 1; max_s = max(max_s, cur)
        else:
            cur = 1
    date_set = set(unique)
    today = date.today()
    cur_s = 0
    check = today
    while check in date_set:
        cur_s += 1; check -= timedelta(days=1)
    if cur_s == 0:
        check = today - timedelta(days=1)
        while check in date_set:
            cur_s += 1; check -= timedelta(days=1)
    return {"current_streak": cur_s, "max_streak": max_s}


def _calc_estimated_time(content_types: list) -> dict:
    avg = {
        "youtube": 12, "blog": 5, "news": 3, "video": 12, "article": 5,
        "instagram": 2, "naver_blog": 5, "naver_news": 3, "music": 3,
        "place": 2, "recipe": 5, "other": 5,
    }
    total = sum(avg.get(ct["type"].lower(), 5) * ct["count"] for ct in content_types)
    h, m = divmod(total, 60)
    return {"total_minutes": total, "display": f"{h}시간 {m}분" if h > 0 else f"{m}분"}


# ── DB 조회 ──

def _fetch_contents(start: datetime, end: datetime) -> list:
    db    = get_db()
    query = (db.table('contents')
               .select('*')
               .eq('analysis_status', 'completed')
               .gte('saved_at', start.isoformat())
               .lte('saved_at', end.isoformat()))
    if USER_ID:
        query = query.eq('user_id', USER_ID)
    return query.execute().data


# ── 통계 계산 (backend _build_stats 동일 로직) ──

def _build_stats(rows: list) -> dict:
    word_ctr = Counter()
    type_ctr = Counter()
    time_ctr = Counter()
    hour_ctr = Counter()
    day_ctr  = Counter()
    mood_ctr = Counter()
    dates    = []

    for r in rows:
        for t in (r.get('topics') or []):
            if t: word_ctr[t] += 1
        for h in (r.get('hashtags') or []):
            if h: word_ctr[h.lstrip('#')] += 1
        for m in (r.get('moods') or []):
            if m: mood_ctr[m] += 1
        type_ctr[r.get('content_type') or 'other'] += 1
        saved = r.get('saved_at')
        if saved:
            try:
                dt = datetime.fromisoformat(saved.replace('Z', '+00:00'))
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                time_ctr[_get_time_slot(dt.hour)] += 1
                hour_ctr[dt.hour] += 1
                day_ctr[dt.strftime('%Y-%m-%d')] += 1
                dates.append(dt.date())
            except Exception:
                pass

    ct_list = [{"type": k, "count": v} for k, v in type_ctr.most_common()]
    return {
        "total":             len(rows),
        "word_cloud":        [{"text": w, "value": v} for w, v in word_ctr.most_common(30)],
        "top5_topics":       [{"topic": w, "count": v} for w, v in word_ctr.most_common(5)],
        "content_types":     ct_list,
        "time_distribution": [{"slot": k, "count": v} for k, v in time_ctr.most_common()],
        "peak_slot":         time_ctr.most_common(1)[0][0] if time_ctr else "알 수 없음",
        "peak_hour":         hour_ctr.most_common(1)[0][0] if hour_ctr else None,
        "top_moods":         [{"mood": k, "count": v} for k, v in mood_ctr.most_common(5)],
        "streak":            _calc_streak(dates),
        "estimated_time":    _calc_estimated_time(ct_list),
        "heatmap":           [{"date": k, "count": v} for k, v in sorted(day_ctr.items())],
        "word_counter":      word_ctr,   # 비교용 (응답 미포함)
    }


def _build_comparison(curr_wc: Counter, prev_wc: Counter, top_n: int = 5) -> list:
    result = []
    for topic, curr_count in curr_wc.most_common(10):
        prev_count = prev_wc.get(topic, 0)
        if prev_count == 0:
            result.append({"topic": topic, "curr_count": curr_count,
                           "prev_count": 0, "change": "new", "pct": None})
        else:
            pct = round((curr_count - prev_count) / prev_count * 100)
            result.append({"topic": topic, "curr_count": curr_count,
                           "prev_count": prev_count,
                           "change": "up" if pct > 0 else "down" if pct < 0 else "same",
                           "pct": pct})
    return result[:top_n]


def _find_new_discovery(curr_wc: Counter, prev_wc: Counter):
    new_topics = [(t, c) for t, c in curr_wc.most_common() if prev_wc.get(t, 0) == 0]
    return {"topic": new_topics[0][0], "count": new_topics[0][1]} if new_topics else None


def _gen_ai_result(year: int, month: int, stats: dict, period: str = "주") -> dict:
    top5      = stats["top5_topics"]
    top_moods = stats["top_moods"]
    ctypes    = stats["content_types"]
    prompt = f"""
사용자의 {year}년 {month}월 콘텐츠 저장 데이터입니다.
- 총 저장 수: {stats['total']}개
- 주요 관심 주제: {', '.join([t['topic'] for t in top5])}
- 주로 저장한 시간대: {stats['peak_slot']} ({stats['peak_hour']}시 전후)
- 주요 분위기: {', '.join([m['mood'] for m in top_moods]) or '없음'}
- 콘텐츠 유형: {', '.join([f"{t['type']} {t['count']}개" for t in ctypes])}

아래 JSON 형식으로 응답해주세요 (한국어):
{{
  "personality_type": "취향 유형 이름 (예: 밤의 미식가, 디지털 탐험가, 감성 수집가 등)",
  "personality_emoji": "유형을 표현하는 이모지 1~2개",
  "personality_desc": "유형 설명 1~2문장, 따뜻한 말투",
  "summary": "이 사람의 한 {period}을 2~3문장으로 요약, 따뜻하고 친근한 말투",
  "nickname": "이번 {period} 키핏 이름. '~하는 N' 형식 (N은 사람을 가리키는 말)"
}}"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=350,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ── 주간 레포트 API (backend /report/weekly/{user_id} 동일 구조) ──

@report_bp.route('/api/weekly-report')
def weekly_report():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))
    week  = int(request.args.get('week',  (today.day - 1) // 7 + 1))

    start, end = _get_week_range(year, month, week)
    rows       = _fetch_contents(start, end)

    if not rows:
        return jsonify({'empty': True, 'total': 0,
                        'period_start': start.strftime('%Y-%m-%d'),
                        'period_end':   end.strftime('%Y-%m-%d')})

    stats            = _build_stats(rows)
    collection_count = len({r.get('collection_id') for r in rows if r.get('collection_id')})

    # 이전 주 (비교용)
    if week > 1:
        prev_start, prev_end = _get_week_range(year, month, week - 1)
    else:
        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        last_week  = (cal_module.monthrange(prev_year, prev_month)[1] - 1) // 7 + 1
        prev_start, prev_end = _get_week_range(prev_year, prev_month, last_week)

    prev_rows     = _fetch_contents(prev_start, prev_end)
    comparison    = []
    new_discovery = None
    if prev_rows:
        prev_stats    = _build_stats(prev_rows)
        comparison    = _build_comparison(stats['word_counter'], prev_stats['word_counter'])
        new_discovery = _find_new_discovery(stats['word_counter'], prev_stats['word_counter'])

    # 카테고리별 파일 현황
    cat_ctr    = Counter()
    cat_latest = {}
    for r in rows:
        meta   = r.get('metadata') or {}
        topics = r.get('topics') or []
        cat    = meta.get('category') or map_topics_to_category(topics)
        cat_ctr[cat] += 1
        saved = r.get('saved_at', '')
        if saved > cat_latest.get(cat, ''):
            cat_latest[cat] = saved
    categories = [
        {'category': cat, 'cnt': cnt, 'latest': cat_latest.get(cat, '')}
        for cat, cnt in cat_ctr.most_common(6)
    ]

    # 기간 내 일별 저장 횟수
    day_map = {e['date']: e['count'] for e in stats['heatmap']}
    delta   = (end.date() - start.date()).days + 1
    daily_counts = [
        {
            'day':   (start.date() + timedelta(days=i)).strftime('%Y-%m-%d'),
            'label': WEEKDAYS[(start.date() + timedelta(days=i)).weekday()],
            'cnt':   day_map.get((start.date() + timedelta(days=i)).strftime('%Y-%m-%d'), 0),
        }
        for i in range(delta)
    ]

    ai = _gen_ai_result(year, month, stats, "주")

    return jsonify({
        'empty':            False,
        'year':             year,
        'month':            month,
        'week':             week,
        'period_start':     start.strftime('%Y-%m-%d'),
        'period_end':       end.strftime('%Y-%m-%d'),
        'total_count':      stats['total'],
        'collection_count': collection_count,
        'word_cloud':       stats['word_cloud'],
        'top5_topics':      stats['top5_topics'],
        'content_types':    stats['content_types'],
        'time_distribution':stats['time_distribution'],
        'peak_time_slot':   stats['peak_slot'],
        'peak_hour':        stats['peak_hour'],
        'top_moods':        stats['top_moods'],
        'streak':           stats['streak'],
        'estimated_time':   stats['estimated_time'],
        'heatmap':          stats['heatmap'],
        'comparison':       comparison,
        'new_discovery':    new_discovery,
        'categories':       categories,
        'daily_counts':     daily_counts,
        'personality_type': ai.get('personality_type', ''),
        'personality_emoji':ai.get('personality_emoji', ''),
        'personality_desc': ai.get('personality_desc', ''),
        'ai_summary':       ai.get('summary', ''),
        'nickname':         ai.get('nickname', ''),
    })

# backend generate_weekly_report 동일 로직 — Supabase에서 주간 데이터 집계 후 반환


# ── 월간 레포트 API (backend /report/monthly/{user_id} 동일 구조) ──

@report_bp.route('/api/monthly-report')
def monthly_report():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))

    start, end = _get_month_range(year, month)
    rows       = _fetch_contents(start, end)

    if not rows:
        return jsonify({'empty': True, 'message': '이번 달 저장된 콘텐츠가 없어요', 'total': 0})

    stats            = _build_stats(rows)
    collection_count = len({r.get('collection_id') for r in rows if r.get('collection_id')})

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    prev_start, prev_end = _get_month_range(prev_year, prev_month)
    prev_rows     = _fetch_contents(prev_start, prev_end)
    comparison    = []
    new_discovery = None
    if prev_rows:
        prev_stats    = _build_stats(prev_rows)
        comparison    = _build_comparison(stats['word_counter'], prev_stats['word_counter'])
        new_discovery = _find_new_discovery(stats['word_counter'], prev_stats['word_counter'])

    ai = _gen_ai_result(year, month, stats, "달")

    return jsonify({
        'empty':            False,
        'year':             year,
        'month':            month,
        'total_count':      stats['total'],
        'collection_count': collection_count,
        'word_cloud':       stats['word_cloud'],
        'top5_topics':      stats['top5_topics'],
        'content_types':    stats['content_types'],
        'time_distribution':stats['time_distribution'],
        'peak_time_slot':   stats['peak_slot'],
        'peak_hour':        stats['peak_hour'],
        'top_moods':        stats['top_moods'],
        'streak':           stats['streak'],
        'estimated_time':   stats['estimated_time'],
        'heatmap':          stats['heatmap'],
        'comparison':       comparison,
        'new_discovery':    new_discovery,
        'personality_type': ai.get('personality_type', ''),
        'personality_emoji':ai.get('personality_emoji', ''),
        'personality_desc': ai.get('personality_desc', ''),
        'ai_summary':       ai.get('summary', ''),
    })

# backend generate_report 동일 로직 — Supabase에서 월간 데이터 집계 후 반환
