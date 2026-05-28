# app/services/chat.py

import os
import json
import logging
from difflib import SequenceMatcher
from datetime import datetime, timezone

from app.http_client import get_client
from app.services.embedding import generate_embedding
from app.services.database import (
    search_contents,
    fetch_deadlines,
    get_collections,
    get_contents_by_ids,
)

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

INTENT_PROMPT = """사용자의 현재 메시지와 이전 대화를 보고 의도를 분류하세요. 반드시 JSON만 응답.

의도 종류:
- search   : 저장한 콘텐츠를 처음 찾거나, 이전 대화와 무관한 새로운 검색
- found    : 제시된 후보 중 찾던 콘텐츠를 발견했다고 **명시적으로** 확인만 하는 경우
             해당 예시: "맞아", "있어", "이거야", "찾았어", "ㅇㅇ", "응", "맞음", "오케이"
             ⚠️ 아래는 found가 절대 아님 — refine으로 분류할 것:
               - "그중 XX", "그중에서 XX" (특정 조건으로 좁히는 표현)
               - "XX 영상", "XX 거 찾아줘" (콘텐츠명·조건이 포함된 표현)
               - "아니" + 다른 설명, "없어" + 다른 설명
- refine   : 이전 결과가 없거나 틀렸을 때, 또는 조건을 추가·변경해 다시 찾아달라는 요청
             해당 예시: "없어", "아니야", "그거 말고", "다른 거", "못 찾겠어",
                       "그중 뮤직뱅크 거", "그중 유튜브 영상", "좀 더 최근 거"
- deadline : 마감기한 관련 ("마감 언제야", "기한 얼마나 남았어", "임박한 거" 등)
- folder   : 폴더 생성·지정·관리 ("OO 폴더에 넣어줘", "폴더 만들어줘" 등)
- cleanup  : 오래된·만료된 콘텐츠 정리 ("정리해줘", "오래된 거 지워줘" 등)
- general  : 그 외

응답 형식 (folder_name은 폴더 의도일 때만 채울 것):
{"intent": "search", "folder_name": null}"""


async def _llm(
    messages: list,
    model: str = "gpt-4o-mini",
    max_tokens: int = 500,
    json_mode: bool = False,
) -> str:
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    client = get_client()
    response = await client.post(
        OPENAI_API_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


# ── 의도 감지 ─────────────────────────────────────────────────────────────────

async def _detect_intent(query: str, history: list[dict]) -> dict:
    """Fix 4: 히스토리를 함께 전달해 맥락 기반 의도 분류"""
    try:
        messages = [
            {"role": "system", "content": INTENT_PROMPT},
            *history[-4:],          # 최근 4개 메시지만 전달
            {"role": "user", "content": query},
        ]
        raw = await _llm(messages, model="gpt-4o-mini", max_tokens=80, json_mode=True)
        return json.loads(raw)
    except Exception:
        return {"intent": "general", "folder_name": None}


# ── 쿼리 보강 & 유도질문 ──────────────────────────────────────────────────────

async def _enrich_query(query: str, history: list[dict]) -> str:
    """이전 대화를 바탕으로 검색 쿼리 구체화"""
    try:
        raw = await _llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "이전 대화와 현재 질문을 종합해, 사용자가 찾는 콘텐츠를 가장 잘 표현하는 "
                        "검색 쿼리를 한 문장으로 만드세요. 주제·플랫폼·키워드를 최대한 포함하세요. "
                        "반드시 JSON만 응답: {\"query\": \"...\"}"
                    ),
                },
                *history[-6:],
                {"role": "user", "content": query},
            ],
            model="gpt-4o-mini",
            max_tokens=120,
            json_mode=True,
        )
        return json.loads(raw).get("query", query)
    except Exception:
        return query


async def _expand_multilingual(query: str) -> str:
    """한국어↔영어 고유명사 병기로 쿼리 확장.

    DB에 영어로 저장된 콘텐츠를 한국어로 검색하거나 그 반대일 때
    임베딩 유사도가 낮아지는 문제를 방지합니다.
    예) '뮤직뱅크 영상' → '뮤직뱅크 music bank 영상'
    """
    try:
        raw = await _llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "검색 쿼리에 포함된 고유명사·프로그램명·브랜드명·플랫폼명을 "
                        "한국어면 영어로, 영어면 한국어로 바로 뒤에 병기해 쿼리를 확장하세요. "
                        "일반 동사·조사·부사는 건드리지 마세요. "
                        "예시:\n"
                        "  입력: '뮤직뱅크 영상 찾아줘'\n"
                        "  출력: {\"query\": \"뮤직뱅크 music bank 영상\"}\n"
                        "  입력: 'show music core 무대'\n"
                        "  출력: {\"query\": \"show music core 쇼! 음악중심 무대\"}\n"
                        "  입력: '유튜브에서 저장한 파이썬 강의'\n"
                        "  출력: {\"query\": \"유튜브 youtube 파이썬 python 강의\"}\n"
                        "반드시 JSON만 응답: {\"query\": \"...\"}"
                    ),
                },
                {"role": "user", "content": query},
            ],
            model="gpt-4o-mini",
            max_tokens=150,
            json_mode=True,
        )
        return json.loads(raw).get("query", query)
    except Exception:
        return query


async def _generate_contextual_followup(query: str, history: list[dict]) -> str:
    """히스토리를 참고해 범위를 좁히는 유도 질문 생성"""
    try:
        return await _llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "저장된 콘텐츠에서 해당 내용을 찾지 못했습니다. "
                        "이전 대화를 참고해 정답을 좁힐 수 있는 유도 질문을 친근하게 1~2개 해주세요. "
                        "예) 플랫폼(유튜브/블로그/뉴스), 주제, 저장 시기, 제목 키워드 등. "
                        "한국어로. 2~3문장."
                    ),
                },
                *history[-6:],
                {"role": "user", "content": query},
            ],
            model="gpt-4o",
            max_tokens=200,
        )
    except Exception:
        return "저장된 콘텐츠 중에서는 찾지 못했어요. 제목에 포함된 단어나 저장했던 시기를 알려주시면 더 잘 찾을 수 있어요!"


# ── 검색 결과 포맷 ────────────────────────────────────────────────────────────

def _format_result(r: dict, rank: int) -> dict:
    """Fix 2: 썸네일·제목·해시태그를 포함한 카드 형식으로 변환"""
    return {
        "rank": rank,
        "id": r.get("id", ""),
        "title": r.get("title", ""),
        "thumbnail_url": r.get("thumbnail_url", ""),
        "hashtags": r.get("hashtags", []),
        "one_line_summary": r.get("one_line_summary", r.get("description", "")),
        "url": r.get("url", ""),
        "platform": r.get("content_type", ""),
        "similarity": round(r.get("similarity", 0), 2),
    }


# ── 핸들러 ────────────────────────────────────────────────────────────────────

async def _handle_search(user_id: str, query: str, history: list[dict], shown_ids: list[str]) -> dict:
    """히스토리 기반 쿼리 보강 → 한영 병기 확장 → 검색(이미 보여준 항목 제외) → 카드형 결과 반환."""
    enriched_query = await _enrich_query(query, history) if history else query
    enriched_query = await _expand_multilingual(enriched_query)   # 한영 고유명사 병기

    embedding = await generate_embedding(enriched_query)
    if not embedding:
        return {"answer": "검색 처리 중 문제가 생겼어요. 다시 시도해주세요.", "results": []}

    results = await search_contents(user_id, embedding, limit=3, exclude_ids=shown_ids)

    if not results:
        answer = await _generate_contextual_followup(query, history)
        return {"answer": answer, "results": []}

    formatted = [_format_result(r, i + 1) for i, r in enumerate(results)]

    context = "\n".join([
        f"{i+1}. [{r.get('platform','')}] {r.get('title','제목 없음')} — {r.get('one_line_summary', r.get('description',''))}"
        for i, r in enumerate(results)
    ])
    answer = await _llm(
        messages=[
            {
                "role": "system",
                "content": (
                    "아래 제공된 후보 목록에 있는 것만 소개하세요. "
                    "목록에 없는 콘텐츠는 절대 언급하지 마세요. "
                    "번호는 목록 그대로(1, 2, 3) 사용하세요. "
                    "각 항목을 한 줄씩 간략히 소개하세요. 한국어로."
                ),
            },
            {"role": "user", "content": f"검색어: {query}\n\n후보:\n{context}"},
        ],
        model="gpt-4o",
        max_tokens=250,
    )
    # 확인 질문 항상 추가
    answer += "\n\n이 중에 찾으시는 콘텐츠가 있나요?"

    return {"answer": answer, "results": formatted}


async def _handle_refine(user_id: str, query: str, history: list[dict], shown_ids: list[str]) -> dict:
    """이전 결과가 틀렸을 때 히스토리 기반 재검색 — 이전에 보여준 항목은 제외."""
    enriched_query = await _enrich_query(query, history)
    enriched_query = await _expand_multilingual(enriched_query)   # 한영 고유명사 병기
    embedding = await generate_embedding(enriched_query)

    if not embedding:
        answer = await _generate_contextual_followup(query, history)
        return {"answer": answer, "results": []}

    # 낮은 threshold로 넓게 검색, 이미 보여준 항목 제외
    results = await search_contents(user_id, embedding, limit=3, threshold=0.2, exclude_ids=shown_ids)

    if not results:
        answer = await _generate_contextual_followup(query, history)
        return {"answer": answer, "results": []}

    formatted = [_format_result(r, i + 1) for i, r in enumerate(results)]
    context = "\n".join([
        f"{i+1}. {r.get('title','제목 없음')} — {r.get('one_line_summary','')}"
        for i, r in enumerate(results)
    ])
    answer = await _llm(
        messages=[
            {
                "role": "system",
                "content": (
                    "아래 제공된 새 후보 목록에 있는 것만 소개하세요. "
                    "목록에 없는 콘텐츠는 절대 언급하지 마세요. "
                    "번호는 1번부터 시작해서 목록 순서 그대로 사용하세요. "
                    "각 항목을 한 줄씩 간략히 소개하세요. 한국어로."
                ),
            },
            {"role": "user", "content": context},
        ],
        model="gpt-4o",
        max_tokens=200,
    )
    answer += "\n\n이 중에 찾으시는 콘텐츠가 있나요?"
    return {"answer": answer, "results": formatted}


async def _handle_deadline(user_id: str) -> dict:
    deadlines = await fetch_deadlines(user_id)
    today = datetime.now(timezone.utc).date().isoformat()

    upcoming = [d for d in deadlines if d.get("deadline_date", "9999") >= today]
    expired  = [d for d in deadlines if d.get("deadline_date", "9999") < today]

    if not upcoming and not expired:
        return {"answer": "마감기한이 있는 콘텐츠가 없어요.", "results": []}

    context_parts = []
    if upcoming:
        context_parts.append("[ 다가오는 마감 ]")
        context_parts += [
            f"- {d.get('title', '')}: {d.get('deadline_date', '')} ({d.get('deadline_note', '')})"
            for d in upcoming[:5]
        ]
    if expired:
        context_parts.append("\n[ 이미 만료된 마감 ]")
        context_parts += [
            f"- {d.get('title', '')}: {d.get('deadline_date', '')} ({d.get('deadline_note', '')})"
            for d in expired[:3]
        ]

    answer = await _llm(
        messages=[
            {
                "role": "system",
                "content": (
                    "사용자의 마감기한 목록입니다. 임박한 것을 먼저 강조하고, "
                    "만료된 것은 정리를 권유하세요. 친근하게. 한국어로. 3~4문장."
                ),
            },
            {"role": "user", "content": "\n".join(context_parts)},
        ],
        model="gpt-4o",
        max_tokens=220,
    )
    return {"answer": answer, "results": upcoming[:5], "expired": expired[:3]}


async def _handle_folder(user_id: str, folder_name: str) -> dict:
    """유사 폴더 감지 → 확인 요청"""
    collections = await get_collections(user_id)
    existing_names = [c["name"] for c in collections]

    matched = _fuzzy_match(folder_name, existing_names)

    if matched and matched != folder_name:
        return {
            "answer": f"혹시 '{matched}' 폴더를 말씀하시는 건가요? 아니면 '{folder_name}'(으)로 새로 만들까요?",
            "needs_confirmation": True,
            "confirmation_data": {"suggested_folder": matched, "new_folder_name": folder_name},
            "results": [],
        }
    if folder_name in existing_names:
        return {"answer": f"'{folder_name}' 폴더에 저장할게요.", "needs_confirmation": False, "results": []}

    return {
        "answer": f"'{folder_name}' 폴더가 없어요. 새로 만들까요?",
        "needs_confirmation": True,
        "confirmation_data": {"suggested_folder": None, "new_folder_name": folder_name},
        "results": [],
    }


async def _handle_cleanup(user_id: str) -> dict:
    deadlines = await fetch_deadlines(user_id)
    today = datetime.now(timezone.utc).date().isoformat()
    expired = [d for d in deadlines if d.get("deadline_date", "9999") < today]

    if not expired:
        return {"answer": "만료된 마감기한 콘텐츠가 없어요. 저장 목록이 깔끔하네요!", "results": []}

    context = "\n".join([
        f"- {d.get('title', '')}: {d.get('deadline_date', '')} 만료"
        for d in expired
    ])
    answer = await _llm(
        messages=[
            {"role": "system", "content": "마감이 지난 콘텐츠 목록입니다. 사용자에게 정리를 권유하세요. 친근하게. 한국어로."},
            {"role": "user", "content": context},
        ],
        model="gpt-4o",
        max_tokens=150,
    )
    return {"answer": answer, "results": expired, "action": "cleanup_suggested"}


def _fuzzy_match(name: str, candidates: list[str], threshold: float = 0.75) -> str | None:
    name_norm = name.replace(" ", "").lower()
    best_ratio, best_match = 0.0, None
    for c in candidates:
        ratio = SequenceMatcher(None, name_norm, c.replace(" ", "").lower()).ratio()
        if ratio > best_ratio:
            best_ratio, best_match = ratio, c
    return best_match if best_ratio >= threshold else None


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

MAX_SEARCH_ATTEMPTS = 3   # 최대 검색 시도 횟수

# 버튼에 표시할 선택지 — show_confirmation=True 일 때 응답에 포함
_CONFIRMATION_OPTIONS = [
    {"label": "있어요 ✅", "action": "found"},
    {"label": "없어요 ❌", "action": "refine"},
]


async def process_chat(
    user_id: str,
    query: str,
    history: list[dict] | None = None,
    search_attempt: int = 0,
    shown_ids: list[str] | None = None,
    action: str | None = None,
) -> dict:
    """
    대화 흐름 상태 관리 포함 메인 진입점.
    - action         : 버튼 클릭 시 직접 전달 ("found" | "refine") — 있으면 LLM 의도 분류 생략
    - search_attempt : 지금까지 몇 번 검색했는지 (클라이언트가 유지해서 전달)
    - shown_ids      : 지금까지 사용자에게 보여준 콘텐츠 ID 목록
    응답에 search_attempt, shown_ids, session_ended, show_confirmation, confirmation_options 포함.
    """
    # 가변 기본값 대신 None → 빈 리스트로 안전하게 처리
    history = history or []
    shown_ids = shown_ids or []

    # action이 있으면 LLM 분류 생략 — 버튼 클릭은 확정값이므로 오분류 없음
    if action in ("found", "refine"):
        intent = action
        folder_name = None
    else:
        intent_data = await _detect_intent(query, history)
        intent = intent_data.get("intent", "general")
        folder_name = intent_data.get("folder_name")

    # ── 찾았다고 확인 → 이전 후보 목록과 함께 대화 종료 ──────────────────────
    if intent == "found":
        # shown_ids에 있던 후보 콘텐츠를 다시 포함해 어떤 항목이 정답이었는지 컨텍스트 유지
        found_results = []
        if shown_ids:
            contents_map = await get_contents_by_ids(shown_ids)
            found_results = [
                {
                    "id": cid,
                    "title": contents_map[cid].get("title", ""),
                    "thumbnail_url": contents_map[cid].get("thumbnail_url", ""),
                    "hashtags": contents_map[cid].get("hashtags", []),
                    "one_line_summary": contents_map[cid].get("one_line_summary", ""),
                    "url": contents_map[cid].get("url", ""),
                    "platform": contents_map[cid].get("content_type", ""),
                }
                for cid in shown_ids
                if cid in contents_map
            ]
        return {
            "answer": "찾으셨군요! 즐겁게 감상하세요 😊",
            "results": found_results,
            "intent": "found",
            "search_attempt": search_attempt,
            "shown_ids": shown_ids,
            "session_ended": True,
            "show_confirmation": False,
            "confirmation_options": [],
        }

    # ── 검색 (새 질문) → 상태 리셋 후 검색 ───────────────────────────────────
    if intent in ("search", "general"):
        search_attempt = 0
        shown_ids = []
        result = await _handle_search(user_id, query, history, shown_ids)
        new_shown_ids = shown_ids + [r["id"] for r in result.get("results", [])]
        has_results = len(result.get("results", [])) > 0
        result.update({
            "intent": intent,
            "search_attempt": 1,
            "shown_ids": new_shown_ids,
            "session_ended": False,
            "show_confirmation": has_results,
            "confirmation_options": _CONFIRMATION_OPTIONS if has_results else [],
        })
        return result

    # ── 재검색 (이어서 하는 질문) ──────────────────────────────────────────────
    if intent == "refine":
        # 최대 시도 횟수 초과 → 포기 메시지
        if search_attempt >= MAX_SEARCH_ATTEMPTS:
            return {
                "answer": (
                    "열심히 찾아봤지만 저장된 콘텐츠 중에서는 찾기 어렵네요 😅\n"
                    "제목에 포함된 단어나 저장했던 시기가 기억나신다면 새로 검색해보세요!"
                ),
                "results": [],
                "intent": "refine",
                "search_attempt": search_attempt,
                "shown_ids": shown_ids,
                "session_ended": True,
                "show_confirmation": False,
                "confirmation_options": [],
            }
        result = await _handle_refine(user_id, query, history, shown_ids)
        new_shown_ids = shown_ids + [r["id"] for r in result.get("results", [])]
        has_results = len(result.get("results", [])) > 0
        result.update({
            "intent": intent,
            "search_attempt": search_attempt + 1,
            "shown_ids": new_shown_ids,
            "session_ended": False,
            "show_confirmation": has_results,
            "confirmation_options": _CONFIRMATION_OPTIONS if has_results else [],
        })
        return result

    # ── 그 외 (deadline / folder / cleanup) — 검색 상태 유지 ─────────────────
    if intent == "deadline":
        result = await _handle_deadline(user_id)
    elif intent == "folder" and folder_name:
        result = await _handle_folder(user_id, folder_name)
    elif intent == "cleanup":
        result = await _handle_cleanup(user_id)
    else:
        result = {"answer": "무엇을 도와드릴까요?", "results": []}

    result.update({
        "intent": intent,
        "search_attempt": search_attempt,
        "shown_ids": shown_ids,
        "session_ended": False,
        "show_confirmation": False,
        "confirmation_options": [],
    })
    return result
