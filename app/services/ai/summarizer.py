# app/services/ai/summarizer.py

from app.services.ai.client import client
from app.utils.config import OPENAI_SUMMARY_MODEL


async def summarize_text(text: str) -> str | None:
    if not text:
        return None

    text = text[:12000]

    response = await client.responses.create(
        model=OPENAI_SUMMARY_MODEL,
        input=f"""
다음 자료를 개인 지식 저장소에 저장하기 좋게 요약해줘.

요약 규칙:
1. 핵심 내용을 5문장 이내로 요약
2. 사용자가 나중에 검색했을 때 이해하기 쉽게 작성
3. 광고 문구, 불필요한 메뉴명, 반복 문구는 제외
4. 한국어로 작성

자료:
{text}
"""
    )

    return response.output_text