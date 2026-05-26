import json
import calendar
from collections import Counter
from datetime import datetime, timedelta, date
from openai import AsyncOpenAI
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

openai_client = AsyncOpenAI()
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
)


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
    """월의 시작일과 종료일 반환"""
    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day}"


def _get_week_range(year: int, month: int, week: int):
    """주의 시작일과 종료일 반환 (1주=1~7일, 2주=8~14일 ...)"""
    start_day = (week - 1) * 7 + 1
    end_day = min(week * 7, calendar.monthrange(year, month)[1])
    return f"{year}-{month:02d}-{start_day:02d}", f"{year}-{month:02d}-{end_day:02d}"


def _calc_streak(dates: list) -> dict:
    """연속 저장 기록 계산"""
    if not dates:
        return {"current_streak": 0, "max_streak": 0}

    unique_dates = sorted(set(dates))

    # 최장 연속
    max_streak = 1
    current = 1
    for i in range(1, len(unique_dates)):
        if (unique_dates[i] - unique_dates[i - 1]).days == 1:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 1

    # 현재 연속 (오늘 또는 어제 기준)
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
    """콘텐츠 타입별 예상 소비 시간 계산"""
    avg_minutes = {
        "youtube": 12,
        "blog": 5,
        "news": 3,
        "instagram": 2,
        "naver_blog": 5,
        "naver_news": 3,
        "other": 5,
    }
    total_minutes = sum(
        avg_minutes.get(ct["type"].lower(), 5) * ct["count"]
        for ct in content_types
    )
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return {
        "total_minutes": total_minutes,
        "display": f"{hours}시간 {minutes}분" if hours > 0 else f"{minutes}분",
    }


def _fetch_contents(user_id: str, start: str, end: str) -> list:
    res = (
        supabase.table("contents")
        .select("topics, moods, hashtags, content_type, saved_at, title")
        .eq("user_id", user_id)
        .eq("analysis_status", "completed")
        .gte("saved_at", start)
        .lte("saved_at", end)
        .execute()
    )
    return res.data


def _build_stats(contents: list) -> dict:
    """공통 통계 계산 (월간·주간 공용)"""
    total = len(contents)

    # 워드클라우드 (topics + hashtags 빈도)
    word_counter: Counter = Counter()
    for c in contents:
        for t in (c.get("topics") or []):
            word_counter[t] += 1
        for h in (c.get("hashtags") or []):
            word_counter[h.replace("#", "")] += 1

    word_cloud = [{"text": w, "value": v} for w, v in word_counter.most_common(30)]
    top5_topics = [{"topic": w, "count": v} for w, v in word_counter.most_common(5)]

    # 콘텐츠 타입 분포
    type_counter: Counter = Counter()
    for c in contents:
        type_counter[c.get("content_type", "other")] += 1
    content_types = [{"type": k, "count": v} for k, v in type_counter.most_common()]

    # 시간대 + 히트맵용 날짜별 카운트
    time_counter: Counter = Counter()
    hour_counter: Counter = Counter()
    day_counter: Counter = Counter()
    dates = []

    for c in contents:
        saved_at = c.get("saved_at")
        if saved_at:
            dt = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
            time_counter[_get_time_slot(dt.hour)] += 1
            hour_counter[dt.hour] += 1
            day_counter[dt.strftime("%Y-%m-%d")] += 1
            dates.append(dt.date())

    peak_slot = time_counter.most_common(1)[0][0] if time_counter else "알 수 없음"
    peak_hour = hour_counter.most_common(1)[0][0] if hour_counter else None
    time_distribution = [{"slot": k, "count": v} for k, v in time_counter.most_common()]

    # 분위기
    mood_counter: Counter = Counter()
    for c in contents:
        for m in (c.get("moods") or []):
            mood_counter[m] += 1
    top_moods = [{"mood": k, "count": v} for k, v in mood_counter.most_common(5)]

    # 연속 저장 + 예상 시청 시간 + 히트맵
    streak = _calc_streak(dates)
    estimated_time = _calc_estimated_time(content_types)
    heatmap = [{"date": k, "count": v} for k, v in sorted(day_counter.items())]

    return {
        "total": total,
        "word_cloud": word_cloud,
        "top5_topics": top5_topics,
        "content_types": content_types,
        "time_distribution": time_distribution,
        "peak_slot": peak_slot,
        "peak_hour": peak_hour,
        "top_moods": top_moods,
        "streak": streak,
        "estimated_time": estimated_time,
        "heatmap": heatmap,
        "word_counter": word_counter,  # 비교용 (response에는 미포함)
    }


def _build_comparison(curr_wc: Counter, prev_wc: Counter, top_n: int = 5) -> list:
    """전기간 대비 변화 계산"""
    comparison = []
    for topic, curr_count in curr_wc.most_common(10):
        prev_count = prev_wc.get(topic, 0)
        if prev_count == 0:
            comparison.append({"topic": topic, "curr_count": curr_count,
                                "prev_count": 0, "change": "new", "pct": None})
        else:
            pct = round((curr_count - prev_count) / prev_count * 100)
            change = "up" if pct > 0 else "down" if pct < 0 else "same"
            comparison.append({"topic": topic, "curr_count": curr_count,
                                "prev_count": prev_count, "change": change, "pct": pct})
    return comparison[:top_n]


def _find_new_discovery(curr_wc: Counter, prev_wc: Counter):
    """이전 기간에 없던 신규 관심사"""
    new_topics = [(t, c) for t, c in curr_wc.most_common() if prev_wc.get(t, 0) == 0]
    if new_topics:
        return {"topic": new_topics[0][0], "count": new_topics[0][1]}
    return None


async def _gen_ai_result(year: int, month: int, stats: dict, period: str = "달") -> dict:
    """AI 취향 유형 + 총평 동시 생성 (JSON mode)"""
    top5 = stats["top5_topics"]
    top_moods = stats["top_moods"]
    content_types = stats["content_types"]
    peak_slot = stats["peak_slot"]
    peak_hour = stats["peak_hour"]
    total = stats["total"]

    prompt = f"""
사용자의 {year}년 {month}월 콘텐츠 저장 데이터입니다.
- 총 저장 수: {total}개
- 주요 관심 주제: {', '.join([t['topic'] for t in top5])}
- 주로 저장한 시간대: {peak_slot} ({peak_hour}시 전후)
- 주요 분위기: {', '.join([m['mood'] for m in top_moods])}
- 콘텐츠 유형: {', '.join([f"{t['type']} {t['count']}개" for t in content_types])}

아래 JSON 형식으로 응답해주세요 (한국어):
{{
  "personality_type": "취향 유형 이름 (예: 밤의 미식가, 디지털 탐험가, 감성 수집가 등 2~4글자 형용사+명사)",
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


# ────────────────────────────────────────────────────────────────
#  월간 리포트
# ────────────────────────────────────────────────────────────────
async def generate_report(user_id: str, year: int, month: int) -> dict:
    start, end = _get_month_range(year, month)
    contents = _fetch_contents(user_id, start, end)

    if not contents:
        return {"message": "이번 달 저장된 콘텐츠가 없어요", "total": 0}

    stats = _build_stats(contents)

    # 전월 데이터
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    prev_start, prev_end = _get_month_range(prev_year, prev_month)
    prev_contents = _fetch_contents(user_id, prev_start, prev_end)

    comparison, new_discovery = [], None
    if prev_contents:
        prev_stats = _build_stats(prev_contents)
        comparison = _build_comparison(stats["word_counter"], prev_stats["word_counter"])
        new_discovery = _find_new_discovery(stats["word_counter"], prev_stats["word_counter"])

    ai = await _gen_ai_result(year, month, stats, "달")

    return {
        "year": year,
        "month": month,
        "total_count": stats["total"],
        "word_cloud": stats["word_cloud"],
        "top5_topics": stats["top5_topics"],
        "content_types": stats["content_types"],
        "time_distribution": stats["time_distribution"],
        "peak_time_slot": stats["peak_slot"],
        "peak_hour": stats["peak_hour"],
        "top_moods": stats["top_moods"],
        "streak": stats["streak"],                 # ★ 연속 저장 기록
        "estimated_time": stats["estimated_time"], # ★ 예상 소비 시간
        "heatmap": stats["heatmap"],               # ★ 요일별 히트맵 데이터
        "comparison": comparison,                  # ★ 전월 대비
        "new_discovery": new_discovery,            # ★ 이달의 새로운 발견
        "personality_type": ai.get("personality_type"),   # ★ 취향 유형
        "personality_emoji": ai.get("personality_emoji"),
        "personality_desc": ai.get("personality_desc"),
        "ai_summary": ai.get("summary"),
    }


# ────────────────────────────────────────────────────────────────
#  주간 리포트
# ────────────────────────────────────────────────────────────────
async def generate_weekly_report(user_id: str, year: int, month: int, week: int) -> dict:
    start, end = _get_week_range(year, month, week)
    contents = _fetch_contents(user_id, start, end)

    if not contents:
        return {"message": "이번 주 저장된 콘텐츠가 없어요", "total": 0}

    stats = _build_stats(contents)

    # 전주 데이터
    if week > 1:
        prev_start, prev_end = _get_week_range(year, month, week - 1)
    else:
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        last_day = calendar.monthrange(prev_year, prev_month)[1]
        last_week = (last_day - 1) // 7 + 1
        prev_start, prev_end = _get_week_range(prev_year, prev_month, last_week)

    prev_contents = _fetch_contents(user_id, prev_start, prev_end)

    comparison, new_discovery = [], None
    if prev_contents:
        prev_stats = _build_stats(prev_contents)
        comparison = _build_comparison(stats["word_counter"], prev_stats["word_counter"])
        new_discovery = _find_new_discovery(stats["word_counter"], prev_stats["word_counter"])

    ai = await _gen_ai_result(year, month, stats, "주")

    return {
        "year": year,
        "month": month,
        "week": week,
        "period_start": start,
        "period_end": end,
        "total_count": stats["total"],
        "word_cloud": stats["word_cloud"],
        "top5_topics": stats["top5_topics"],
        "content_types": stats["content_types"],
        "time_distribution": stats["time_distribution"],
        "peak_time_slot": stats["peak_slot"],
        "peak_hour": stats["peak_hour"],
        "top_moods": stats["top_moods"],
        "streak": stats["streak"],
        "estimated_time": stats["estimated_time"],
        "heatmap": stats["heatmap"],
        "comparison": comparison,
        "new_discovery": new_discovery,
        "personality_type": ai.get("personality_type"),
        "personality_emoji": ai.get("personality_emoji"),
        "personality_desc": ai.get("personality_desc"),
        "ai_summary": ai.get("summary"),
    }
