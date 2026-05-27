# app/services/embedding.py

import httpx
import json
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY_HERE")
OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"

SUPABASE_URL = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL_HERE")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "YOUR_SUPABASE_KEY_HERE")


async def generate_embedding(text: str) -> list[float]:
    """
    텍스트 → 1536차원 벡터 변환 (text-embedding-3-small)
    """
    # 8000자 초과하면 잘라냄 (OpenAI 토큰 제한)
    text = text.strip()[:8000]
    if not text:
        return []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENAI_EMBED_URL,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "text-embedding-3-small",
                    "input": text,
                },
            )
            response.raise_for_status()
            data = response.json()

        return data["data"][0]["embedding"]

    except httpx.HTTPError as e:
        print(f"[embedding] OpenAI 오류: {e}")
        return []
    except (KeyError, IndexError) as e:
        print(f"[embedding] 응답 파싱 오류: {e}")
        return []


def build_embed_text(metadata: dict, analysis: dict, thumbnail_description: str = "") -> str:
    """
    임베딩용 텍스트 조합.
    제목 + 태그 + 요약 + 썸네일 설명을 합쳐서 검색 품질을 높임.
    thumbnail_description: GPT-4o Vision이 분석한 썸네일 텍스트 설명
    """
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
    """
    embeddings 테이블에 벡터 저장 (Supabase REST API)
    schema.sql의 embeddings 테이블에 맞춤
    """
    if not embedding:
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
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
                    "embedding": json.dumps(embedding),  # vector 타입은 JSON 문자열로
                },
            )
            response.raise_for_status()
        return True

    except httpx.HTTPError as e:
        print(f"[embedding] Supabase 저장 오류: {e}")
        return False


async def run(content_id: str, metadata: dict, analysis: dict, thumbnail_description: str = "") -> bool:
    """
    외부에서 호출하는 메인 함수.
    메타데이터 + AI 분석 결과 받아서 임베딩 생성 후 저장.

    사용 예:
        from backend.services.embedding import run as embed
        success = await embed(content_id, metadata, analysis, thumbnail_description)
    """
    embed_text = build_embed_text(metadata, analysis, thumbnail_description)
    if not embed_text:
        print(f"[embedding] content_id={content_id} 임베딩할 텍스트 없음")
        return False

    embedding = await generate_embedding(embed_text)
    if not embedding:
        return False

    return await save_embedding(content_id, embedding)
