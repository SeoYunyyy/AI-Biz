# app/services/thumbnail_vision.py

import os
import logging

from app.http_client import get_client

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


async def analyze_thumbnail(thumbnail_url: str, title: str) -> str:
    """
    GPT-4o Vision으로 썸네일 이미지를 분석해 텍스트 설명 반환.
    실패 시 빈 문자열 반환 (파이프라인 중단 없음).
    """
    if not thumbnail_url:
        return ""

    try:
        client = get_client()
        response = await client.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": thumbnail_url,
                                    "detail": "low",
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    f'이 썸네일은 "{title}"의 이미지입니다. '
                                    "나중에 이 콘텐츠를 검색할 때 도움이 되도록, "
                                    "썸네일에서 보이는 요소를 검색 키워드로 쉼표로 나열하세요 "
                                    "(단어 또는 짧은 구문, 15개 이내):\n"
                                    "- 썸네일 안에 보이는 텍스트·자막·로고는 그대로 옮겨 적기\n"
                                    "- 인물 이름(알 수 있으면) 또는 외모 특징 (헤어스타일, 안경, 옷차림)\n"
                                    "- 장소·상황 (예: 콘서트 무대, 주방, 강의실)\n"
                                    "- 눈에 띄는 사물·소품·색상"
                                ),
                            },
                        ],
                    }
                ],
                "max_tokens": 200,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.warning(f"[thumbnail_vision] 분석 실패: {e}")
        return ""
