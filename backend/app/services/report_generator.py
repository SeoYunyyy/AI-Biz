"""월간 취향 리포트 생성.

집계 SQL → LLM 내러티브 → 캐싱.
"""
from collections import Counter

from openai import OpenAI
from sqlalchemy import text

from app.config import settings
from app.db.session import SessionLocal


client = OpenAI(api_key=settings.openai_api_key)


def generate_monthly_report(user_id: str, year_month: str) -> dict:
    """
    Args:
        year_month: "YYYY-MM" 형식

    Returns:
        { "narrative": str, "stats": {...} }
    """
    with SessionLocal() as db:
        rows = db.execute(text("""
            SELECT c.id, c.category, c.summary, c.saved_at, c.last_viewed_at,
                   array_remove(array_agg(t.tag), NULL) AS tags
            FROM contents c
            LEFT JOIN tags t ON t.content_id = c.id
            WHERE c.user_id = :uid
              AND to_char(c.saved_at, 'YYYY-MM') = :ym
            GROUP BY c.id
        """), {"uid": user_id, "ym": year_month}).mappings().all()

    if not rows:
        return {
            "narrative": "이번 달에는 저장한 콘텐츠가 없네요. 다음 달에 더 풍성해질 거예요!",
            "stats": {"total": 0, "top_categories": [], "top_tags": []},
        }

    cat_counter = Counter(r["category"] for r in rows if r["category"])
    all_tags = [t for r in rows for t in (r["tags"] or [])]
    tag_counter = Counter(all_tags)

    # 잊고 있는 콘텐츠 — 저장 후 한 번도 안 본 것
    forgotten = [
        {"id": str(r["id"]), "summary": r["summary"]}
        for r in rows if r["last_viewed_at"] is None
    ][:3]

    stats = {
        "total": len(rows),
        "top_categories": cat_counter.most_common(3),
        "top_tags": tag_counter.most_common(10),
        "forgotten": forgotten,
    }

    # 내러티브 생성 프롬프트
    prompt = f"""사용자의 한 달 콘텐츠 저장 패턴 데이터입니다.

- 총 저장 개수: {stats['total']}건
- 가장 많이 저장한 카테고리: {stats['top_categories']}
- 인기 태그: {stats['top_tags']}

이 데이터를 바탕으로 "이달의 나"라는 친근하고 감성적인 톤의 1~2문단 짜리 내러티브를 작성해 주세요.
- 통계 나열이 아니라, 이야기처럼 들리도록.
- 멜론 Recap, 네이버 블로그 돌아보기 같은 감성.
- 사용자에게 직접 말을 거는 어투 ("~ 보내셨네요", "~ 빠지셨군요").
- 끝에 자연스럽게 다음 달 추천 도전 1개를 제안.
"""

    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=500,
    )
    narrative = resp.choices[0].message.content

    return {"narrative": narrative, "stats": stats}
