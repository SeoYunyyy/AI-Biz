# app/services/ai/tagger.py

import json
from app.services.ai.client import client
from app.utils.config import OPENAI_TAG_MODEL


async def generate_tags(text: str, source_type: str) -> list[str]:
    if not text:
        return [source_type]

    text = text[:8000]

    response = await client.responses.create(
        model=OPENAI_TAG_MODEL,
        input=f"""
다음 자료에 어울리는 태그를 생성해줘.

규칙:
1. 태그는 3개에서 7개
2. 너무 포괄적인 태그는 피하기
3. 한국어 태그 중심
4. 결과는 반드시 JSON 배열만 반환
5. 예: ["AI", "마케팅", "수요예측"]

자료 유형: {source_type}

자료:
{text}
"""
    )

    try:
        tags = json.loads(response.output_text)
        if isinstance(tags, list):
            return list(set([source_type] + tags))
    except json.JSONDecodeError:
        pass

    return [source_type]