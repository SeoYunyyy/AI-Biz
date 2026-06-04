# app/services/query_expander.py

import os
import httpx

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

EXPAND_PROMPT = """사용자의 콘텐츠 검색 쿼리를 임베딩 검색에 최적화된 풍부한 문단으로 확장하세요.

규칙:
- 원래 의도를 유지하면서 동의어·관련 개념·시각적 특징·맥락을 추가하세요.
- 썸네일/외모/시각적 특징 언급이 있으면 → 색상·소품·복장·배경 등 시각 키워드를 그대로 포함하고 관련 분야도 추가하세요.
  예) "안경 쓴 사람" → "안경, glasses, 전문가, 강사, 크리에이터, 교수, presenter"
  예) "핑크색 부츠" → "핑크 부츠, pink boots, 핑크색 신발, 패션, 댄스, 퍼포먼스, 걸그룹, 무대"
  예) "노란 배경에 남자" → "노란 배경, yellow background, 남자, 솔로, 뮤직비디오"
  예) "강아지 안고 있는 썸네일" → "강아지, 반려동물, pet, dog, 안고 있는, 유튜브 썸네일"
- 줄임말·닉네임·팬덤 용어는 반드시 원래 이름으로 풀어서 함께 포함하세요:
  예) "여돌" → "여자 아이돌, 걸그룹, girl group, K-pop female idol, 여성 아이돌"
  예) "남돌" → "남자 아이돌, 보이그룹, boy group, K-pop male idol"
  예) "하투하" → "Hearts2Hearts, 하츠투하츠, H2H"
  예) "방탄" → "BTS, 방탄소년단", "엑소" → "EXO, 엑소", "싸이" → "PSY 싸이 강남스타일 Gangnam Style 젠틀맨 한국 솔로 가수"
- 아티스트명·그룹명이 보이면 알고 있는 정보로 보완하세요:
  · 성별: 남자아이돌/보이그룹 또는 여자아이돌/걸그룹
  · 장르, 소속사, 대표곡, 활동 시기 등
  예) "킥플립" → "킥플립 Kickflip 남자아이돌 보이그룹 K-pop"
  예) "뉴진스" → "뉴진스 NewJeans 여자아이돌 걸그룹 K-pop"
  모르는 이름이면 K-pop 아티스트로 추정하고 맥락만 추가하세요.
- 한국어 ↔ 영어 양방향 확장을 반드시 포함하세요:
  · 아티스트명·곡명·앨범명은 한/영 모두 포함
  · 방송 프로그램: 뮤직뱅크↔Music Bank, 엠카운트다운↔M Countdown, 인기가요↔Inkigayo, 음악중심↔Music Core
- 100단어 이내의 단일 단락으로만 출력하세요. (설명 없이 바로)"""


async def expand_query(query: str) -> str:
    """
    검색 쿼리를 임베딩 친화적인 문단으로 확장.
    실패 시 원본 쿼리 그대로 반환 (파이프라인 중단 없음).
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": EXPAND_PROMPT},
                        {"role": "user", "content": f'검색 쿼리: "{query}"'},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 180,
                },
            )
            response.raise_for_status()
            expanded = response.json()["choices"][0]["message"]["content"].strip()
            return expanded or query

    except Exception as e:
        print(f"[query_expander] 확장 실패, 원본 쿼리 사용: {e}")
        return query
