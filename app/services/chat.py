# app/services/chat.py

import os
import httpx
import json
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import Any

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

INTENT_PROMPT = """사용자 메시지와 대화 맥락을 보고 의도를 분류하세요. 반드시 JSON만 응답.

의도 종류:
- search   : 저장한 콘텐츠를 찾거나 검색하는 요청 (이전 검색의 후속 답변 포함)
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


async def _detect_intent(query: str, history: list[dict[str, Any]]) -> dict:
    try:
        messages = [{"role": "system", "content": INTENT_PROMPT}]
        messages += history[-20:]  # 최근 6개 메시지로 맥락 파악
        messages += [{"role": "user", "content": query}]
        raw = await _llm(messages, model="gpt-4o-mini", max_tokens=80, json_mode=True)
        return json.loads(raw)
    except Exception:
        return {"intent": "general", "folder_name": None}


async def _filter_results(query: str, results: list[dict]) -> list[dict]:
    """LLM으로 장르·분야가 명백히 다른 항목만 제거 (같은 분야 내 세부 차이는 유지)"""
    if not results:
        return results
    try:
        items = "\n".join([
            f"- id:{r['id']} | 제목:{r.get('title','')} | 태그:{','.join(r.get('topics', []))}"
            for r in results
        ])
        raw = await _llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "검색어와 장르/분야가 명백히 다른 콘텐츠만 제거하세요.\n"
                        "규칙:\n"
                        "- 케이팝·아이돌 검색 → 재즈, 클래식, 팝, 뉴스 등 다른 장르 제거\n"
                        "- 재즈 검색 → 케이팝, 뉴스 등 제거\n"
                        "- 같은 장르 내 아티스트·성별·그룹 차이는 제거하지 말 것\n"
                        "- 불확실하면 포함 유지\n"
                        "관련 있는 결과의 id만 JSON 배열로 반환. 예: [\"id1\", \"id2\"]"
                    ),
                },
                {"role": "user", "content": f"검색어: {query}\n\n결과:\n{items}"},
            ],
            model="gpt-4o-mini",
            max_tokens=200,
            json_mode=False,
        )
        import re as _re
        match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
        if not match:
            return results
        valid_ids = json.loads(match.group())
        filtered = [r for r in results if r["id"] in valid_ids]
        return filtered if filtered else results
    except Exception:
        return results


async def _build_context_query(query: str, history: list[dict[str, Any]]) -> str:
    """이전 대화 맥락을 반영한 통합 검색 쿼리 생성.
    원본 쿼리의 핵심 키워드(아티스트명, 곡명 등)는 반드시 유지하고, 대화 맥락의 추가 정보만 보완한다."""
    if not history:
        return query
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "이전 대화를 참고해서 사용자가 찾으려는 콘텐츠를 하나의 검색 쿼리로 만드세요. "
                    "규칙: 원본 쿼리의 아티스트명·곡명·고유명사는 반드시 그대로 유지하세요. "
                    "대화에서 추가된 정보(콘텐츠 유형, 시기 등)만 덧붙이세요. "
                    "50자 이내. 설명 없이 쿼리만 출력."
                ),
            },
            *history[-10:],
            {"role": "user", "content": f"원본 쿼리: {query}"},
        ]
        refined = await _llm(messages, model="gpt-4o-mini", max_tokens=80)
        return refined or query
    except Exception:
        return query


def _fuzzy_match(name: str, candidates: list[str], threshold: float = 0.75) -> str | None:
    name_norm = name.replace(" ", "").lower()
    best_ratio, best_match = 0.0, None
    for c in candidates:
        ratio = SequenceMatcher(None, name_norm, c.replace(" ", "").lower()).ratio()
        if ratio > best_ratio:
            best_ratio, best_match = ratio, c
    return best_match if best_ratio >= threshold else None


# ── 핸들러 ────────────────────────────────────────────────────────────────────

DISSATISFACTION_SIGNALS = ["없", "아니", "못 찾", "모르겠", "그거 말고", "다른 거", "없는데", "아닌데", "틀렸"]

# assistant answer 텍스트에서 유도질문을 이미 했음을 나타내는 마커
_FOLLOWUP_ASKED_MARKERS = [
    "아래 질문으로 범위를 좁혀볼게요",
    "조금 더 알려주시면 다시 찾아볼게요",
    "기억나시나요",
    "유튜브 영상이었나요",
]

def _is_dissatisfied(query: str, history: list[dict[str, Any]]) -> bool:
    """이전 결과에 불만족 표현하는지 감지"""
    if not history:
        return False
    return any(s in query for s in DISSATISFACTION_SIGNALS)

def _has_extra_context(query: str) -> bool:
    """불만족 신호 외에 추가 검색 정보가 있는지 (있으면 바로 검색)"""
    cleaned = query
    for s in DISSATISFACTION_SIGNALS:
        cleaned = cleaned.replace(s, "")
    cleaned = cleaned.strip().replace(" ", "")
    return len(cleaned) >= 4  # 4글자 이상 남으면 의미 있는 추가 정보로 판단

def _already_asked_followup(history: list[dict[str, Any]]) -> bool:
    """history에서 유도질문을 이미 했는지 확인"""
    return any(
        any(marker in m.get("content", "") for marker in _FOLLOWUP_ASKED_MARKERS)
        for m in history
        if m.get("role") == "assistant"
    )


async def _handle_search(user_id: str, query: str, history: list[dict[str, Any]], shown_ids: list[str] = []) -> dict:
    already_asked = _already_asked_followup(history)

    if _is_dissatisfied(query, history):
        if _has_extra_context(query):
            # "없어 남돌 영상인데" 처럼 추가 정보 있으면 → 바로 검색
            pass
        elif already_asked:
            # 유도질문 했는데 또 그냥 없다고만 하면 → 힌트 요청
            return {
                "answer": "그 조건으로도 찾지 못했어요. 제목에 포함된 단어나 저장 시기를 조금 더 알려주시면 다시 찾아볼게요.",
                "results": [],
                "follow_up_questions": [],
            }
        else:
            # 추가 정보 없이 그냥 없다고만 하면 → 유도질문
            return {
                "answer": "찾으시는 게 없었군요. 조금 더 알려주시면 다시 찾아볼게요!",
                "results": [],
                "follow_up_questions": [
                    "유튜브 영상이었나요, 아니면 블로그나 뉴스 글이었나요?",
                    "어떤 주제였는지 기억나시나요? (예: 요리, 여행, IT 등)",
                    "언제쯤 저장하셨는지 기억나시나요?",
                    "제목에 특정 단어가 포함됐었나요?",
                ],
            }

    # 이전 대화가 있으면 맥락 반영한 쿼리로 보강
    context_query = await _build_context_query(query, history) if history else query

    expanded = await expand_query(context_query)
    embedding = await generate_embedding(expanded)
    if not embedding:
        return {
            "answer": "검색어 처리 중 문제가 생겼어요. 다시 시도해주세요.",
            "results": [],
            "follow_up_questions": [],
        }

    threshold = 0.3
    raw_results = await search_contents(user_id, embedding, limit=15, threshold=threshold)
    candidates = [r for r in raw_results if r.get("id") not in shown_ids]
    filtered = await _filter_results(expanded, candidates[:10])
    results = filtered[:5]

    if not results:
        if already_asked or _has_extra_context(query):
            return {
                "answer": "그 조건으로도 찾지 못했어요. 제목에 포함된 단어나 저장 시기를 조금 더 알려주시면 다시 찾아볼게요.",
                "results": [],
                "follow_up_questions": [],
            }
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

    top_similarity = results[0].get("similarity", 0) if results else 0

    if top_similarity >= 0.85:
        return {
            "answer": "이거 맞나요?",
            "results": results[:1],
            "follow_up_questions": ["맞아요", "아니요, 다른 거예요 — 제목이나 내용 키워드를 더 알려주시면 다시 찾아볼게요!"],
        }

    count = len(results)
    if count == 1:
        answer = "이거 맞나요?"
        follow_up = ["맞아요", "아니요, 다른 거예요 — 제목이나 내용 키워드를 더 알려주시면 다시 찾아볼게요!"]
    else:
        answer = f"관련 콘텐츠 {count}개 찾았어요. 찾으시는 거 있나요?"
        follow_up = ["이 중에 없으면 제목이나 내용 키워드를 더 알려주세요!"]

    return {"answer": answer, "results": results, "follow_up_questions": follow_up}


async def _handle_deadline(user_id: str) -> dict:
    from datetime import timedelta

    deadlines = await get_deadlines(user_id)
    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()
    week_later = (today + timedelta(days=7)).isoformat()

    urgent   = [d for d in deadlines if today_str <= (d.get("deadline_date") or "9999") <= week_later]
    relaxed  = [d for d in deadlines if (d.get("deadline_date") or "9999") > week_later]
    expired  = [d for d in deadlines if (d.get("deadline_date") or "9999") < today_str]

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
    expired = [d for d in deadlines if (d.get("deadline_date") or "9999") < today]
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

async def process_chat(user_id: str, query: str, history: list[dict[str, Any]] = [], shown_ids: list[str] = []) -> dict:
    """의도 파악 후 적절한 핸들러 호출. history로 대화 맥락 유지."""
    intent_data = await _detect_intent(query, history)
    intent = intent_data.get("intent", "general")
    folder_name = intent_data.get("folder_name")
    delete_query = intent_data.get("delete_query")
    move_query = intent_data.get("move_query")
    target_folder = intent_data.get("target_folder")

    if intent == "search":
        result = await _handle_search(user_id, query, history, shown_ids)
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
        result = await _handle_search(user_id, query, history, shown_ids)

    result["intent"] = intent
    return result
