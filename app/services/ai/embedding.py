# app/services/ai/embedding.py

from app.services.ai.client import client
from app.utils.config import OPENAI_EMBEDDING_MODEL


async def create_embedding(text: str) -> list[float] | None:
    if not text:
        return None

    text = text[:8000]

    response = await client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=text
    )

    return response.data[0].embedding