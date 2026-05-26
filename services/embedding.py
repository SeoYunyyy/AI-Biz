import httpx
import json
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


async def generate_embedding(text: str) -> list:
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

    except (httpx.HTTPError, KeyError, IndexError) as e:
        print(f"[embedding] OpenAI 오류: {e}")
        return []


def build_embed_text(metadata: dict, analysis: dict, thumbnail_description: str = "") -> str:
    parts = [
        metadata.get("title", ""),
        " ".join(analysis.get("tags", [])),
        analysis.get("one_line_summary", ""),
        analysis.get("detailed_summary", ""),
        metadata.get("summary", ""),
        thumbnail_description,
    ]
    return " ".join(p for p in parts if p).strip()


async def save_embedding(content_id: str, embedding: list) -> bool:
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
                    "embedding": json.dumps(embedding),
                },
            )
            response.raise_for_status()
        return True

    except httpx.HTTPError as e:
        print(f"[embedding] Supabase 저장 오류: {e}")
        return False


async def run(content_id: str, metadata: dict, analysis: dict, thumbnail_description: str = "") -> bool:
    embed_text = build_embed_text(metadata, analysis, thumbnail_description)
    if not embed_text:
        return False

    embedding = await generate_embedding(embed_text)
    if not embedding:
        return False

    return await save_embedding(content_id, embedding)
