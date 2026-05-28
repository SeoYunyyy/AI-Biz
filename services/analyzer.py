# ── OpenAI를 활용한 콘텐츠 분석 ──

import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


CATEGORIES = [
    '뉴스/사회', '정치/경제', '스포츠', '게임', '종교', '기타',
    'IT/기술', '요리/식품', '여행', '영상/엔터', '음악', '독서/책',
    '패션/뷰티', '운동/헬스', '교육/학습', '예술/디자인',
]


def analyze_content(content: dict, deadline: str = None) -> dict:
    deadline_str = f"\n마감기한: {deadline}" if deadline else ""
    categories_str = ', '.join(CATEGORIES)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""웹 콘텐츠를 분석해서 아래 JSON 형식으로만 응답해. 설명 없이 JSON만.

URL: {content['url']}
제목: {content['title']}
내용: {content['text'][:1500]}{deadline_str}

{{
  "title": "콘텐츠 제목",
  "category": "반드시 다음 중 하나만 선택: {categories_str}",
  "subcategory": "콘텐츠 주제와 가장 유사한 단어 딱 하나 (예: 재즈, 파이썬, 미니멀리즘, 손흥민 등 — 복합어 금지, 단어 하나만)",
  "summary": "핵심 내용 2문장",
  "tags": ["태그1", "태그2"]
}}"""
        }]
    )

    text = resp.choices[0].message.content.strip()
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```|(\{.*\})', text, re.DOTALL)
    json_str = match.group(1) or match.group(2) if match else text
    result = json.loads(json_str)

    if result.get('category') not in CATEGORIES:
        result['category'] = '기타'
    return result

# OpenAI gpt-4o-mini로 URL 콘텐츠를 분석해 카테고리·요약·태그 반환
