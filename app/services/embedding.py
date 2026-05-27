# app/services/embedding.py

import json
import os
import logging

from app.http_client import get_client

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY_HERE")
OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"

SUPABASE_URL = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL_HERE")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "YOUR_SUPABASE_KEY_HERE")


async def generate_embedding(text: str) -> list[float]:
    """텍스트 → 1536차원 벡터 (text-embedding-3-small)"""
    text = text.strip()[:8000]
    if not text:
        return []

    try:
        client = get_client()
        response = await client.post(
            OPENAI_EMBED_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": "text-embedding-3-small", "input": text},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    except Exception as e:
        logger.error(f"[embedding] OpenAI 오류: {e}")
        return []


def build_embed_text(metadata: dict, analysis: dict, thumbnail_description: str = "") -> str:
    """임베딩용 텍스트 조합 (제목 + 태그 + 요약 + 썸네일 설명)"""
    parts = [
        metadata.get("title", ""),
        " ".join(analysis.get("tags", [])),
        analysis.get("one_line_summary", ""),
        analysis.get("detailed_summary", ""),
        metadata.get("summary", ""),
        thumbnail_description,
    ]
    return " ".join(p for p in parts if p).strip()


async def save_embedding(content_id: str, embedding: list[float]) -> bool:
    """embeddings 테이블에 벡터 저장"""
    if not embedding:
        return False

    try:
        client = get_client()
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/embeddings",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={
                "content_id": content_id,
                "embedding": json.dumps(embedding),
            },
            timeout=15.0,
        )
        response.raise_for_status()
        return True

    except Exception as e:
        logger.error(f"[embedding] Supabase 저장 오류: {e}")
        return False


async def run(
    content_id: str,
    metadata: dict,
    analysis: dict,
    thumbnail_description: str = "",
) -> list[float]:
    """
    Fix 4: bool 대신 생성된 embedding 반환.
    호출부에서 embedding을 재사용할 수 있어 이중 API 호출을 방지한다.
    실패 시 빈 리스트 반환.
    """
    embed_text = build_embed_text(metadata, analysis, thumbnail_description)
    if not embed_text:
        logger.warning(f"[embedding] content_id={content_id} 임베딩할 텍스트 없음")
        return []

    embedding = await generate_embedding(embed_text)
    if not embedding:
        return []

    await save_embedding(content_id, embedding)
    return embedding
