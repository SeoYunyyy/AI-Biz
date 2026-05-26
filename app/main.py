# app/main.py
from dotenv import load_dotenv
load_dotenv()


from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

from app.services.metadata.dispatcher import extract as dispatch
from app.services.ai_classifier import classify
from app.services.embedding import run as embed, generate_embedding
from app.services.thumbnail_vision import analyze_thumbnail
from app.services.database import (
    save_content,
    update_content,
    mark_failed,
    check_duplicate,
    search_contents,
    get_deadlines,
    get_or_create_collection, 
    get_collections,
    find_similar_contents,
)

app = FastAPI(title="Keepit API")


# ── 요청/응답 모델 ─────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    url: str
    user_id: str
    instruction: str = ""   # 추가 - "생비과제 폴더에 넣어줘" 같은 지시사항
    collection_id: str | None = None  # 추가 - 프론트에서 선택한 폴더 ID

class SearchRequest(BaseModel):
    query: str
    user_id: str
    limit: int = 5


# ── 헬스체크 ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "service": "Keepit API"}


# ── 핵심: URL 저장 파이프라인 ──────────────────────────────────────────────────

@app.post("/ingest")
async def ingest(req: IngestRequest):
    """
    URL 하나 받아서 끝까지 처리.

    흐름:
    1. 중복 체크
    2. 즉시 저장 (processing)
    3. 메타데이터 추출 (dispatcher)
    4. 썸네일 Vision 분석 (thumbnail_vision)
    5. AI 분류 (ai_classifier)
    6. 임베딩 생성 + 저장 (embedding)
    7. contents 업데이트 (completed)
    """

    # 1. 중복 체크
    existing = await check_duplicate(req.user_id, req.url)
    if existing:
        return {"duplicate": True, "content": existing}

    # 2. 즉시 저장 (분석 전 — 사용자를 기다리게 하지 않음)
    saved = await save_content(req.user_id, req.url)
    if not saved:
        raise HTTPException(status_code=500, detail="초기 저장 실패")

    content_id = saved["id"]

    try:
        # 3. 메타데이터 추출 (dispatcher가 URL 보고 적절한 추출기 선택)
        metadata = await dispatch(req.url)

        # 4. 썸네일 Vision 분석 (thumbnail_url 있을 때만, 실패해도 파이프라인 계속)
        thumbnail_description = await analyze_thumbnail(
            metadata.get("thumbnail", ""),
            metadata.get("title", ""),
        )

        # 5. AI 분류
        analysis = await classify(metadata, user_instruction=req.instruction)

        # 5-1. 사용자 지정 폴더 처리
        collection_id = req.collection_id
        if not collection_id and analysis.get("user_collection"):
            collection_id = await get_or_create_collection(
                req.user_id, analysis["user_collection"]
            )

        # 6. 임베딩 생성 + embeddings 테이블 저장 (썸네일 설명 포함)
        await embed(content_id, metadata, analysis, thumbnail_description)

        # 6-1. 유사 콘텐츠 검색
        from app.services.embedding import generate_embedding, build_embed_text
        embed_text = build_embed_text(metadata, analysis, thumbnail_description)
        embedding = await generate_embedding(embed_text)
        similar = await find_similar_contents(req.user_id, embedding) if embedding else []

        # 7. contents 업데이트 (completed)
        await update_content(content_id, metadata, analysis, collection_id=collection_id, thumbnail_description=thumbnail_description)

        return {
            "id": content_id,
            "title": metadata.get("title", ""),
            "thumbnail": metadata.get("thumbnail", ""),
            "platform": metadata.get("platform", ""),
            "category": analysis.get("category", ""),
            "one_line_summary": analysis.get("one_line_summary", ""),
            "tags": analysis.get("tags", []),
            "has_deadline": analysis.get("has_deadline", False),
            "deadline_date": analysis.get("deadline_date"),
            "deadline_note": analysis.get("deadline_note"),
            "sub_category": analysis.get("sub_category", ""),
            "analysis_status": "completed",
            "similar_contents": [        # 추가
                {
                    "id": s["id"],
                    "title": s["title"],
                    "url": s["url"],
                    "similarity": round(s["similarity"], 2),
                    "one_line_summary": s.get("one_line_summary", ""),
                }
                for s in similar
            ],
        }

    except Exception as e:
        # 분석 중 에러나면 failed 처리
        await mark_failed(content_id)
        raise HTTPException(status_code=500, detail=f"분석 실패: {str(e)}")


# ── 검색 ───────────────────────────────────────────────────────────────────────

@app.post("/search")
async def search(req: SearchRequest):
    """
    자연어로 저장된 콘텐츠 검색.
    "저번에 본 딥러닝 기사" → 벡터 유사도로 찾아줌
    """
    # 검색어를 임베딩으로 변환
    query_embedding = await generate_embedding(req.query)
    if not query_embedding:
        raise HTTPException(status_code=500, detail="검색어 임베딩 실패")

    results = await search_contents(req.user_id, query_embedding, req.limit)
    return {"results": results}


# 마감기한 엔드포인트 추가
@app.get("/deadlines/{user_id}")
async def get_deadlines(user_id: str):
    """마감기한 있는 링크를 마감순으로 반환"""
    results = await get_deadlines(user_id)
    return {"deadlines": results}

@app.get("/collections/{user_id}")
async def get_user_collections(user_id: str):
    """사용자 폴더 목록 조회 - 프론트 드롭다운용"""
    results = await get_collections(user_id)
    return {"collections": results}


@app.post("/collections")
async def create_collection(user_id: str, name: str):
    """폴더 직접 생성"""
    collection_id = await get_or_create_collection(user_id, name)
    if not collection_id:
        raise HTTPException(status_code=500, detail="폴더 생성 실패")
    return {"collection_id": collection_id, "name": name}