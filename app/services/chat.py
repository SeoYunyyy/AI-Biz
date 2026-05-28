# app/services/chat.py

import os
import httpx
import json
from difflib import SequenceMatcher
from datetime import datetime, timezone

from app.services.embedding import generate_embedding
from app.services.query_expander import expand_query
from app.services.database import (
    search_contents,
    get_deadlines,
    get_collections,
    get_old_contents,
    get_or_create_collection,
    move_content_collection,
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

INTENT_PROMPT = """사용자 메시지를 보고 의도를 분류하세요. 반드시 JSON만 응답.

의도 종류:
- search   : 저장한 콘텐츠를 찾거나 검색하는 요청
- deadline : 마감기한 관련 질문 ("마감 언제야", "임박한 거 뭐야" 등)
- folder   : 폴더 생성·지정·관리 ("이 링크 OO 폴더에 넣어줘" 등)
- move     : 콘텐츠를 다른 폴더로 이동 ("OO 폴더로 옮겨줘", "폴더 위치 바꿔줘" 등)
- cleanup  : 오래된·만료된 콘텐츠 정리 또는 리마인드 요청
             ("오래된 거 정리해줘", "정리할 거 뭐있지", "리마인드 해줘봐",
              "쌓인 거 뭐 있어", "안 보는 거 뭐야", "오래된 거 알려줘" 등)
- delete   : 특정 콘텐츠 삭제 요청 ("OO 관련 삭제해줘", "이거 지워줘" 등)
- general  : 그 외

응답 형식:
{"intent": "search", "folder_name": null, "delete_query": null, "move_query": null, "target_folder": null}

folder_name: 폴더 의도일 때만 폴더명 추출, 없으면 null
delete_query: 삭제 의도일 때 삭제 대상 키워드 추출 (예: "딥러닝"), 없으면 null
move_query: 이동 의도일 때 이동할 콘텐츠 키워드 (예: "에릭센 기사"), 없으면 null
target_folder: 이동 의도일 때 목적지 폴더명 (예: "스포츠"), 없으면 null"""


async def _llm(messages: list, model: str = "gpt-4o-mini", max_tokens: int = 500, json_mode: bool = False) -> str:
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


async def _detect_intent(query: str) -> dict:
    try:
        raw = await _llm(
            messages=[
                {"role": "system", "content": INTENT_PROMPT},
                {"role": "user", "content": query},
            ],
            model="gpt-4o-mini",
            max_tokens=80,
            json_mode=True,
        )
        return json.loads(raw)
    except Exception:
        return {"intent": "general", "folder_name": None}


def _fuzzy_match(name: str, candidates: list[str], threshold: float = 0.75) -> str | None:
    """공백 제거 후 유사도 비교. threshold 이상인 가장 유사한 폴더명 반환."""
    name_norm = name.replace(" ", "").lower()
    best_ratio, best_match = 0.0, None
    for c in candidates:
        ratio = SequenceMatcher(None, name_norm, c.replace(" ", "").lower()).ratio()
        if ratio > best_ratio:
            best_ratio, best_match = ratio, c
    return best_match if best_ratio >= threshold else None


# ── 핸들러 ────────────────────────────────────────────────────────────────────

async def _handle_search(user_id: str, query: str) -> dict:
    expanded = await expand_query(query)
    embedding = await generate_embedding(expanded)
    if not embedding:
        return {
            "answer": "검색어 처리 중 문제가 생겼어요. 다시 시도해주세요.",
            "results": [],
            "follow_up_questions": [],
        }

    results = await search_contents(user_id, embedding, limit=3)

    if not results:
        return {
            "answer": "저장된 콘텐츠 중에서 찾지 못했어요. 아래 질문으로 범위를 좁혀볼게요.",
            "results": [],
            "follow_up_questions": [
                "유튜브 영상이었나요, 아니면 블로그나 뉴스 글이었나요?",
                "어떤 주제였는지 기억나시나요? (예: 요리, 여행, IT 등)",
                "언제쯤 저장하셨는지 기억나시나요?",
                "제목에 특정 단어가 포함됐었나요?",
            ],
        }

    context = "\n".join([
        f"- 제목: {r.get('title', '제목 없음')} | 플랫폼: {r.get('content_type', '')} | 요약: {r.get('description', '')}"
        for r in results
    ])
    answer = await _llm(
        messages=[
            {
                "role": "system",
                "content": (
                    "사용자의 저장된 콘텐츠 중 관련 항목을 찾았습니다. "
                    "2~3문장으로 자연스럽게 안내해주세요. 제목을 언급하고 어떤 내용인지 간단히 설명하세요. 한국어로."
                ),
            },
            {"role": "user", "content": f"검색어: {query}\n\n찾은 콘텐츠:\n{context}"},
        ],
        model="gpt-4o",
        max_tokens=180,
    )

    return {"answer": answer, "results": results, "follow_up_questions": []}


async def _handle_deadline(user_id: str) -> dict:
    from datetime import timedelta

    deadlines = await get_deadlines(user_id)
    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()
    week_later = (today + timedelta(days=7)).isoformat()

    urgent   = [d for d in deadlines if today_str <= d.get("deadline_date", "9999") <= week_later]
    relaxed  = [d for d in deadlines if d.get("deadline_date", "9999") > week_later]
    expired  = [d for d in deadlines if d.get("deadline_date", "9999") < today_str]

    if not urgent and not relaxed and not expired:
        return {"answer": "마감기한이 있는 콘텐츠가 없어요.", "results": []}

    context_parts = []
    if urgent:
        context_parts.append("[ 🚨 마감 임박 — 7일 이내 ]")
        context_parts += [
            f"- {d.get('title', '')}: {d.get('deadline_date', '')} ({d.get('deadline_note', '')})"
            for d in urgent
        ]
    if relaxed:
        context_parts.append("\n[ 📅 여유 있음 — 7일 초과 ]")
        context_parts += [
            f"- {d.get('title', '')}: {d.get('deadline_date', '')} ({d.get('deadline_note', '')})"
            for d in relaxed[:5]
        ]
    if expired:
        context_parts.append("\n[ 만료됨 ]")
        context_parts += [
            f"- {d.get('title', '')}: {d.get('deadline_date', '')} ({d.get('deadline_note', '')})"
            for d in expired[:3]
        ]

    answer = await _llm(
        messages=[
            {
                "role": "system",
                "content": (
                    "사용자의 마감기한 목록입니다. "
                    "7일 이내 임박한 것은 긴박하게 강조하고, "
                    "여유 있는 것은 가볍게 언급하고, "
                    "만료된 것은 정리를 권유하세요. "
                    "친근하게. 한국어로. 3~4문장."
                ),
            },
            {"role": "user", "content": "\n".join(context_parts)},
        ],
        model="gpt-4o",
        max_tokens=220,
    )

    return {
        "answer": answer,
        "urgent": urgent,
        "relaxed": relaxed[:5],
        "expired": expired[:3],
    }


async def _handle_folder(user_id: str, folder_name: str) -> dict:
    """유사 폴더 감지 → 확인 요청. 없으면 새로 만들겠다고 안내."""
    collections = await get_collections(user_id)
    existing_names = [c["name"] for c in collections]

    matched = _fuzzy_match(folder_name, existing_names)

    if matched and matched != folder_name:
        return {
            "answer": f"혹시 '{matched}' 폴더를 말씀하시는 건가요? 아니면 '{folder_name}'(으)로 새로 만들까요?",
            "needs_confirmation": True,
            "confirmation_data": {
                "suggested_folder": matched,
                "new_folder_name": folder_name,
            },
            "results": [],
        }

    if folder_name in existing_names:
        return {
            "answer": f"'{folder_name}' 폴더에 저장할게요.",
            "needs_confirmation": False,
            "results": [],
        }

    return {
        "answer": f"'{folder_name}' 폴더가 없어요. 새로 만들까요?",
        "needs_confirmation": True,
        "confirmation_data": {
            "suggested_folder": None,
            "new_folder_name": folder_name,
        },
        "results": [],
    }


async def _handle_cleanup(user_id: str) -> dict:
    deadlines = await get_deadlines(user_id)
    today = datetime.now(timezone.utc).date().isoformat()
    expired = [d for d in deadlines if d.get("deadline_date", "9999") < today]
    old_contents = await get_old_contents(user_id, days=365)

    if not expired and not old_contents:
        return {"answer": "정리할 콘텐츠가 없어요. 저장 목록이 깔끔하네요!", "results": []}

    context_parts = []
    if expired:
        context_parts.append(f"[ 마감 만료 — {len(expired)}개 ]")
        context_parts += [f"- {d.get('title', '')}: {d.get('deadline_date', '')} 만료" for d in expired[:5]]
    if old_contents:
        context_parts.append(f"\n[ 1년 이상 된 콘텐츠 — {len(old_contents)}개 ]")
        context_parts += [f"- {c.get('title', '')} ({c.get('saved_at', '')[:10]} 저장)" for c in old_contents[:5]]

    answer = await _llm(
        messages=[
            {
                "role": "system",
                "content": (
                    "정리 후보 콘텐츠 목록입니다. 만료된 것과 오래된 것을 구분해서 "
                    "삭제를 권유하세요. 친근하게. 한국어로. '삭제해줘라고 말하면 삭제해드릴게요'라고 안내하세요."
                ),
            },
            {"role": "user", "content": "\n".join(context_parts)},
        ],
        model="gpt-4o",
        max_tokens=200,
    )

    return {
        "answer": answer,
        "expired": expired[:5],
        "old_contents": old_contents[:5],
        "action": "cleanup_suggested",
    }


async def _handle_move(user_id: str, move_query: str, target_folder: str) -> dict:
    """콘텐츠를 다른 폴더로 이동 — 후보 검색 후 확인 요청."""
    expanded = await expand_query(move_query)
    embedding = await generate_embedding(expanded)
    if not embedding:
        return {"answer": "이동할 콘텐츠를 찾지 못했어요.", "results": []}

    results = await search_contents(user_id, embedding, limit=5)
    if not results:
        return {"answer": f"'{move_query}' 관련 콘텐츠를 찾지 못했어요.", "results": []}

    collections = await get_collections(user_id)
    existing_names = [c["name"] for c in collections]
    matched_folder = _fuzzy_match(target_folder, existing_names) or target_folder

    titles = "\n".join([f"- {r.get('title', '제목 없음')}" for r in results])
    return {
        "answer": (
            f"'{move_query}' 관련 콘텐츠 {len(results)}개를 찾았어요:\n{titles}\n\n"
            f"'{matched_folder}' 폴더로 이동할까요?"
        ),
        "needs_confirmation": True,
        "pending_move_ids": [r["id"] for r in results],
        "target_folder": matched_folder,
        "results": results,
    }


async def _handle_delete(user_id: str, delete_query: str) -> dict:
    """삭제 대상 검색 후 확인 요청."""
    expanded = await expand_query(delete_query)
    embedding = await generate_embedding(expanded)
    if not embedding:
        return {"answer": "삭제할 콘텐츠를 찾지 못했어요.", "results": []}

    results = await search_contents(user_id, embedding, limit=5)
    if not results:
        return {"answer": f"'{delete_query}' 관련 콘텐츠를 찾지 못했어요.", "results": []}

    titles = "\n".join([f"- {r.get('title', '제목 없음')}" for r in results])
    return {
        "answer": f"'{delete_query}' 관련 콘텐츠 {len(results)}개를 찾았어요:\n{titles}\n\n삭제할까요?",
        "needs_confirmation": True,
        "pending_delete_ids": [r["id"] for r in results],
        "results": results,
    }


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

async def process_chat(user_id: str, query: str) -> dict:
    """의도 파악 후 적절한 핸들러 호출."""
    intent_data = await _detect_intent(query)
    intent = intent_data.get("intent", "general")
    folder_name = intent_data.get("folder_name")
    delete_query = intent_data.get("delete_query")
    move_query = intent_data.get("move_query")
    target_folder = intent_data.get("target_folder")

    if intent == "search":
        result = await _handle_search(user_id, query)
    elif intent == "deadline":
        result = await _handle_deadline(user_id)
    elif intent == "folder" and folder_name:
        result = await _handle_folder(user_id, folder_name)
    elif intent == "cleanup":
        result = await _handle_cleanup(user_id)
    elif intent == "move" and move_query and target_folder:
        result = await _handle_move(user_id, move_query, target_folder)
    elif intent == "delete" and delete_query:
        result = await _handle_delete(user_id, delete_query)
    else:
        result = await _handle_search(user_id, query)

    result["intent"] = intent
    return result
