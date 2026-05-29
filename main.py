# ── Keepit 통합 서버 진입점 ──

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.services.metadata.dispatcher import extract as dispatch
from app.services.ai_classifier import classify
from app.services.embedding import run as embed, generate_embedding, build_embed_text
from app.services.thumbnail_vision import analyze_thumbnail
from app.services.query_expander import expand_query
from app.services.chat import process_chat
from app.services.database import (
    save_content, update_content, mark_failed, check_duplicate,
    search_contents, get_deadlines, get_or_create_collection, get_collections,
    find_similar_contents, delete_content, get_all_contents_for_reclassify,
    update_ai_fields, move_content_collection,
)
from app.routes.archive import router as archive_router
from app.routes.report import router as report_router

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


# ── 페이지 라우트 ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/weekly-report", response_class=HTMLResponse)
async def weekly_report_page(request: Request):
    return templates.TemplateResponse(request, "report_weekly.html")


# ── 요청 모델 ──────────────────────────────────────────────────────────────────

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


class IngestRequest(BaseModel):
    url: str
    user_id: str = DEFAULT_USER_ID
    instruction: str = ""
    collection_id: str | None = None


class SearchRequest(BaseModel):
    query: str
    user_id: str = DEFAULT_USER_ID
    limit: int = 5


class ChatRequest(BaseModel):
    query: str
    user_id: str = DEFAULT_USER_ID
    history: list[dict] = []
    shown_ids: list[str] = []


class MoveRequest(BaseModel):
    user_id: str
    content_ids: list[str]
    target_folder: str


# ── 헬스체크 ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Keepit API"}


# ── URL 저장 파이프라인 ────────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest(req: IngestRequest):
    existing = await check_duplicate(req.user_id, req.url)
    if existing:
        return {"duplicate": True, "content": existing}

    saved = await save_content(req.user_id, req.url)
    if not saved:
        raise HTTPException(status_code=500, detail="초기 저장 실패")

    content_id = saved["id"]

    try:
        metadata = await dispatch(req.url)

        thumbnail_description = await analyze_thumbnail(
            metadata.get("thumbnail", ""),
            metadata.get("title", ""),
        )

        analysis = await classify(metadata, user_instruction=req.instruction)
        if req.instruction:
            analysis["save_purpose"] = req.instruction

        collection_id = req.collection_id
        if not collection_id and analysis.get("user_collection"):
            collection_id = await get_or_create_collection(
                req.user_id, analysis["user_collection"]
            )

        await embed(content_id, metadata, analysis, thumbnail_description)

        embed_text = build_embed_text(metadata, analysis, thumbnail_description)
        embedding = await generate_embedding(embed_text)
        similar = await find_similar_contents(req.user_id, embedding) if embedding else []

        await update_content(
            content_id, metadata, analysis,
            collection_id=collection_id,
            thumbnail_description=thumbnail_description,
        )

        reminder_message = None
        if similar:
            top_title = similar[0].get("title", "")
            reminder_message = (
                f"'{top_title}'과 비슷한 내용을 저장한 적 있어요."
                if len(similar) == 1
                else f"'{top_title}' 등 {len(similar)}개의 비슷한 내용을 저장한 적 있어요."
            )

        return {
            "id": content_id,
            "url": req.url,
            "title": metadata.get("title", ""),
            "thumbnail": metadata.get("thumbnail", ""),
            "platform": metadata.get("platform", ""),
            "category": analysis.get("category", ""),
            "sub_category": analysis.get("sub_category", ""),
            "one_line_summary": analysis.get("one_line_summary", ""),
            "tags": analysis.get("tags", []),
            "has_deadline": analysis.get("has_deadline", False),
            "deadline_date": analysis.get("deadline_date"),
            "deadline_note": analysis.get("deadline_note"),
            "analysis_status": "completed",
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
        await mark_failed(content_id)
        raise HTTPException(status_code=500, detail=f"분석 실패: {str(e)}")


# ── 검색 ───────────────────────────────────────────────────────────────────────

@app.post("/search")
async def search(req: SearchRequest):
    expanded = await expand_query(req.query)
    query_embedding = await generate_embedding(expanded)
    if not query_embedding:
        raise HTTPException(status_code=500, detail="검색어 임베딩 실패")

    results = await search_contents(req.user_id, query_embedding, limit=3)

    if not results:
        return {
            "results": [],
            "found": False,
            "message": "저장된 콘텐츠 중 찾지 못했어요.",
            "follow_up_questions": [
                "유튜브 영상이었나요, 아니면 블로그/뉴스 글이었나요?",
                "어떤 주제였는지 기억나시나요? (예: 요리, 여행, IT 등)",
                "언제쯤 저장하셨는지 기억나시나요?",
                "제목에 특정 단어가 포함됐었나요?",
            ],
        }

    return {"results": results, "found": True, "message": None, "follow_up_questions": []}


# ── 마감기한 ───────────────────────────────────────────────────────────────────

@app.get("/deadlines/{user_id}")
async def list_deadlines(user_id: str):
    results = await get_deadlines(user_id)
    return {"deadlines": results}


# ── 컬렉션 ─────────────────────────────────────────────────────────────────────

@app.get("/collections/{user_id}")
async def list_collections(user_id: str):
    results = await get_collections(user_id)
    return {"collections": results}


@app.post("/collections")
async def create_collection(user_id: str, name: str):
    collection_id = await get_or_create_collection(user_id, name)
    if not collection_id:
        raise HTTPException(status_code=500, detail="폴더 생성 실패")
    return {"collection_id": collection_id, "name": name}


# ── 콘텐츠 삭제 / 이동 ─────────────────────────────────────────────────────────

@app.delete("/contents/{content_id}")
async def remove_content(content_id: str, user_id: str):
    success = await delete_content(content_id, user_id)
    if not success:
        raise HTTPException(status_code=500, detail="삭제 실패")
    return {"deleted": True, "content_id": content_id}


@app.post("/contents/move")
async def move_contents(req: MoveRequest):
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
            if await update_ai_fields(c["id"], analysis):
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
    result = await process_chat(req.user_id, req.query, history=req.history, shown_ids=req.shown_ids)
    return result


@app.exception_handler(Exception)
async def handle_exception(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
