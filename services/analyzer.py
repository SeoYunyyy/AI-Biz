# OpenAI를 활용한 콘텐츠 AI 분류 (카테고리·요약·태그·마감일 자동 감지)

import os
import re
import json
from openai import OpenAI
from datetime import datetime, timezone

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

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
3. sub_category는 콘텐츠의 핵심 주제·프로그램·인물·종목 기준으로 2~4글자로 생성할 것
   - 반드시 '무엇에 관한 내용인가'로 정할 것 (기사 형태·유형·뉴스 종류로 정하면 안 됨)
   - 대분류명 반복 금지
   - 좋은 예: 영상/엔터 → "나는솔로", "런닝맨", "아이유" / 스포츠 → "축구", "에릭센" / IT/기술 → "딥러닝", "클라우드"
   - 나쁜 예: "방송이슈", "연예뉴스", "라이브방송", "스포츠뉴스", "IT소식" (유형·형태로 분류한 것)
4. 마감기한 판단 규칙 (아래를 엄격히 따를 것):
   - has_deadline=true로 처리하는 경우:
     · 신청/접수 마감일: "~까지 신청", "접수 마감", "지원 마감"
     · 사용/이용 종료일: "~까지 사용 가능", "서비스 종료", "이용 기간 ~까지"
     · 이벤트/혜택 종료일: "~까지 할인", "이벤트 종료"
     · 사용자 메모에 "~까지", "~마감", "~까지만" 같은 표현이 있을 때
   - has_deadline=false로 처리하는 경우 (절대 deadline으로 넣지 말 것):
     · 신청 시작일, 오픈일, 출시일, 공개일
     · 기사 작성일/게시일 (예: "기사입력2026-05-27", "27일 방송", "5월 27일 공개")
     · 방송 날짜, 촬영 날짜, 행사 개최일 (시작하는 날짜)
     · 단순 날짜 언급
   - deadline_date 우선순위 규칙 (매우 중요):
     · 신청/접수 마감일을 반드시 최우선으로 사용할 것
     · 조건부 마감(심사 통과자 대상 등 일부에게만 해당하는 날짜)은
       deadline_date에 절대 넣지 말 것 — deadline_note에만 간략히 언급
   - deadline_date: 년도가 명시되지 않은 경우 반드시 오늘 날짜의 연도 사용. YYYY-MM-DD 형식
   - deadline_note: 마감 유형을 반드시 괄호 없이 앞에 명시할 것
     · 신청 마감만 있을 때: "신청 마감 7/2"
     · 사용 기간만 있을 때: "사용 기간 ~8/31"
     · 둘 다 있을 때: "신청 마감 7/2 · 사용 기간 ~8/31"
5. 태그는 한국어로 3~5개, 핵심 키워드 + 상위 분류 포함:
   - K-pop 여자 아이돌/걸그룹 → 반드시 "여자아이돌" 또는 "걸그룹" 태그 포함
   - K-pop 남자 아이돌/보이그룹 → 반드시 "남자아이돌" 또는 "보이그룹" 태그 포함
6. 요약은 건조하지 않고 사람이 쓴 것처럼 자연스럽게"""


def analyze_content(metadata: dict, user_instruction: str = "") -> dict:
    """
    추출된 메타데이터를 받아서 AI로 분류.
    user_instruction: 사용자가 넘긴 지시사항 (예: "생비과제 폴더에 넣어줘")
    실패 시 _empty_result() 반환 (파이프라인 중단 없음).
    """
    prompt = _build_prompt(metadata, user_instruction)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=700,
        )
        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)
        return _validate(result)

    except Exception as e:
        print(f"[analyzer] AI 분류 오류: {e}")
        return _empty_result(error=str(e))


def _build_prompt(metadata: dict, user_instruction: str = "") -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    categories_str = "\n".join(f"- {c}" for c in CATEGORIES)

    instruction_block = ""
    if user_instruction:
        instruction_block = (
            f"\n사용자 메모: {user_instruction}\n"
            f"(폴더명이 있으면 user_collection에 반영, '~까지·마감·까지만' 등 마감 표현이 있으면 deadline 필드에도 반영)"
        )

    return f"""
다음 링크를 분석해서 JSON으로 응답해주세요.
오늘 날짜: {today}
※ 오늘 날짜는 년도 추론 전용입니다. 콘텐츠에 마감일이 명시되지 않으면 deadline_date는 반드시 null로 할 것.

[링크 정보]
제목: {metadata.get('title', '없음')}
플랫폼: {metadata.get('platform', '없음')}
내용: {metadata.get('summary', '없음')}
URL: {metadata.get('original_url', metadata.get('url', '없음'))}
{instruction_block}

[선택 가능한 대분류 - 반드시 아래 중 하나만 선택]
{categories_str}

[응답 형식]
{{
  "one_line_summary": "한 문장으로 핵심 내용 (20자 내외, 간결하게)",
  "detailed_summary": "2~3문장으로 내용 설명. 왜 저장할 만한지도 포함",
  "tags": ["태그1", "태그2", "태그3"],
  "category": "위 16개 대분류 중 하나",
  "sub_category": "핵심 주제·프로그램·인물·종목 (2~4글자)",
  "save_purpose": "이 링크를 저장한 이유 추측",
  "has_deadline": true 또는 false,
  "deadline_date": "YYYY-MM-DD 또는 null",
  "deadline_note": "마감 유형 명시 또는 null",
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
        "tags":             result.get("tags", [])[:5],
        "category":         category,
        "sub_category":     result.get("sub_category", ""),
        "save_purpose":     result.get("save_purpose", ""),
        "has_deadline":     bool(result.get("has_deadline", False)),
        "deadline_date":    result.get("deadline_date"),
        "deadline_note":    result.get("deadline_note"),
        "user_collection":  result.get("user_collection"),
    }


def _empty_result(error: str = "") -> dict:
    return {
        "one_line_summary": "",
        "detailed_summary": "",
        "tags":             [],
        "category":         "기타/알쓸신잡",
        "sub_category":     "",
        "save_purpose":     "",
        "has_deadline":     False,
        "deadline_date":    None,
        "deadline_note":    None,
        "user_collection":  None,
        "error":            error,
    }


def parse_user_input(raw_input: str) -> tuple:
    """
    채팅창 입력에서 URL과 사용자 지시사항을 분리.
    반환: (url, instruction)
    """
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, raw_input)
    url = urls[0] if urls else ""
    instruction = re.sub(url_pattern, "", raw_input).strip()
    return url, instruction
