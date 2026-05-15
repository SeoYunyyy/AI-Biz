# app/services/ai_classifier.py

import httpx
import json
import os
from typing import Optional

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY_HERE")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


async def classify(metadata: dict) -> dict:
    """
    추출된 메타데이터를 받아서 AI로 분석.
    출력: 한줄요약, 상세요약, 태그, 카테고리, 저장목적
    """
    prompt = _build_prompt(metadata)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "response_format": {"type": "json_object"},  # JSON 모드
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "당신은 사용자가 저장한 링크를 분석하는 AI입니다. "
                                "입력된 메타데이터를 바탕으로 JSON 형식으로만 응답하세요."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data = response.json()

        result_text = data["choices"][0]["message"]["content"]
        result = json.loads(result_text)
        return _validate(result)

    except httpx.HTTPError as e:
        return _empty_result(error=str(e))
    except (json.JSONDecodeError, KeyError) as e:
        return _empty_result(error=f"응답 파싱 오류: {str(e)}")


def _build_prompt(metadata: dict) -> str:
    """메타데이터를 AI 프롬프트로 변환"""
    return f"""
다음 링크의 메타데이터를 분석해서 JSON으로 응답해주세요.

제목: {metadata.get('title', '없음')}
플랫폼: {metadata.get('platform', '없음')}
내용: {metadata.get('summary', '없음')}
URL: {metadata.get('original_url', '없음')}

아래 JSON 형식으로만 응답하세요:
{{
  "one_line_summary": "한 문장으로 핵심 내용 요약",
  "detailed_summary": "2-3문장으로 상세 내용 요약",
  "tags": ["태그1", "태그2", "태그3"],
  "category": "뉴스/블로그/영상/쇼핑/장소/기술/기타 중 하나",
  "save_purpose": "이 링크를 저장하는 이유 추측 (예: 나중에 참고, 관심 있는 주제, 구매 고려 등)"
}}
"""


def _validate(result: dict) -> dict:
    """AI 응답 검증 및 기본값 채우기"""
    return {
        "one_line_summary": result.get("one_line_summary", ""),
        "detailed_summary": result.get("detailed_summary", ""),
        "tags": result.get("tags", [])[:5],  # 최대 5개
        "category": result.get("category", "기타"),
        "save_purpose": result.get("save_purpose", ""),
    }


def _empty_result(error: str = "") -> dict:
    return {
        "one_line_summary": "",
        "detailed_summary": "",
        "tags": [],
        "category": "기타",
        "save_purpose": "",
        "error": error,
    }
