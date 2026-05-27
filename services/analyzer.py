# ── OpenAI를 활용한 콘텐츠 분석 ──

import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def analyze_content(content: dict, deadline: str = None) -> dict:
    deadline_str = f"\n마감기한: {deadline}" if deadline else ""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=400,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": f"""웹 콘텐츠를 분석해서 JSON으로 응답해.

URL: {content['url']}
제목: {content['title']}
내용: {content['text'][:1500]}{deadline_str}

반환할 JSON 필드:
- title: 콘텐츠 제목
- category: 대분류 (음악/딥러닝/디자인/카페/요리/여행/개발/영상 등)
- subcategory: 소분류 (재즈/TFT모델/미니멀리즘 등 세분화)
- content_type: article 또는 music 또는 video 또는 place 또는 recipe 또는 other
- summary: 핵심 내용 2문장 (content_type이 music이면 null)
- tags: 태그 배열 (2개)"""
        }]
    )

    return json.loads(resp.choices[0].message.content)

# OpenAI gpt-4o-mini로 URL 콘텐츠를 분석해 카테고리·요약·태그 반환
