# Keepit FastAPI 서버 진입점
from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Any

from keepit.services.metadata.dispatcher import extract as dispatch
from keepit.services.ai_classifier import classify
from keepit.services.embedding import run as embed, generate_embedding, build_embed_text
from keepit.services.thumbnail_vision import analyze_thumbnail
from keepit.services.query_expander import expand_query
from keepit.services.chat import process_chat
from keepit.services.database import (
    save_content, update_content, mark_failed, check_duplicate,
    search_contents, get_deadlines, get_or_create_collection, get_collections,
    find_similar_contents, delete_content, get_all_contents_for_reclassify,
    update_ai_fields, move_content_collection, get_old_contents,
    get_groups, create_group, update_group, delete_group, get_group_items,
)

app = FastAPI(title="Keepit API")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ── 페이지 ────────────────────────────────────────────────────────────────────

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": None,
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", ""),
    })

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", ""),
    })

@app.get("/weekly-report")
async def weekly_report_page(request: Request):
    return templates.TemplateResponse("report_weekly.html", {"request": request})

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Keepit API"}


# ── 요청 모델 ─────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    url: str
    user_id: str
    instruction: str = ""
    collection_id: str | None = None

class SearchRequest(BaseModel):
    query: str
    user_id: str
    limit: int = 5

class ChatRequest(BaseModel):
    query: str = ""
    message: str = ""        # 프론트 호환 (message → query)
    user_id: str
    history: list[dict[str, Any]] = []
    shown_ids: list[str] = []
    content_id: str | None = None
    context: dict = {}       # activeContext (그룹/검색 상태)

class MoveRequest(BaseModel):
    user_id: str
    content_ids: list[str]
    target_folder: str

class GroupCreateRequest(BaseModel):
    user_id: str
    name: str
    item_ids: list[str] = []

class GroupUpdateRequest(BaseModel):
    user_id: str
    name: str
    item_ids: list[str] = []


# ── URL 저장 파이프라인 ────────────────────────────────────────────────────────

async def _ingest_logic(req: IngestRequest):
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
            metadata.get("thumbnail", ""), metadata.get("title", ""),
        )
        analysis = await classify(metadata, user_instruction=req.instruction)
        if req.instruction:
            analysis["save_purpose"] = req.instruction

        collection_id = req.collection_id
        if not collection_id and analysis.get("user_collection"):
            collection_id = await get_or_create_collection(req.user_id, analysis["user_collection"])

        await embed(content_id, metadata, analysis, thumbnail_description)

        embed_text = build_embed_text(metadata, analysis, thumbnail_description)
        embedding  = await generate_embedding(embed_text)
        similar    = await find_similar_contents(req.user_id, embedding) if embedding else []

        await update_content(content_id, metadata, analysis,
                             collection_id=collection_id,
                             thumbnail_description=thumbnail_description)

        reminder_message = None
        if similar:
            top_title = similar[0].get("title", "")
            reminder_message = (
                f"'{top_title}'과 비슷한 내용을 저장한 적 있어요."
                if len(similar) == 1
                else f"'{top_title}' 등 {len(similar)}개의 비슷한 내용을 저장한 적 있어요."
            )

        has_deadline   = analysis.get("has_deadline", False)
        deadline_date  = analysis.get("deadline_date")
        deadline_note  = analysis.get("deadline_note")
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
                {"id": s["id"], "title": s["title"], "url": s["url"],
                 "similarity": round(s["similarity"], 2), "one_line_summary": s.get("one_line_summary", "")}
                for s in similar
            ],
            # 프론트 호환 래퍼
            "item": {
                "id": content_id, "url": req.url,
                "title": metadata.get("title", ""),
                "category": analysis.get("category", ""),
                "subcategory": analysis.get("sub_category", ""),
                "summary": analysis.get("one_line_summary", ""),
                "content_type": metadata.get("platform", "web"),
                "tags": analysis.get("tags", []),
                "thumbnail": metadata.get("thumbnail", ""),
                "deadline": deadline_date, "created_at": "",
            },
        }
    except Exception as e:
        await mark_failed(content_id)
        raise HTTPException(status_code=500, detail=f"분석 실패: {str(e)}")


@app.post("/ingest")
async def ingest(req: IngestRequest):
    return await _ingest_logic(req)

@app.post("/api/save")          # 프론트 호환 alias
async def api_save(req: IngestRequest):
    return await _ingest_logic(req)


# ── 검색 ─────────────────────────────────────────────────────────────────────

SEARCH_FOLLOWUPS = [
    "혹시 유튜브 영상이었나요, 아니면 블로그/뉴스 글이었나요?",
    "어떤 주제였는지 조금 더 기억나시나요? (예: 요리, 여행, IT 등)",
    "언제쯤 저장하셨는지 기억나시나요?",
    "제목에 특정 단어가 포함됐었나요?",
]

async def _search_logic(req: SearchRequest):
    expanded = await expand_query(req.query)
    query_embedding = await generate_embedding(expanded)
    if not query_embedding:
        raise HTTPException(status_code=500, detail="검색어 임베딩 실패")
    results = await search_contents(req.user_id, query_embedding, limit=req.limit)
    if not results:
        return {"results": [], "found": False,
                "message": "저장된 콘텐츠 중 찾지 못했어요.",
                "follow_up_questions": SEARCH_FOLLOWUPS}
    return {"results": results, "found": True, "message": None, "follow_up_questions": []}

@app.post("/search")
async def search(req: SearchRequest):
    return await _search_logic(req)

@app.post("/api/search")        # 프론트 호환 alias
async def api_search(req: SearchRequest):
    return await _search_logic(req)


# ── 채팅 ─────────────────────────────────────────────────────────────────────

async def _chat_logic(req: ChatRequest):
    query = req.query or req.message   # 프론트는 message, game_test는 query
    result = await process_chat(req.user_id, query, req.history, req.shown_ids, req.content_id)
    # 프론트 호환: answer → message, results → items
    result["message"] = result.get("answer", "")
    result["items"]   = result.get("results", [])
    return result

@app.post("/chat")
async def chat(req: ChatRequest):
    return await _chat_logic(req)

@app.post("/api/chat")          # 프론트 호환 alias
async def api_chat(req: ChatRequest):
    return await _chat_logic(req)


# ── 마감기한 ─────────────────────────────────────────────────────────────────

@app.get("/deadlines/{user_id}")
async def list_deadlines(user_id: str):
    results = await get_deadlines(user_id)
    return {"deadlines": results}

@app.get("/api/reminders")
async def api_reminders(user_id: str):
    from datetime import date, timedelta
    deadlines = await get_deadlines(user_id)
    today = date.today()
    limit = (today + timedelta(days=3)).isoformat()
    today_str = today.isoformat()
    reminders = [
        {"id": d["id"], "title": d.get("title", ""),
         "deadline": d.get("deadline_date", ""), "url": d.get("url", ""),
         "category": d.get("category", "")}
        for d in deadlines
        if today_str <= (d.get("deadline_date") or "9999") <= limit
    ]
    return reminders


# ── 컬렉션(폴더) ─────────────────────────────────────────────────────────────

@app.get("/collections/{user_id}")
async def get_user_collections(user_id: str):
    results = await get_collections(user_id)
    return {"collections": results}

@app.post("/collections")
async def create_collection(user_id: str, name: str):
    collection_id = await get_or_create_collection(user_id, name)
    if not collection_id:
        raise HTTPException(status_code=500, detail="폴더 생성 실패")
    return {"collection_id": collection_id, "name": name}


# ── 콘텐츠 삭제/이동 ─────────────────────────────────────────────────────────

@app.delete("/contents/{content_id}")
async def remove_content(content_id: str, user_id: str):
    success = await delete_content(content_id, user_id)
    if not success:
        raise HTTPException(status_code=500, detail="삭제 실패")
    return {"deleted": True, "content_id": content_id}

@app.delete("/api/contents/{content_id}")   # 프론트 호환 alias
async def api_remove_content(content_id: str, user_id: str):
    return await remove_content(content_id, user_id)

@app.post("/contents/move")
async def move_contents(req: MoveRequest):
    collection_id = await get_or_create_collection(req.user_id, req.target_folder)
    if not collection_id:
        raise HTTPException(status_code=500, detail="폴더 생성 실패")
    results = []
    for cid in req.content_ids:
        success = await move_content_collection(cid, req.user_id, collection_id)
        results.append({"content_id": cid, "moved": success})
    return {"target_folder": req.target_folder, "results": results}


# ── 그룹 ─────────────────────────────────────────────────────────────────────

@app.get("/api/groups")
async def api_get_groups(user_id: str):
    return {"groups": await get_groups(user_id)}

@app.post("/api/groups")
async def api_create_group(req: GroupCreateRequest):
    group = await create_group(req.user_id, req.name, req.item_ids)
    if not group:
        raise HTTPException(status_code=500, detail="그룹 생성 실패")
    return {"success": True, "group": group}

@app.put("/api/groups/{group_id}")
async def api_update_group(group_id: str, req: GroupUpdateRequest):
    success = await update_group(group_id, req.user_id, req.name, req.item_ids)
    return {"success": success}

@app.delete("/api/groups/{group_id}")
async def api_delete_group(group_id: str, user_id: str):
    success = await delete_group(group_id, user_id)
    return {"success": success, "deleted_id": group_id}

@app.get("/api/groups/{group_id}/items")
async def api_get_group_items(group_id: str, user_id: str):
    return await get_group_items(group_id, user_id)


# ── 카테고리 / 아이템 (아카이브용) ───────────────────────────────────────────

@app.get("/api/categories")
async def api_categories(user_id: str):
    """contents 테이블에서 category/sub_category 집계"""
    import httpx, os as _os
    SUPABASE_URL = _os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = _os.getenv("SUPABASE_SERVICE_ROLE_KEY") or _os.getenv("SUPABASE_SERVICE_KEY", "")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=headers,
                params={"user_id": f"eq.{user_id}",
                        "select": "category,sub_category",
                        "analysis_status": "eq.completed"},
            )
            rows = res.json()
    except Exception:
        return {}
    cats: dict = {}
    for r in rows:
        cat = r.get("category") or "기타"
        sub = r.get("sub_category") or "-"
        cats.setdefault(cat, {})
        cats[cat][sub] = cats[cat].get(sub, 0) + 1
    return {
        cat: [{"name": s, "count": c} for s, c in sorted(subs.items(), key=lambda x: -x[1])]
        for cat, subs in cats.items()
    }

@app.get("/api/items")
async def api_items(user_id: str, category: str = "", subcategory: str = ""):
    import httpx, os as _os
    SUPABASE_URL = _os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = _os.getenv("SUPABASE_SERVICE_ROLE_KEY") or _os.getenv("SUPABASE_SERVICE_KEY", "")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{SUPABASE_URL}/rest/v1/contents",
                headers=headers,
                params={"user_id": f"eq.{user_id}",
                        "category": f"eq.{category}",
                        "sub_category": f"eq.{subcategory}",
                        "analysis_status": "eq.completed",
                        "select": "*",
                        "order": "saved_at.desc"},
            )
            rows = res.json()
    except Exception:
        return {"items": []}
    items = [
        {"id": r.get("id"), "url": r.get("url"), "title": r.get("title"),
         "category": r.get("category", ""), "subcategory": r.get("sub_category", ""),
         "summary": r.get("one_line_summary") or r.get("description", ""),
         "content_type": r.get("content_type", "web"),
         "tags": r.get("topics") or [],
         "thumbnail": r.get("thumbnail_url", ""),
         "deadline": r.get("deadline_date"),
         "created_at": r.get("saved_at", "")}
        for r in rows
    ]
    return {"items": items}


# ── 재분류 ───────────────────────────────────────────────────────────────────

@app.post("/admin/reclassify/{user_id}")
async def reclassify_all(user_id: str):
    contents = await get_all_contents_for_reclassify(user_id)
    if not contents:
        return {"updated": 0, "message": "재분류할 콘텐츠가 없어요."}
    updated, failed = 0, 0
    for c in contents:
        try:
            metadata = {"title": c.get("title", ""), "platform": c.get("content_type", "web"),
                        "summary": c.get("description", ""), "original_url": c.get("url", "")}
            analysis = await classify(metadata)
            if await update_ai_fields(c["id"], analysis):
                updated += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[reclassify] {c.get('id')} 실패: {e}")
            failed += 1
    return {"updated": updated, "failed": failed, "total": len(contents)}
