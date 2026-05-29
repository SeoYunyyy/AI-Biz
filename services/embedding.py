# 텍스트 임베딩 생성 및 Supabase 저장

import os
import json
from openai import OpenAI
from database.db import get_db

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def generate_embedding(text: str) -> list:
    """텍스트 → 1536차원 벡터 변환 (text-embedding-3-small)"""
    text = text.strip()[:8000]
    if not text:
        return []
    try:
        response = client.embeddings.create(model="text-embedding-3-small", input=text)
        return response.data[0].embedding
    except Exception as e:
        print(f"[embedding] OpenAI 오류: {e}")
        return []


def build_embed_text(metadata: dict, analysis: dict, thumbnail_description: str = "") -> str:
    """임베딩용 텍스트 조합 — 제목 + 태그 + 요약 + 썸네일 설명"""
    parts = [
        metadata.get("title", ""),
        " ".join(analysis.get("tags", [])),
        analysis.get("one_line_summary", ""),
        analysis.get("detailed_summary", ""),
        metadata.get("summary", ""),
        thumbnail_description,
    ]
    return " ".join(p for p in parts if p).strip()


def save_embedding(content_id: str, embedding: list) -> bool:
    """embeddings 테이블에 벡터 저장"""
    if not embedding:
        return False
    try:
        db = get_db()
        db.table('embeddings').insert({
            "content_id": content_id,
            "embedding": json.dumps(embedding),
        }).execute()
        return True
    except Exception as e:
        print(f"[embedding] Supabase 저장 오류: {e}")
        return False


def run(content_id: str, metadata: dict, analysis: dict, thumbnail_description: str = "") -> bool:
    """메타데이터 + AI 분석 결과 받아서 임베딩 생성 후 저장"""
    embed_text = build_embed_text(metadata, analysis, thumbnail_description)
    if not embed_text:
        print(f"[embedding] content_id={content_id} 임베딩할 텍스트 없음")
        return False
    embedding = generate_embedding(embed_text)
    if not embedding:
        return False
    return save_embedding(content_id, embedding)
