"""
리포트 서비스 (월간 / 주간)

팀 Supabase 기준: https://irrsxjjraqihjxnhsaxb.supabase.co
SQLAlchemy AsyncSession 방식으로 팀 백엔드 패턴과 통일
"""

import json
import calendar as cal_module
from collections import Counter
from datetime import datetime, timedelta, date, timezone
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv
import os

from models.content import Content

load_dotenv()

openai_client = AsyncOpenAI()


# ────────────────────────────────────────────────────────────
#  유틸
# ────────────────────────────────────────────────────────────

def _get_time_slot(hour: int) -> str:
    if 5 <= hour < 12:
        return "오전"
    elif 12 <= hour < 17:
        return "오후"
    elif 17 <= hour < 21:
        return "저녁"
    else:
        return "심야"


def _get_month_range(year: int, month: int):
    last_day = cal_module.monthrange(year, month)[1]
    return datetime(year, month, 1), datetime(year, month, last_day, 23, 59, 59)


def _get_week_range(year: int, month: int, week: int):
    """week: 1=1~7일, 2=8~14일, 3=15~21일, 4=22~28일, 5=29일~말일"""
    start_day = (week - 1) * 7 + 1
    end_day = min(week * 7, cal_module.monthrange(year, month)[1])
    return datetime(year, month, start_day), datetime(year, month, end_day, 23, 59, 59)


def _calc_streak(dates: list) -> dict:
    if not dates:
        return {"current_streak": 0, "max_streak": 0}
    unique_dates = sorted(set(dates))
    max_streak = current = 1
    for i in range(1, len(unique_dates)):
        if (unique_dates[i] - unique_dates[i - 1]).days == 1:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 1
    date_set = set(unique_dates)
    today = date.today()
    current_streak = 0
    check = today
    while check in date_set:
        current_streak += 1
        check -= timedelta(days=1)
    if current_streak == 0:
        check = today - timedelta(days=1)
        while check in date_set:
            current_streak += 1
            check -= timedelta(days=1)
    return {"current_streak": current_streak, "max_streak": max_streak}


def _calc_estimated_time(content_types: list) -> dict:
    avg_minutes = {
        "youtube": 12, "blog": 5, "news": 3,
        "instagram": 2, "naver_blog": 5, "naver_news": 3, "other": 5,
    }
    total_minutes = sum(
        avg_minutes.get(ct["type"].lower(), 5) * ct["count"]
        for ct in content_types
    )
    h, m = divmod(total_minutes, 60)
    return {
        "total_minutes": total_minutes,
        "display": f"{h}시간 {m}분" if h > 0 else f"{m}분",
    }


# ────────────────────────────────────────────────────────────
#  DB 조회 — SQLAlchemy AsyncSession (팀 패턴)
# ────────────────────────────────────────────────────────────

async def _fetch_contents(
    db: AsyncSession, user_id: UUID, start: datetime, end: datetime
) -> list:
    result = await db.execute(
        select(Content).where(
            and_(
                Content.user_id == user_id,
                Content.analysis_status == "completed",
                Content.saved_at >= start,
                Content.saved_at <= end,
            )
        )
    )
    return result.scalars().all()


async def _fetch_collection_count(
    db: AsyncSession, user_id: UUID, start: datetime, end: datetime
) -> int:
    """기간 내 사용된 고유 컬렉션 수"""
    result = await db.execute(
        select(func.count(Content.collection_id.distinct())).where(
            and_(
                Content.user_id == user_id,
                Content.collection_id.isnot(None),
                Content.saved_at >= start,
                Content.saved_at <= end,
            )
        )
    )
    return result.scalar() or 0


# ────────────────────────────────────────────────────────────
#  통계 계산 (월간·주간 공용)
# ────────────────────────────────────────────────────────────

def _build_stats(contents: list) -> dict:
    word_counter: Counter = Counter()
    type_counter: Counter = Counter()
    time_counter: Counter = Counter()
    hour_counter: Counter = Counter()
    day_counter:  Counter = Counter()
    mood_counter: Counter = Counter()
    dates = []

    for c in contents:
        for t in (c.topics or []):
            word_counter[t] += 1
        for h in (c.hashtags or []):
            word_counter[h.replace("#", "")] += 1
        type_counter[c.content_type or "other"] += 1
        for m in (c.moods or []):
            mood_counter[m] += 1
        if c.saved_at:
            dt = c.saved_at
            # timezone-aware → UTC naive로 정규화
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            time_counter[_get_time_slot(dt.hour)] += 1
            hour_counter[dt.hour] += 1
            day_counter[dt.strftime("%Y-%m-%d")] += 1
            dates.append(dt.date())

    return {
        "total":           len(contents),
        "word_cloud":      [{"text": w, "value": v} for w, v in word_counter.most_common(30)],
        "top5_topics":     [{"topic": w, "count": v} for w, v in word_counter.most_common(5)],
        "content_types":   [{"type": k, "count": v} for k, v in type_counter.most_common()],
        "time_distribution":[{"slot": k, "count": v} for k, v in time_counter.most_common()],
        "peak_slot":       time_counter.most_common(1)[0][0] if time_counter else "알 수 없음",
        "peak_hour":       hour_counter.most_common(1)[0][0] if hour_counter else None,
        "top_moods":       [{"mood": k, "count": v} for k, v in mood_counter.most_common(5)],
        "streak":          _calc_streak(dates),
        "estimated_time":  _calc_estimated_time([{"type": k, "count": v} for k, v in type_counter.most_common()]),
        "heatmap":         [{"date": k, "count": v} for k, v in sorted(day_counter.items())],
        "word_counter":    word_counter,  # 비교용 (응답에 미포함)
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


async def _gen_ai_result(year: int, month: int, stats: dict, period: str = "달") -> dict:
    top5      = stats["top5_topics"]
    top_moods = stats["top_moods"]
    ctypes    = stats["content_types"]
    prompt = f"""
사용자의 {year}년 {month}월 콘텐츠 저장 데이터입니다.
- 총 저장 수: {stats['total']}개
- 주요 관심 주제: {', '.join([t['topic'] for t in top5])}
- 주로 저장한 시간대: {stats['peak_slot']} ({stats['peak_hour']}시 전후)
- 주요 분위기: {', '.join([m['mood'] for m in top_moods])}
- 콘텐츠 유형: {', '.join([f"{t['type']} {t['count']}개" for t in ctypes])}

아래 JSON 형식으로 응답해주세요 (한국어):
{{
  "personality_type": "취향 유형 이름 (예: 밤의 미식가, 디지털 탐험가, 감성 수집가 등)",
  "personality_emoji": "유형을 표현하는 이모지 1~2개",
  "personality_desc": "유형 설명 1~2문장, 따뜻한 말투",
  "summary": "이 사람의 한 {period}을 2~3문장으로 요약, 따뜻하고 친근한 말투"
}}
"""
    resp = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ────────────────────────────────────────────────────────────
#  월간 리포트
# ────────────────────────────────────────────────────────────

async def generate_report(
    db: AsyncSession, user_id: UUID, year: int, month: int
) -> dict:
    start, end       = _get_month_range(year, month)
    contents         = await _fetch_contents(db, user_id, start, end)
    if not contents:
        return {"message": "이번 달 저장된 콘텐츠가 없어요", "total": 0}

    stats            = _build_stats(contents)
    collection_count = await _fetch_collection_count(db, user_id, start, end)

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    prev_start, prev_end = _get_month_range(prev_year, prev_month)
    prev_contents = await _fetch_contents(db, user_id, prev_start, prev_end)

    comparison, new_discovery = [], None
    if prev_contents:
        prev_stats    = _build_stats(prev_contents)
        comparison    = _build_comparison(stats["word_counter"], prev_stats["word_counter"])
        new_discovery = _find_new_discovery(stats["word_counter"], prev_stats["word_counter"])

    ai = await _gen_ai_result(year, month, stats, "달")

    return {
        "year": year, "month": month,
        "total_count":       stats["total"],
        "collection_count":  collection_count,
        "word_cloud":        stats["word_cloud"],
        "top5_topics":       stats["top5_topics"],
        "content_types":     stats["content_types"],
        "time_distribution": stats["time_distribution"],
        "peak_time_slot":    stats["peak_slot"],
        "peak_hour":         stats["peak_hour"],
        "top_moods":         stats["top_moods"],
        "streak":            stats["streak"],
        "estimated_time":    stats["estimated_time"],
        "heatmap":           stats["heatmap"],
        "comparison":        comparison,
        "new_discovery":     new_discovery,
        "personality_type":  ai.get("personality_type"),
        "personality_emoji": ai.get("personality_emoji"),
        "personality_desc":  ai.get("personality_desc"),
        "ai_summary":        ai.get("summary"),
    }


# ────────────────────────────────────────────────────────────
#  주간 리포트
# ────────────────────────────────────────────────────────────

async def generate_weekly_report(
    db: AsyncSession, user_id: UUID, year: int, month: int, week: int
) -> dict:
    start, end       = _get_week_range(year, month, week)
    contents         = await _fetch_contents(db, user_id, start, end)
    if not contents:
        return {"message": "이번 주 저장된 콘텐츠가 없어요", "total": 0}

    stats            = _build_stats(contents)
    collection_count = await _fetch_collection_count(db, user_id, start, end)

    if week > 1:
        prev_start, prev_end = _get_week_range(year, month, week - 1)
    else:
        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        last_week  = (cal_module.monthrange(prev_year, prev_month)[1] - 1) // 7 + 1
        prev_start, prev_end = _get_week_range(prev_year, prev_month, last_week)

    prev_contents = await _fetch_contents(db, user_id, prev_start, prev_end)

    comparison, new_discovery = [], None
    if prev_contents:
        prev_stats    = _build_stats(prev_contents)
        comparison    = _build_comparison(stats["word_counter"], prev_stats["word_counter"])
        new_discovery = _find_new_discovery(stats["word_counter"], prev_stats["word_counter"])

    ai = await _gen_ai_result(year, month, stats, "주")

    return {
        "year": year, "month": month, "week": week,
        "period_start":      start.strftime("%Y-%m-%d"),
        "period_end":        end.strftime("%Y-%m-%d"),
        "total_count":       stats["total"],
        "collection_count":  collection_count,
        "word_cloud":        stats["word_cloud"],
        "top5_topics":       stats["top5_topics"],
        "content_types":     stats["content_types"],
        "time_distribution": stats["time_distribution"],
        "peak_time_slot":    stats["peak_slot"],
        "peak_hour":         stats["peak_hour"],
        "top_moods":         stats["top_moods"],
        "streak":            stats["streak"],
        "estimated_time":    stats["estimated_time"],
        "heatmap":           stats["heatmap"],
        "comparison":        comparison,
        "new_discovery":     new_discovery,
        "personality_type":  ai.get("personality_type"),
        "personality_emoji": ai.get("personality_emoji"),
        "personality_desc":  ai.get("personality_desc"),
        "ai_summary":        ai.get("summary"),
    }
