"""임베딩 생성 (OpenAI text-embedding-3-small, 1536차원)."""
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


client = OpenAI(api_key=settings.openai_api_key)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def create_embedding(metadata: dict, ai_result: dict) -> list[float]:
    """검색 정확도를 위해 여러 필드를 결합한 텍스트로 임베딩 생성."""
    text = " ".join([
        metadata.get("title", "") or "",
        metadata.get("description", "") or "",
        ai_result.get("summary", "") or "",
        " ".join(ai_result.get("tags", []) or []),
    ]).strip()

    if not text:
        text = "empty"

    resp = client.embeddings.create(
        model=settings.embedding_model,
        input=text[:8000],  # 토큰 제한 안전
    )
    return resp.data[0].embedding


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def embed_query(query: str) -> list[float]:
    """검색·챗봇용 사용자 쿼리 임베딩."""
    resp = client.embeddings.create(
        model=settings.embedding_model,
        input=query[:8000],
    )
    return resp.data[0].embedding
