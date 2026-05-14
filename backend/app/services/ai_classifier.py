"""AI 분류·태그·요약 (OpenAI).

한 번의 LLM 호출로 카테고리·태그·요약·무드를 JSON으로 받음 (비용·지연 1/3).
"""
import json
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

from app.config import settings


client = OpenAI(api_key=settings.openai_api_key)

# 카테고리 화이트리스트 — 자유 생성 금지 (일관성 확보)
CATEGORIES = [
    "FOOD", "TRAVEL", "FITNESS", "FASHION", "HOME",
    "FINANCE", "LEARN", "CULTURE", "HOBBY", "NEWS",
]

# 프롬프트는 외부 파일로 분리 (튜닝 빈도 높음)
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "classify.md"
if PROMPT_PATH.exists():
    SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
else:
    SYSTEM_PROMPT = f"""당신은 콘텐츠 분류 전문가입니다.
사용자가 저장한 콘텐츠의 메타데이터를 분석하여 JSON으로만 응답하세요.

카테고리는 반드시 다음 중 하나여야 합니다: {CATEGORIES}

응답 형식:
{{
  "category": "FOOD",
  "tags": ["#태그1", "#태그2", "#태그3"],
  "summary": "콘텐츠의 핵심을 2~3줄로 요약",
  "mood": "감성적 무드를 한 단어로 (선택)"
}}

태그는 3~5개, 한국어로, # 기호 포함."""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def classify_content(metadata: dict) -> dict:
    """메타데이터를 받아 분류·태그·요약을 한 번에 생성.

    Args:
        metadata: services.metadata.* 가 반환한 dict.

    Returns:
        {
          "category": str,    # 화이트리스트 강제
          "tags": list[str],  # 최대 5개
          "summary": str,
          "mood": str | None,
        }
    """
    user_text = f"""제목: {metadata.get('title', '')}
설명: {metadata.get('description', '') or ''}
플랫폼: {metadata.get('platform', '')}
본문 일부: {(metadata.get('raw_text') or '')[:300]}"""

    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    try:
        result = json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError as e:
        logger.error(f"LLM JSON 파싱 실패: {e}")
        result = {}

    # 안전장치: 카테고리 화이트리스트 강제 + 태그 5개 제한
    if result.get("category") not in CATEGORIES:
        logger.warning(f"알 수 없는 카테고리 → NEWS 폴백: {result.get('category')}")
        result["category"] = "NEWS"

    result["tags"] = (result.get("tags") or [])[:5]
    result["summary"] = result.get("summary", "")
    result["mood"] = result.get("mood")
    return result
