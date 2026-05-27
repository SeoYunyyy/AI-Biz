# app/main.py
from dotenv import load_dotenv
load_dotenv()

import logging
from contextlib import asynccontextmanager

from typing import Literal
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, AnyHttpUrl

import app.http_client as http_client
from app.auth import get_current_user_id
from app.services.metadata.dispatcher import extract as dispatch
from app.services.ai_classifier import classify
from app.services.embedding import run as embed, generate_embedding
from app.services.thumbnail_vision import analyze_thumbnail
from app.services.chat import process_chat
from app.services.database import (
    save_content,
    update_content,
    mark_failed,
    check_duplicate,
    search_contents,
    fetch_deadlines,
    get_or_create_collection,
    get_collections,
    find_similar_contents,
    get_content,
    delete_content,
    list_contents,
    get_collection_contents,
    delete_collection,
    rename_collection,
    patch_content,
)

logger = logging.getLogger(__name__)


# ── 앱 수명주기 ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await http_client.startup()
    yield
    await http_client.shutdown()


app = FastAPI(title="Keepit API", lifespan=lifespan)


# ── 요청/응답 모델 ─────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    url: AnyHttpUrl
    user_id: str
    instruction: str = ""
    collection_id: str | None = None


class SearchRequest(BaseModel):
    query: str
    user_id: str
    limit: int = 5


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    query: str
    user_id: str
    history: list[ChatMessage] = []
    search_attempt: int = 0
    shown_ids: list[str] = []
    action: Literal["found", "refine"] | None = None   # 버튼 클릭 시 직접 전달


class CreateCollectionRequest(BaseModel):
    user_id: str
    name: str


class UpdateCollectionRequest(BaseModel):
    user_id: str
    name: str


class PatchContentRequest(BaseModel):
    user_id: str
    collection_id: str | None = None  # 폴더 재배정 (None이면 변경 안 함)


# ── 헬스체크 ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "service": "Keepit API"}


# ── 파이프라인 ────────────────────────────────────────────────────────────────

async def _run_pipeline(content_id: str, url: str, user_id: str, instruction: str, collection_id: str | None) -> dict:
    """메타데이터 추출 ~ 임베딩 전 과정 실행 후 결과 반환."""
    metadata = await dispatch(url)

    thumbnail_description = await analyze_thumbnail(
        metadata.get("thumbnail", ""),
        metadata.get("title", ""),
    )

    analysis = await classify(metadata, user_instruction=instruction)

    if not collection_id and analysis.get("user_collection"):
        # 우선순위 1: instruction에서 유저가 직접 언급한 폴더
        collection_id = await get_or_create_collection(user_id, analysis["user_collection"])

    if not collection_id and analysis.get("category"):
        # 우선순위 2: 유저가 폴더를 지정하지 않은 경우 대분류(category)로 자동 배정
        collection_id = await get_or_create_collection(user_id, analysis["category"])

    embedding = await embed(content_id, metadata, analysis, thumbnail_description)
    similar = await find_similar_contents(user_id, embedding) if embedding else []

    await update_content(
        content_id,
        metadata,
        analysis,
        collection_id=collection_id,
        thumbnail_description=thumbnail_description,
    )

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
        "deadline_items": analysis.get("deadline_items", []),
        "sub_category": analysis.get("sub_category", ""),
        "collection_id": collection_id,
        "analysis_status": "completed",
        "similar_contents": [
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


# ── 핵심: URL 저장 파이프라인 ──────────────────────────────────────────────────

@app.post("/ingest")
async def ingest(
    req: IngestRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    if req.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    url_str = str(req.url)

    existing = await check_duplicate(req.user_id, url_str)
    if existing:
        return {"duplicate": True, "content": existing}

    saved = await save_content(req.user_id, url_str)
    if not saved:
        raise HTTPException(status_code=500, detail="초기 저장 실패")

    content_id = saved["id"]

    try:
        result = await _run_pipeline(content_id, url_str, req.user_id, req.instruction, req.collection_id)
        return result
    except Exception as e:
        await mark_failed(content_id)
        raise HTTPException(status_code=500, detail=f"분석 실패: {str(e)}")


@app.get("/contents")
async def list_user_contents(
    user_id: str,
    category: str | None = None,
    platform: str | None = None,
    collection_id: str | None = None,
    date_from: str | None = None,   # YYYY-MM-DD
    date_to: str | None = None,     # YYYY-MM-DD
    limit: int = 20,
    offset: int = 0,
    current_user_id: str = Depends(get_current_user_id),
):
    """콘텐츠 목록 조회 (필터 + 페이지네이션).
    - category: 대분류 (예: IT/기술, 여행)
    - platform: content_type 값 (예: youtube, blog)
    - collection_id: 특정 폴더 필터
    - date_from / date_to: 저장일 범위 (YYYY-MM-DD)
    - limit / offset: 페이지네이션
    """
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    results = await list_contents(
        user_id=user_id,
        category=category,
        platform=platform,
        collection_id=collection_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"contents": results, "limit": limit, "offset": offset}


@app.get("/contents/{content_id}")
async def get_content_status(
    content_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """/ingest 후 처리 상태·결과를 폴링하는 엔드포인트."""
    content = await get_content(content_id, user_id=current_user_id)
    if not content:
        raise HTTPException(status_code=404, detail="콘텐츠를 찾을 수 없습니다.")
    return content


@app.patch("/contents/{content_id}")
async def patch_content_endpoint(
    content_id: str,
    req: PatchContentRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """콘텐츠 폴더 재배정.
    - collection_id: 이동할 폴더 ID (null 전달 시 변경 없음)
    """
    if req.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    updates: dict = {}
    if req.collection_id is not None:
        updates["collection_id"] = req.collection_id

    ok = await patch_content(content_id, req.user_id, updates)
    if not ok:
        raise HTTPException(status_code=500, detail="콘텐츠 수정 실패")
    return {"success": True}


@app.delete("/contents/{content_id}")
async def delete_content_endpoint(
    content_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """콘텐츠 삭제. JWT에서 추출한 user_id로 소유권을 검증하므로 별도 body 불필요."""
    ok = await delete_content(content_id, current_user_id)
    if not ok:
        raise HTTPException(status_code=500, detail="콘텐츠 삭제 실패")
    return {"success": True}


# ── 검색 ───────────────────────────────────────────────────────────────────────

SEARCH_FOLLOWUPS = [
    "혹시 유튜브 영상이었나요, 아니면 블로그/뉴스 글이었나요?",
    "어떤 주제였는지 조금 더 기억나시나요? (예: 요리, 여행, IT 등)",
    "언제쯤 저장하셨는지 기억나시나요?",
    "제목에 특정 단어가 포함됐었나요?",
]


@app.post("/search")
async def search(
    req: SearchRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    if req.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    query_embedding = await generate_embedding(req.query)
    if not query_embedding:
        raise HTTPException(status_code=500, detail="검색어 임베딩 실패")

    results = await search_contents(req.user_id, query_embedding, limit=req.limit)

    if not results:
        return {
            "results": [],
            "found": False,
            "message": "저장된 콘텐츠 중 찾지 못했어요. 아래 힌트를 참고해서 다시 검색해보세요.",
            "follow_up_questions": SEARCH_FOLLOWUPS,
        }

    return {
        "results": results,
        "found": True,
        "message": None,
        "follow_up_questions": [],
    }


# ── 마감기한 ───────────────────────────────────────────────────────────────────

@app.get("/deadlines/{user_id}")
async def list_deadlines(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    results = await fetch_deadlines(user_id)
    return {"deadlines": results}


# ── 컬렉션(폴더) ───────────────────────────────────────────────────────────────

@app.get("/collections/{user_id}")
async def get_user_collections(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    results = await get_collections(user_id)
    return {"collections": results}


@app.post("/collections")
async def create_collection(
    req: CreateCollectionRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    if req.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    collection_id = await get_or_create_collection(req.user_id, req.name)
    if not collection_id:
        raise HTTPException(status_code=500, detail="폴더 생성 실패")
    return {"collection_id": collection_id, "name": req.name}


@app.get("/collections/{collection_id}/contents")
async def list_collection_contents(
    collection_id: str,
    user_id: str,
    limit: int = 20,
    offset: int = 0,
    current_user_id: str = Depends(get_current_user_id),
):
    """특정 폴더에 속한 콘텐츠 목록 조회 (페이지네이션 지원)."""
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    results = await get_collection_contents(collection_id, user_id, limit, offset)
    return {
        "contents": results,
        "collection_id": collection_id,
        "limit": limit,
        "offset": offset,
    }


@app.patch("/collections/{collection_id}")
async def update_collection_endpoint(
    collection_id: str,
    req: UpdateCollectionRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """폴더 이름 변경."""
    if req.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    ok = await rename_collection(collection_id, req.user_id, req.name)
    if not ok:
        raise HTTPException(status_code=500, detail="폴더 이름 변경 실패")
    return {"success": True, "collection_id": collection_id, "name": req.name}


@app.delete("/collections/{collection_id}")
async def delete_collection_endpoint(
    collection_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """폴더 삭제. 소속 콘텐츠의 collection_id는 null로 해제 후 폴더를 삭제한다."""
    ok = await delete_collection(collection_id, current_user_id)
    if not ok:
        raise HTTPException(status_code=500, detail="폴더 삭제 실패")
    return {"success": True}


# ── 채팅 ───────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(
    req: ChatRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    if req.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="본인 데이터만 접근할 수 있습니다.")

    history = [m.model_dump() for m in req.history]
    result = await process_chat(
        req.user_id, req.query, history,
        search_attempt=req.search_attempt,
        shown_ids=req.shown_ids,
        action=req.action,
    )
    return result
