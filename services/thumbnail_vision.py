# GPT-4o Vision으로 썸네일 이미지를 분석해 검색용 키워드 추출

import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def analyze_thumbnail(thumbnail_url: str, title: str) -> str:
    """
    썸네일 이미지 URL → 검색 키워드 텍스트 반환.
    실패 시 빈 문자열 반환 (파이프라인 중단 없음).
    """
    if not thumbnail_url:
        return ""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": thumbnail_url, "detail": "auto"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f'이 썸네일은 "{title}"의 이미지입니다. '
                            "썸네일에서 보이는 요소를 검색 키워드로 추출하세요.\n\n"
                            "추출 기준 (15개 이내):\n"
                            "1. 썸네일 안에 보이는 텍스트·자막·로고는 그대로 옮겨 적기\n"
                            "2. 인물 이름(알 수 있으면) 또는 외모 특징 (헤어스타일, 안경, 옷차림)\n"
                            "3. 장소·상황 (예: 콘서트 무대, 주방, 강의실)\n"
                            "4. 눈에 띄는 사물·소품·색상\n\n"
                            "출력 규칙:\n"
                            "- 반드시 쉼표(,)로만 구분해서 한 줄로 출력\n"
                            "- bullet point(-), 번호(1.), 줄바꿈 절대 사용 금지\n"
                            "출력 예시: MMA 2025, EXO, 콘서트 무대, 회색 의상, 군무, 케이팝"
                        ),
                    },
                ],
            }],
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[thumbnail_vision] 분석 실패: {e}")
        return ""
