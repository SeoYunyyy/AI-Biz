# app/services/ai_classifier.py

import httpx
import json
import os
import re
from typing import Optional

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Keepit 확정 대분류 16개
CATEGORIES = [
    "뉴스/사회", "정치/경제", "스포츠", "게임",
    "종교", "기타/알쓸신잡", "IT/기술", "요리/식품",
    "여행", "영상/엔터", "음악", "독서/책",
    "패션/뷰티", "운동/헬스", "교육/학습", "예술/디자인"
]

SYSTEM_PROMPT = """당신은 Keepit의 AI 큐레이터입니다.
사용자가 저장한 링크를 분석해서 깔끔하게 분류하고 요약해주는 역할이에요.

규칙:
1. 반드시 JSON 형식으로만 응답할 것
2. category는 반드시 제공된 16개 대분류 중 하나로만 선택할 것
3. sub_category는 대분류 안에서 더 세밀한 주제를 2~4글자로 직접 생성할 것
   (예: IT/기술 → "딥러닝", "클라우드", "보안" / 여행 → "유럽여행", "맛집탐방")
4. 마감기한은 반드시 '종료일/마감일'만 추출할 것. 신청 시작일, 오픈일, 출시일은 has_deadline=false로 처리
5. 태그는 한국어로 3~5개, 핵심 키워드만 뽑을 것
6. 요약은 건조하지 않고 사람이 쓴 것처럼 자연스럽게"""


async def classify(metadata: dict, user_instruction: str = "") -> dict:
    """
    추출된 메타데이터를 받아서 AI로 분석.
    user_instruction: 사용자가 채팅으로 넘긴 지시사항 (예: "생비과제 폴더에 넣어줘")
    """
    prompt = _build_prompt(metadata, user_instruction)

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
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 700,
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


def _build_prompt(metadata: dict, user_instruction: str = "") -> str:
    instruction_block = ""
    if user_instruction:
        instruction_block = f"\n사용자 지시사항: {user_instruction}\n(위 지시사항을 user_collection 필드에 반영해주세요)"

    categories_str = "\n".join(f"- {c}" for c in CATEGORIES)

    return f"""
다음 링크를 분석해서 JSON으로 응답해주세요.

[링크 정보]
제목: {metadata.get('title', '없음')}
플랫폼: {metadata.get('platform', '없음')}
내용: {metadata.get('summary', '없음')}
URL: {metadata.get('original_url', '없음')}
{instruction_block}

[선택 가능한 대분류 - 반드시 아래 중 하나만 선택]
{categories_str}

[응답 형식]
{{
  "one_line_summary": "한 문장으로 핵심 내용 (20자 내외, 간결하게)",
  "detailed_summary": "2~3문장으로 내용 설명. 왜 저장할 만한지도 포함",
  "tags": ["태그1", "태그2", "태그3"],
  "category": "위 16개 대분류 중 하나",
  "sub_category": "대분류 안에서 더 세밀한 주제 (2~4글자, AI가 직접 생성)",
  "save_purpose": "이 링크를 저장한 이유 추측 (예: 나중에 참고할 기술 자료, 여행 계획용 등)",
  "has_deadline": true 또는 false,
  "deadline_date": "신청/이용/참여 마감일(종료일)이 있으면 YYYY-MM-DD 형식으로. 시작일이나 오픈일은 절대 넣지 말 것. 없으면 null",
  "deadline_note": "마감 관련 메모. '~까지 신청', '~까지 사용 가능' 같은 종료 기한만 작성. 시작일은 제외. 없으면 null",
  "user_collection": "사용자가 지정한 폴더명, 없으면 null"
}}
"""


def _validate(result: dict) -> dict:
    """AI 응답 검증 및 기본값 채우기"""
    category = result.get("category", "기타/알쓸신잡")
    if category not in CATEGORIES:
        category = "기타/알쓸신잡"

    return {
        "one_line_summary": result.get("one_line_summary", ""),
        "detailed_summary": result.get("detailed_summary", ""),
        "tags": result.get("tags", [])[:5],
        "category": category,
        "sub_category": result.get("sub_category", ""),
        "save_purpose": result.get("save_purpose", ""),
        "has_deadline": bool(result.get("has_deadline", False)),
        "deadline_date": result.get("deadline_date"),
        "deadline_note": result.get("deadline_note"),
        "user_collection": result.get("user_collection"),
    }


def _empty_result(error: str = "") -> dict:
    return {
        "one_line_summary": "",
        "detailed_summary": "",
        "tags": [],
        "category": "기타/알쓸신잡",
        "sub_category": "",
        "save_purpose": "",
        "has_deadline": False,
        "deadline_date": None,
        "deadline_note": None,
        "user_collection": None,
        "error": error,
    }


def parse_user_input(raw_input: str) -> tuple[str, str]:
    """
    채팅창 입력에서 URL과 사용자 지시사항을 분리.
    반환: (url, instruction)
    
    예시:
    "https://example.com 이거 생비과제 폴더에 저장해줘"
    → ("https://example.com", "생비과제 폴더에 저장해줘")
    """
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, raw_input)
    url = urls[0] if urls else ""
    instruction = re.sub(url_pattern, "", raw_input).strip()
    return url, instruction