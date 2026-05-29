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
- folder   : 폴더 자체를 새로 만들거나, 지금 보고 있는 특정 링크 하나를 폴더에 지정하는 요청
             ("OO 폴더 만들어줘", "이 링크 OO 폴더에 저장해줘" 등)
- move     : 특정 주제·키워드에 해당하는 저장된 콘텐츠 여러 개를 찾아서 폴더로 모으거나 이동하는 요청
             ("음악 관련 링크들 노래 폴더에 넣어줘", "플레이리스트 노래 폴더로 옮겨줘",
              "OO 관련 자료 전부 OO 폴더에 모아줘", "OO 폴더로 옮겨줘" 등)
- cleanup  : 오래된·만료된 콘텐츠 정리 또는 리마인드 요청
             ("오래된 거 정리해줘", "정리할 거 뭐있지", "리마인드 해줘봐",
              "쌓인 거 뭐 있어", "안 보는 거 뭐야", "오래된 거 알려줘" 등)
- delete   : 특정 콘텐츠 삭제 요청 ("OO 관련 삭제해줘", "이거 지워줘" 등)
- general  : 그 외

응답 형식:
{"intent": "search", "folder_name": null, "delete_query": null, "move_query": null, "target_folder": null}

folder_name: folder 의도일 때만 폴더명 추출, 없으면 null
delete_query: delete 의도일 때 삭제 대상 키워드 추출 (예: "딥러닝"), 없으면 null
move_query: move 의도일 때 이동할 콘텐츠 주제·키워드 (예: "음악", "플레이리스트"), 없으면 null
target_folder: move 의도일 때 목적지 폴더명 (예: "노래"), 없으면 null"""


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

async def _genre_filter(query: str, results: list[dict]) -> list[dict]:
    """LLM으로 검색 의도와 명확히 다른 장르 항목만 제거 (같은 장르 내 세부 차이는 유지)."""
    if len(results) <= 1:
        return results
    try:
        items_str = "\n".join(
            f"[{i}] {r.get('title', '')}"
            for i, r in enumerate(results)
        )
        raw = await _llm(
            messages=[{"role": "user", "content": (
                f"검색어: '{query}'\n\n콘텐츠 목록:\n{items_str}\n\n"
                "검색 의도와 명확히 다른 장르(예: 케이팝 검색에 재즈·클래식 결과)의 항목 번호만 골라줘. "
                "같은 장르 내 세부 차이나 애매한 경우는 절대 제거하지 마.\n"
                '{"remove_indices": []}'
            )}],
            model="gpt-4o-mini",
            max_tokens=80,
            json_mode=True,
        )
        remove = set(json.loads(raw).get("remove_indices", []))
        return [r for i, r in enumerate(results) if i not in remove]
    except Exception:
        return results


async def _handle_search(user_id: str, query: str, shown_ids: list = None, history: list = None) -> dict:
    shown_ids = shown_ids or []
    history = history or []

    expanded = await expand_query(query)
    embedding = await generate_embedding(expanded)
    if not embedding:
        return {"answer": "검색어 처리 중 문제가 생겼어요. 다시 시도해주세요.", "results": [], "follow_up_questions": []}

    # 후보 15개 → shown_ids 제외 → 장르 필터 → 상위 5개
    candidates = await search_contents(user_id, embedding, limit=15)
    candidates = [r for r in candidates if r.get("id") not in shown_ids]
    candidates = await _genre_filter(query, candidates)
    results = candidates[:5]

    if not results:
        already_guided = any(
            "유튜브 영상이었나요" in (h.get("content") or "")
            for h in history if h.get("role") == "assistant"
        )
        follow_ups = (
            ["제목이나 내용에 포함된 단어를 구체적으로 알려주시면 다시 찾아볼게요!"]
            if already_guided else
            [
                "유튜브 영상이었나요, 아니면 블로그나 뉴스 글이었나요?",
                "어떤 주제였는지 기억나시나요? (예: 요리, 여행, IT 등)",
                "언제쯤 저장하셨는지 기억나시나요?",
                "제목에 특정 단어가 포함됐었나요?",
            ]
        )
        return {"answer": "저장된 콘텐츠 중에서 찾지 못했어요.", "results": [], "follow_up_questions": follow_ups}

    if len(results) == 1:
        return {
            "answer": "이거 맞나요?",
            "results": results,
            "follow_up_questions": ["맞아요", "아니요, 다른 거예요 — 키워드를 더 알려주세요!"],
        }

    return {
        "answer": f"{len(results)}개 찾았어요. 찾으시는 거 있나요?",
        "results": results,
        "follow_up_questions": ["이 중에 없으면 키워드를 더 알려주세요!"],
    }


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


async def _handle_folder(user_id: str, folder_name: str, original_query: str = "") -> dict:
    """폴더 즉시 생성 + 관련 콘텐츠 자동으로 채우기."""
    collection_id = await get_or_create_collection(user_id, folder_name)
    if not collection_id:
        return {"answer": f"'{folder_name}' 폴더를 만드는 데 실패했어요.", "results": []}

    # 채우기 의도가 있으면 폴더명으로 관련 콘텐츠 검색 후 이동
    fill_keywords = ["넣어줘", "담아줘", "모아줘", "추가해줘", "채워줘", "관련", "자료", "링크"]
    should_fill = any(kw in original_query for kw in fill_keywords)

    if should_fill:
        expanded = await expand_query(folder_name)
        embedding = await generate_embedding(expanded)
        if embedding:
            results = await search_contents(user_id, embedding, limit=10)
            if results:
                moved = sum(
                    1 for r in results
                    if await move_content_collection(r["id"], user_id, collection_id)
                )
                titles = "\n".join(f"- {r.get('title', '')}" for r in results[:5])
                return {
                    "answer": f"'{folder_name}' 폴더를 만들고 관련 콘텐츠 {moved}개를 추가했어요:\n{titles}",
                    "results": results,
                }

    return {"answer": f"'{folder_name}' 폴더를 만들었어요!", "results": []}


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
    """콘텐츠를 검색해서 폴더로 즉시 이동 (폴더 없으면 생성)."""
    expanded = await expand_query(move_query)
    embedding = await generate_embedding(expanded)
    if not embedding:
        return {"answer": "이동할 콘텐츠를 찾지 못했어요.", "results": []}

    results = await search_contents(user_id, embedding, limit=10)
    if not results:
        return {
            "answer": f"'{move_query}' 관련 저장된 콘텐츠를 찾지 못했어요. 먼저 관련 링크를 저장해보세요.",
            "results": [],
        }

    collection_id = await get_or_create_collection(user_id, target_folder)
    if not collection_id:
        return {"answer": f"'{target_folder}' 폴더를 만드는 데 실패했어요.", "results": []}

    moved = 0
    for r in results:
        if await move_content_collection(r["id"], user_id, collection_id):
            moved += 1

    titles = "\n".join([f"- {r.get('title', '제목 없음')}" for r in results[:5]])
    return {
        "answer": f"'{move_query}' 관련 콘텐츠 {moved}개를 '{target_folder}' 폴더로 이동했어요:\n{titles}",
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

async def process_chat(user_id: str, query: str, history: list = None, shown_ids: list = None) -> dict:
    """의도 파악 후 적절한 핸들러 호출."""
    history = history or []
    shown_ids = shown_ids or []

    intent_data = await _detect_intent(query)
    intent = intent_data.get("intent", "general")
    folder_name = intent_data.get("folder_name")
    delete_query = intent_data.get("delete_query")
    move_query = intent_data.get("move_query")
    target_folder = intent_data.get("target_folder")

    if intent in ("search", "general"):
        result = await _handle_search(user_id, query, shown_ids=shown_ids, history=history)
    elif intent == "deadline":
        result = await _handle_deadline(user_id)
    elif intent == "folder" and folder_name:
        result = await _handle_folder(user_id, folder_name, original_query=query)
    elif intent == "cleanup":
        result = await _handle_cleanup(user_id)
    elif intent == "move" and move_query and target_folder:
        result = await _handle_move(user_id, move_query, target_folder)
    elif intent == "delete" and delete_query:
        result = await _handle_delete(user_id, delete_query)
    else:
        result = await _handle_search(user_id, query, shown_ids=shown_ids, history=history)

    result["intent"] = intent
    return result
