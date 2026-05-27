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
                                    f'이미지는 "{title}"의 썸네일입니다. '
                                    "다음을 간결하게 설명하세요 (150자 이내):\n"
                                    "1. 사람이 있다면: 안경 착용 여부, 헤어스타일, 성별, 옷차림, 표정\n"
                                    "2. 배경·장소 (스튜디오, 야외, 실내 등)\n"
                                    "3. 텍스트·자막·그래픽 요소\n"
                                    "4. 전반적 분위기·색감"
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
