# app/services/query_expander.py

import os
import httpx

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

EXPAND_PROMPT = """사용자의 콘텐츠 검색 쿼리를 임베딩 검색에 최적화된 풍부한 문단으로 확장하세요.

규칙:
- 원래 의도를 유지하면서 동의어·관련 개념·시각적 특징·맥락을 추가하세요.
- 썸네일/외모/시각적 특징 언급이 있으면 → 해당 직업·스타일·분야 키워드로 확장하세요.
  예) "안경 쓴 사람" → "안경, 전문가, 강사, 크리에이터, 교수, presenter, glasses"
- 줄임말·닉네임·팬덤 용어는 반드시 원래 이름으로 풀어서 함께 포함하세요:
  예) "하투하" → "Hearts2Hearts, 하츠투하츠, H2H, 하투하"
  예) "루드" → "RUDE!, 루드, 노래제목"
  예) "엑소" → "EXO, 엑소", "방탄" → "BTS, 방탄소년단"
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
