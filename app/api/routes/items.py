# app/api/routes/items.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.item import ItemCreate, ItemResponse
from app.db.database import get_db
from app.db.crud import create_item, get_items

from app.utils.source_detector import detect_source_type

from app.services.metadata.router import get_metadata
from app.services.content.extractor import extract_content
from app.services.content.cleaner import clean_text

from app.services.ai.summarizer import summarize_text
from app.services.ai.tagger import generate_tags
from app.services.ai.embedding import create_embedding

router = APIRouter()


@router.post("/", response_model=ItemResponse)
async def save_item(
    request: ItemCreate,
    db: Session = Depends(get_db)
):
    # 1. URL
    url = str(request.url)

    # 2. source type 판별
    source_type = detect_source_type(url)

    # 3. 메타데이터 추출
    metadata = await get_metadata(source_type, url)

    # 4. 본문 추출
    raw_content = await extract_content(source_type, url)

    # 5. 텍스트 정리
    cleaned_content = clean_text(raw_content)

    # 6. 요약 생성
    summary = await summarize_text(cleaned_content)

    # 7. 태그 생성
    tags = await generate_tags(
        cleaned_content,
        source_type
    )

    # 8. 임베딩 생성
    embedding = await create_embedding(cleaned_content)

    # 9. DB 저장 데이터 구성
    item_data = {
        "source_url": url,
        "source_type": source_type,

        "title": metadata.get("title"),
        "description": metadata.get("description"),
        "thumbnail_url": metadata.get("thumbnail_url"),
        "author": metadata.get("author"),
        "published_at": metadata.get("published_at"),

        "content_text": cleaned_content,

        "summary": summary,
        "tags": tags,

        "embedding": embedding
    }

    # 10. DB 저장
    saved_item = create_item(
        db,
        item_data
    )

    return saved_item


@router.get("/", response_model=list[ItemResponse])
def list_saved_items(
    db: Session = Depends(get_db)
):
    return get_items(db)