# app/main.py
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any

from app.services.metadata.dispatcher import extract as dispatch
from app.services.ai_classifier import classify
from app.services.embedding import run as embed, generate_embedding
from app.services.thumbnail_vision import analyze_thumbnail
from app.services.query_expander import expand_query
from app.services.chat import process_chat
from app.services.database import (
    save_content,
    update_content,
    mark_failed,
    check_duplicate,
    search_contents,
    get_deadlines as db_get_deadlines,
    get_or_create_collection,
    get_collections,
    find_similar_contents,
    delete_content,
    get_all_contents_for_reclassify,
    update_ai_fields,
    move_content_collection,
)
from app.routes.archive import router as archive_router
from app.routes.report import router as report_router
from app.routes.auth import router as auth_router

app = FastAPI(title="Keepit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(archive_router)
app.include_router(report_router)
app.include_router(auth_router)


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

class ChatRequest(BaseModel):
    query: str
    user_id: str
    history: list[dict[str, Any]] = []  # [{"role": "user"/"assistant", "content": "..."}]
    shown_ids: list[str] = []  # 이미 보여준 콘텐츠 ID 목록 (재검색 시 제외용)
    content_id: str | None = None  # 마감기한 수정 등 특정 콘텐츠 대상 작업 시


# ── 헬스체크 ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/weekly-report", response_class=HTMLResponse)
async def weekly_report_page(request: Request):
    return templates.TemplateResponse(request, "report_weekly.html")


@app.get("/health")
async def health():
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
        if req.instruction:
            analysis["save_purpose"] = req.instruction

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

        # 유사 콘텐츠 리마인드 메시지 생성
        reminder_message = None
        if similar:
            if len(similar) == 1:
                reminder_message = "유사한 콘텐츠를 저장한 적 있어요."
            else:
                reminder_message = f"유사한 콘텐츠 {len(similar)}개를 저장한 적 있어요."

        has_deadline = analysis.get("has_deadline", False)
        deadline_note = analysis.get("deadline_note")
        deadline_date = analysis.get("deadline_date")
        deadline_confirmation = None
        if has_deadline and deadline_date:
            note_text = deadline_note or deadline_date
            deadline_confirmation = f"마감기한을 발견했어요! '{note_text}'으로 저장할게요. 다르면 말해주세요."

        return {
            "id": content_id,
            "title": metadata.get("title", ""),
            "thumbnail": metadata.get("thumbnail", ""),
            "platform": metadata.get("platform", ""),
            "category": analysis.get("category", ""),
            "one_line_summary": analysis.get("one_line_summary", ""),
            "tags": analysis.get("tags", []),
            "has_deadline": has_deadline,
            "deadline_date": deadline_date,
            "deadline_note": deadline_note,
            "sub_category": analysis.get("sub_category", ""),
            "analysis_status": "completed",
            "deadline_confirmation": deadline_confirmation,
            "reminder_message": reminder_message,
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

    except Exception as e:
        # 분석 중 에러나면 failed 처리
        await mark_failed(content_id)
        raise HTTPException(status_code=500, detail=f"분석 실패: {str(e)}")


# ── 검색 ───────────────────────────────────────────────────────────────────────

SEARCH_FOLLOWUPS = [
    "혹시 유튜브 영상이었나요, 아니면 블로그/뉴스 글이었나요?",
    "어떤 주제였는지 조금 더 기억나시나요? (예: 요리, 여행, IT 등)",
    "언제쯤 저장하셨는지 기억나시나요?",
    "제목에 특정 단어가 포함됐었나요?",
]

@app.post("/search")
async def search(req: SearchRequest):
    """
    자연어로 저장된 콘텐츠 검색.
    유사도 상위 3개만 반환, 결과 없으면 유도 질문 제공.
    """
    expanded = await expand_query(req.query)
    query_embedding = await generate_embedding(expanded)
    if not query_embedding:
        raise HTTPException(status_code=500, detail="검색어 임베딩 실패")

    results = await search_contents(req.user_id, query_embedding, limit=3)

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


@app.get("/deadlines/{user_id}")
async def list_deadlines(user_id: str):
    results = await db_get_deadlines(user_id)
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


# ── 콘텐츠 삭제 / 이동 ─────────────────────────────────────────────────────────

@app.delete("/contents/{content_id}")
async def remove_content(content_id: str, user_id: str):
    """콘텐츠 삭제 — 채팅에서 확인 후 프론트가 호출"""
    success = await delete_content(content_id, user_id)
    if not success:
        raise HTTPException(status_code=500, detail="삭제 실패")
    return {"deleted": True, "content_id": content_id}


class MoveRequest(BaseModel):
    user_id: str
    content_ids: list[str]
    target_folder: str


@app.post("/contents/move")
async def move_contents(req: MoveRequest):
    """콘텐츠 폴더 이동 — 채팅에서 확인 후 프론트가 호출"""
    collection_id = await get_or_create_collection(req.user_id, req.target_folder)
    if not collection_id:
        raise HTTPException(status_code=500, detail="폴더 생성 실패")

    results = []
    for content_id in req.content_ids:
        success = await move_content_collection(content_id, req.user_id, collection_id)
        results.append({"content_id": content_id, "moved": success})

    return {"target_folder": req.target_folder, "results": results}


# ── 재분류 ─────────────────────────────────────────────────────────────────────

@app.post("/admin/reclassify/{user_id}")
async def reclassify_all(user_id: str):
    """
    기존 저장 콘텐츠 전체를 AI로 재분류.
    category, sub_category, 요약, 태그 등 AI 필드만 업데이트.
    """
    contents = await get_all_contents_for_reclassify(user_id)
    if not contents:
        return {"updated": 0, "message": "재분류할 콘텐츠가 없어요."}

    updated, failed = 0, 0
    for c in contents:
        try:
            metadata = {
                "title": c.get("title", ""),
                "platform": c.get("content_type", "web"),
                "summary": c.get("description", ""),
                "original_url": c.get("url", ""),
            }
            analysis = await classify(metadata)
            success = await update_ai_fields(c["id"], analysis)
            if success:
                updated += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[reclassify] {c.get('id')} 실패: {e}")
            failed += 1

    return {"updated": updated, "failed": failed, "total": len(contents)}


# ── 채팅 ───────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(req: ChatRequest):
    """
    자연어 채팅 인터페이스.

    의도 자동 파악 후 처리:
    - search  : 콘텐츠 검색 → 결과 없으면 유도 질문
    - deadline: 마감기한 정리
    - folder  : 유사 폴더 감지 → 확인 요청
    - cleanup : 만료 콘텐츠 정리 안내
    """
    result = await process_chat(req.user_id, req.query, req.history, req.shown_ids, req.content_id)
    return result