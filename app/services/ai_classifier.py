# app/services/ai_classifier.py

import json
import os
import re
import logging
from datetime import date, timedelta

from app.http_client import get_client

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

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
4. 마감기한 판단 규칙 — 반드시 보수적으로 판단할 것:
   ✅ 포함할 날짜: 콘텐츠 본문에 아래 표현과 직접 연결된 날짜만
      "~까지 신청", "신청 마감", "접수 기간", "모집 기간", "제출 기한",
      "이벤트 종료", "할인 기간", "응모 기간", "사용 기간", "유효기간"
   ❌ 절대 포함하지 말 것:
      - 방송일·방영일·방영 날짜 (예: "MBC 260523", "KBS 260322 방송")
      - 게시일·업로드일·공개일·작성일·등록일
      - 영상·기사 제목 안에 포함된 날짜
      - URL, 파일명, 시즌·에피소드 번호에 포함된 날짜
      - 이벤트·공연·행사의 시작일 (마감이 아닌 경우)
   📌 판단이 불명확하면 has_deadline: false, deadline_items: [] 로 설정
   - type 종류: "신청 마감" | "사용 기간" | "이벤트 종료" | "기타"
   - date: YYYY-MM-DD 형식
   - note: "신청 마감 7/2", "사용 기간 ~8/31" 형식
   - has_deadline: deadline_items가 하나라도 있으면 true
   - deadline_date: deadline_items 중 가장 이른 date (신청 마감 우선)
   - deadline_note: 모든 항목을 " · "로 연결 (예: "신청 마감 7/2 · 사용 기간 ~8/31")
5. 태그는 한국어로 3~5개, 핵심 키워드만 뽑을 것
6. 요약은 건조하지 않고 사람이 쓴 것처럼 자연스럽게"""


async def classify(metadata: dict, user_instruction: str = "") -> dict:
    """추출된 메타데이터를 받아서 AI로 분석."""
    prompt = _build_prompt(metadata, user_instruction)

    try:
        client = get_client()
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
                "max_tokens": 900,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        result_text = data["choices"][0]["message"]["content"]
        result = json.loads(result_text)
        return _validate(result)

    except Exception as e:
        logger.error(f"[ai_classifier] 분류 오류: {e}")
        return _empty_result(error=str(e))


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
  "one_line_summary": "한 문장으로 핵심 내용 (20자 내외)",
  "detailed_summary": "2~3문장으로 내용 설명. 왜 저장할 만한지도 포함",
  "tags": ["태그1", "태그2", "태그3"],
  "category": "위 16개 대분류 중 하나",
  "sub_category": "대분류 안에서 더 세밀한 주제 (2~4글자)",
  "save_purpose": "이 링크를 저장한 이유 추측",
  "has_deadline": true 또는 false,
  "deadline_date": "가장 이른 마감일 YYYY-MM-DD. 없으면 null",
  "deadline_note": "모든 마감 유형을 · 로 연결. 없으면 null",
  "deadline_items": [
    {{"type": "신청 마감", "date": "YYYY-MM-DD", "note": "신청 마감 7/2"}},
    {{"type": "사용 기간", "date": "YYYY-MM-DD", "note": "사용 기간 ~8/31"}}
  ],
  "user_collection": "사용자가 지정한 폴더명, 없으면 null"
}}

※ deadline_items: 마감기한이 없으면 빈 배열 [], 여러 종류가 있으면 모두 포함할 것
"""


def _validate(result: dict) -> dict:
    """AI 응답 검증 및 기본값 채우기"""
    category = result.get("category", "기타/알쓸신잡")
    if category not in CATEGORIES:
        category = "기타/알쓸신잡"

    # deadline_items 검증 — 형식 오류 및 1년 이상 과거 날짜 제거
    raw_items = result.get("deadline_items", [])
    cutoff = date.today() - timedelta(days=365)   # 1년 이상 과거면 방송일 등 오탐으로 간주
    deadline_items = []
    for item in raw_items:
        if not isinstance(item, dict) or not item.get("date"):
            continue
        try:
            item_date = date.fromisoformat(item["date"])
            if item_date < cutoff:          # 너무 오래된 날짜 제외
                continue
        except ValueError:
            continue
        deadline_items.append(item)

    # 필터링 후 파생 필드 재계산 — AI가 반환한 값을 그대로 쓰면 불일치 발생
    has_deadline = bool(deadline_items)
    if deadline_items:
        # 신청 마감 항목이 있으면 우선, 없으면 가장 이른 날짜
        signup = [i for i in deadline_items if i.get("type") == "신청 마감"]
        primary = signup if signup else deadline_items
        deadline_date = min(i["date"] for i in primary)
        deadline_note = " · ".join(i["note"] for i in deadline_items if i.get("note")) or None
    else:
        deadline_date = None
        deadline_note = None

    return {
        "one_line_summary": result.get("one_line_summary", ""),
        "detailed_summary": result.get("detailed_summary", ""),
        "tags": result.get("tags", [])[:5],
        "category": category,
        "sub_category": result.get("sub_category", ""),
        "save_purpose": result.get("save_purpose", ""),
        "has_deadline": has_deadline,
        "deadline_date": deadline_date,
        "deadline_note": deadline_note,
        "deadline_items": deadline_items,
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
        "deadline_items": [],
        "user_collection": None,
        "error": error,
    }


def parse_user_input(raw_input: str) -> tuple[str, str]:
    """채팅창 입력에서 URL과 사용자 지시사항을 분리."""
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, raw_input)
    url = urls[0] if urls else ""
    instruction = re.sub(url_pattern, "", raw_input).strip()
    return url, instruction
