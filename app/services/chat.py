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
    update_deadline,
    get_collection_items,
    get_contents_by_ids,
    get_all_subcategories,
    get_contents_by_subcategory,
    get_all_categories,
    get_contents_by_category,
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

INTENT_PROMPT = """사용자 메시지와 대화 맥락을 보고 의도를 분류하세요. 반드시 JSON만 응답.

의도 종류:
- search   : 저장한 콘텐츠를 찾거나 검색하는 요청 (이전 검색의 후속 답변 포함)
- deadline : 마감기한 관련 질문 ("마감 언제야", "임박한 거 뭐야" 등)
- folder   : 폴더 생성·지정·관리 ("이 링크 OO 폴더에 넣어줘" 등)
- move     : 콘텐츠를 다른 폴더로 이동. "옮기고 싶음", "이동", "옮겨줘" 포함.
             목적지가 없거나 "다른 폴더", "다른 곳", "어딘가"처럼 불특정이면 target_folder=null
- cleanup  : 오래된·만료된 콘텐츠 정리 또는 리마인드 요청
- delete   : 특정 콘텐츠 삭제 요청 ("OO 삭제해줘", "이거 지워줘" 등)
- deadline_edit : 방금 저장한 콘텐츠의 마감기한 정정
- merge    : 같은 이름의 소분류/카테고리가 여러 대분류에 흩어져 있을 때 하나로 합치기.
             "합치다", "합쳐줘", "통합", "하나로", "합쳐", "묶어" 등 포함.
- general  : 그 외

중요 규칙:
- "OO에 있는 링크 다른 폴더로 옮기고 싶음" → intent="move", source_folder="OO", target_folder=null
- "OO 폴더에서 PP 폴더로 옮겨줘" → intent="move", source_folder="OO", target_folder="PP"
- "주식 둘이 합치고 싶어" / "주식 합쳐줘" → intent="merge", merge_target="주식"
- source_folder는 현재 메시지에서 "~에서", "~에 있는" 형태로 출처를 명시한 경우만 추출. 조사(에, 에서, 의 등)는 제외하고 이름만.
- target_folder는 구체적인 폴더명이 없으면 반드시 null.
- merge_target: 합칠 대상 이름 (예: "주식")

응답 형식:
{"intent": "search", "folder_name": null, "delete_query": null, "source_folder": null, "move_query": null, "target_folder": null, "merge_target": null, "second_intent": null, "second_query": null}

folder_name: 폴더 의도일 때만 생성할 폴더명
delete_query: 삭제 의도일 때 삭제 대상 키워드 (예: "딥러닝")
source_folder: 출처 폴더명 (조사 제외, 예: "노래", "음악")
move_query: 이동 의도일 때 이동할 콘텐츠 키워드
target_folder: 구체적인 이동 목적지 폴더명 (불특정이면 null)
merge_target: 합칠 대상 이름 (예: "주식")
second_intent: 두 번째 의도, 없으면 null
second_query: 두 번째 요청 키워드, 없으면 null
deadline_edit_type: "remove" 또는 "update"
deadline_edit_date: YYYY-MM-DD
deadline_edit_note: 마감 설명"""


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


# 긴 것 먼저 — "에서"를 먼저 제거해야 "에"가 남지 않음
_KO_PARTICLES = ["에게서", "으로부터", "로부터", "에서", "에게", "으로", "로", "이랑", "에", "의", "을", "를", "과", "와", "랑", "도", "이", "가", "는", "은"]

def _strip_particles(name: str) -> str:
    name = name.strip()
    for p in _KO_PARTICLES:
        if name.endswith(p) and len(name) > len(p):
            return name[:-len(p)].strip()
    return name

def _best_match(name: str, candidates: list[str]) -> tuple[str | None, float]:
    """가장 유사한 후보와 유사도 점수 반환 (임계값 없음)"""
    if not candidates:
        return None, 0.0
    name_norm = name.replace(" ", "").lower()
    best_ratio, best_match = 0.0, None
    for c in candidates:
        ratio = SequenceMatcher(None, name_norm, c.replace(" ", "").lower()).ratio()
        if ratio > best_ratio:
            best_ratio, best_match = ratio, c
    return best_match, best_ratio

def _fuzzy_match(name: str, candidates: list[str], threshold: float = 0.75) -> str | None:
    best, ratio = _best_match(name, candidates)
    return best if ratio >= threshold else None


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


_CONTEXTUAL_REFS = ["그거", "이거", "저거", "방금", "그것", "이것", "맞아", "그 거", "이 거", "그 링크", "이 링크", "그링크", "그걸", "이걸"]

async def _llm_pick_folder(query: str, candidates: list[str]) -> str | None:
    """영어↔한글 등 퍼지 매칭 실패 시 LLM이 목록에서 골라줌"""
    if not candidates:
        return None
    try:
        raw = await _llm(
            [{"role": "system", "content":
                f"아래 폴더 목록 중 사용자가 찾는 것과 가장 일치하는 이름 하나만 정확히 반환해. "
                f"일치하는 게 없으면 'none'만 반환해.\n목록: {candidates}"},
             {"role": "user", "content": query}],
            model="gpt-4o-mini", max_tokens=40,
        )
        pick = raw.strip().strip('"').strip("'")
        return pick if pick in candidates else None
    except Exception:
        return None


def _items_to_results(items: list[dict]) -> list[dict]:
    return [{"id": r["id"], "title": r["title"], "url": r["url"],
             "one_line_summary": r.get("one_line_summary", ""),
             "thumbnail_url": r.get("thumbnail_url", ""), "similarity": 1.0}
            for r in items]


async def _handle_folder_search(user_id: str, source_folder: str, extra_query: str = "", shown_ids: list[str] = []) -> dict:
    """컬렉션 → 소분류 → 대분류 → LLM 4단계로 폴더 찾아 콘텐츠 반환.
    extra_query가 있으면 폴더 내에서 벡터 검색으로 좁힘."""
    clean = _strip_particles(source_folder)

    items: list[dict] = []
    found_label: str = ""

    # 1단계: 사용자 컬렉션
    collections = await get_collections(user_id)
    col_names = [c["name"] for c in collections]
    best_col, col_ratio = _best_match(clean, col_names)
    if col_ratio >= 0.45 and best_col:
        col = next((c for c in collections if c["name"] == best_col), None)
        if col:
            items = await get_collection_items(user_id, col["id"])
            found_label = best_col

    # 2단계: AI 소분류
    if not items:
        subcats = await get_all_subcategories(user_id)
        best_sub, sub_ratio = _best_match(clean, subcats)
        if sub_ratio >= 0.45 and best_sub:
            items = await get_contents_by_subcategory(user_id, best_sub)
            found_label = best_sub

    # 3단계: AI 대분류 (음악, IT/기술 등)
    if not items:
        cats = await get_all_categories(user_id)
        best_cat, cat_ratio = _best_match(clean, cats)
        if cat_ratio >= 0.45 and best_cat:
            items = await get_contents_by_category(user_id, best_cat)
            found_label = best_cat

    # 4단계: LLM (영어↔한글 등)
    if not items:
        if 'subcats' not in locals():
            subcats = await get_all_subcategories(user_id)
        if 'cats' not in locals():
            cats = await get_all_categories(user_id)
        all_names = col_names + subcats + cats
        llm_pick = await _llm_pick_folder(clean, all_names)
        if llm_pick:
            if llm_pick in col_names:
                col = next((c for c in collections if c["name"] == llm_pick), None)
                items = await get_collection_items(user_id, col["id"]) if col else []
            elif llm_pick in cats:
                items = await get_contents_by_category(user_id, llm_pick)
            else:
                items = await get_contents_by_subcategory(user_id, llm_pick)
            found_label = llm_pick

    if not items:
        return {"answer": f"'{clean}' 폴더를 찾지 못했어요. 폴더 이름을 다시 확인해주세요.", "results": []}

    # 이미 보여준 항목 제외
    shown_set = set(shown_ids)
    unseen = [r for r in items if r.get("id") not in shown_set]
    pool = unseen if unseen else items  # 전부 봤으면 전체 허용

    # 추가 검색어가 있으면 폴더 내에서 벡터 검색으로 좁히기
    if extra_query and extra_query.strip():
        pool_ids = {r["id"] for r in pool}
        expanded = await expand_query(extra_query)
        embedding = await generate_embedding(expanded)
        if embedding:
            raw = await search_contents(user_id, embedding, limit=30, threshold=0.2)
            narrowed = [r for r in raw if r.get("id") in pool_ids]
            if narrowed:
                results = _items_to_results(narrowed[:5])
                suffix = " (이전에 보여준 것 제외)" if unseen else ""
                return {"answer": f"'{found_label}'에서 관련 콘텐츠 {len(results)}개 찾았어요{suffix}. 이거 맞나요?",
                        "results": results, "follow_up_questions": ["맞아요", "아니요, 다른 거예요"]}

    results = _items_to_results(pool[:10])
    suffix = f" (이전에 보여준 것 제외, {len(items) - len(unseen)}개 제외)" if shown_set and unseen else ""
    return {"answer": f"'{found_label}'에 콘텐츠 {len(results)}개가 있어요{suffix}.",
            "results": results, "follow_up_questions": []}


async def _resolve_folder_items(user_id: str, source_folder: str | None, shown_ids: list[str]) -> tuple[list[dict], str]:
    """source_folder 또는 shown_ids로 이동 대상 콘텐츠 찾기. (items, found_name) 반환"""
    if shown_ids and not source_folder:
        items = await get_contents_by_ids(user_id, list(shown_ids))
        return items, "이전에 찾은 콘텐츠"

    if source_folder:
        collections = await get_collections(user_id)
        col_names = [c["name"] for c in collections]
        clean = _strip_particles(source_folder)

        best_col, col_ratio = _best_match(clean, col_names)
        if col_ratio >= 0.45 and best_col:
            col = next((c for c in collections if c["name"] == best_col), None)
            if col:
                items = await get_collection_items(user_id, col["id"])
                return items, best_col

        subcats = await get_all_subcategories(user_id)
        best_sub, sub_ratio = _best_match(clean, subcats)
        if sub_ratio >= 0.45 and best_sub:
            items = await get_contents_by_subcategory(user_id, best_sub)
            return items, best_sub

        cats = await get_all_categories(user_id)
        best_cat, cat_ratio = _best_match(clean, cats)
        if cat_ratio >= 0.45 and best_cat:
            items = await get_contents_by_category(user_id, best_cat)
            return items, best_cat

        all_names = col_names + subcats + cats
        llm_pick = await _llm_pick_folder(clean, all_names) if all_names else None
        if llm_pick:
            if llm_pick in col_names:
                col = next((c for c in collections if c["name"] == llm_pick), None)
                items = await get_collection_items(user_id, col["id"]) if col else []
            elif llm_pick in cats:
                items = await get_contents_by_category(user_id, llm_pick)
            else:
                items = await get_contents_by_subcategory(user_id, llm_pick)
            return items, llm_pick

    return [], source_folder or ""


async def _handle_move_no_target(user_id: str, source_folder: str | None, shown_ids: list[str]) -> dict:
    """target 폴더 미지정 → 아이템 찾고 폴더 선택 UI 반환"""
    items, found_name = await _resolve_folder_items(user_id, source_folder, shown_ids)
    if not items:
        label = source_folder or "이전 검색"
        return {"answer": f"'{label}'에서 이동할 콘텐츠를 찾지 못했어요.", "results": []}

    results = [{"id": r["id"], "title": r["title"], "url": r["url"],
                "one_line_summary": r.get("one_line_summary", ""),
                "thumbnail_url": r.get("thumbnail_url", ""), "similarity": 1.0}
               for r in items]
    return {
        "answer": f"'{found_name}'의 콘텐츠 {len(results)}개를 어느 폴더로 옮길까요?",
        "needs_folder_pick": True,
        "pending_move_ids": [r["id"] for r in results],
        "results": results,
        "follow_up_questions": [],
    }


async def _handle_merge(user_id: str, merge_target: str) -> dict:
    """여러 대분류에 흩어진 같은 소분류명 콘텐츠를 하나의 컬렉션으로 합치기"""
    clean = _strip_particles(merge_target)

    # 소분류에서 찾기
    items = await get_contents_by_subcategory(user_id, clean)

    # 퍼지 매칭 시도
    if not items:
        subcats = await get_all_subcategories(user_id)
        best, ratio = _best_match(clean, subcats)
        if ratio >= 0.45 and best:
            items = await get_contents_by_subcategory(user_id, best)
            clean = best

    if not items:
        return {"answer": f"'{clean}' 관련 콘텐츠를 찾지 못했어요.", "results": []}

    results = [{"id": r["id"], "title": r["title"], "url": r["url"],
                "one_line_summary": r.get("one_line_summary", ""),
                "thumbnail_url": r.get("thumbnail_url", ""), "similarity": 1.0}
               for r in items]
    titles = "\n".join([f"- {r.get('title', '제목 없음')}" for r in items])
    return {
        "answer": f"여러 분류에 흩어진 '{clean}' 콘텐츠 {len(items)}개를 찾았어요:\n{titles}\n\n이 항목들을 '{clean}' 폴더 하나로 합칠까요?",
        "needs_confirmation": True,
        "pending_move_ids": [r["id"] for r in items],
        "target_folder": clean,
        "results": results,
    }


async def _handle_move(user_id: str, move_query: str, target_folder: str, source_folder: str | None = None, shown_ids: list[str] = []) -> dict:
    collections = await get_collections(user_id)
    existing_names = [c["name"] for c in collections]

    # target 폴더: 조사 제거 → 컬렉션 퍼지 → 소분류 퍼지 → LLM 순으로 해석
    clean_target = _strip_particles(target_folder)
    best_tgt, tgt_ratio = _best_match(clean_target, existing_names)
    if tgt_ratio >= 0.45 and best_tgt:
        matched_folder = best_tgt
    else:
        subcats = await get_all_subcategories(user_id)
        best_sub, sub_ratio = _best_match(clean_target, subcats)
        if sub_ratio >= 0.45 and best_sub:
            matched_folder = best_sub
        else:
            all_names = existing_names + subcats
            llm_pick = await _llm_pick_folder(clean_target, all_names) if all_names else None
            matched_folder = llm_pick if llm_pick else clean_target

    # shown_ids 우선: 맥락적 참조("그거", "그 링크" 등)면 source_folder보다 먼저 처리
    is_contextual = (
        not move_query
        or any(ref in move_query for ref in _CONTEXTUAL_REFS)
        or len(move_query.replace(" ", "")) <= 5
    )
    if shown_ids and is_contextual:
        results = await get_contents_by_ids(user_id, list(shown_ids))
        if results:
            titles = "\n".join([f"- {r.get('title', '제목 없음')}" for r in results])
            return {
                "answer": f"이전에 찾은 콘텐츠 {len(results)}개를 '{matched_folder}' 폴더로 이동할까요?\n{titles}",
                "needs_confirmation": True,
                "pending_move_ids": [r["id"] for r in results],
                "target_folder": matched_folder,
                "results": results,
            }

    # source_folder 명시된 경우 → 해당 폴더 전체 아이템 이동 (컬렉션→소분류→대분류 순)
    if source_folder:
        src_items, src_label = await _resolve_folder_items(user_id, source_folder, [])
        if not src_items:
            clean_source = _strip_particles(source_folder)
            return {"answer": f"'{clean_source}' 폴더를 찾지 못했어요.", "results": []}
        titles = "\n".join([f"- {r.get('title', '제목 없음')}" for r in src_items])
        return {
            "answer": f"'{src_label}' 폴더의 콘텐츠 {len(src_items)}개를 '{matched_folder}' 폴더로 이동할까요?\n{titles}",
            "needs_confirmation": True,
            "pending_move_ids": [r["id"] for r in src_items],
            "target_folder": matched_folder,
            "results": src_items,
        }

    # 키워드 벡터 검색 + LLM 필터
    expanded = await expand_query(move_query)
    embedding = await generate_embedding(expanded)
    if not embedding:
        return {"answer": "이동할 콘텐츠를 찾지 못했어요.", "results": []}

    raw = await search_contents(user_id, embedding, limit=10)
    results = await _filter_results(move_query, raw)
    results = results[:5]
    if not results:
        return {"answer": f"'{move_query}' 관련 콘텐츠를 찾지 못했어요.", "results": []}

    titles = "\n".join([f"- {r.get('title', '제목 없음')}" for r in results])
    return {
        "answer": f"'{move_query}' 관련 콘텐츠 {len(results)}개를 찾았어요:\n{titles}\n\n'{matched_folder}' 폴더로 이동할까요?",
        "needs_confirmation": True,
        "pending_move_ids": [r["id"] for r in results],
        "target_folder": matched_folder,
        "results": results,
    }


async def _handle_deadline_edit(user_id: str, content_id: str, edit_type: str, deadline_date: str | None, deadline_note: str | None) -> dict:
    if edit_type == "remove":
        success = await update_deadline(content_id, user_id, False, None, None)
        if success:
            return {"answer": "마감기한을 삭제했어요.", "results": []}
        return {"answer": "수정에 실패했어요. 다시 시도해주세요.", "results": []}

    if edit_type == "update" and deadline_date:
        note = deadline_note or f"마감 {deadline_date[5:]}"
        success = await update_deadline(content_id, user_id, True, deadline_date, note)
        if success:
            return {"answer": f"마감기한을 '{note}'으로 수정했어요.", "results": []}
        return {"answer": "수정에 실패했어요. 다시 시도해주세요.", "results": []}

    return {"answer": "마감일을 어떻게 바꿔드릴까요? '마감 없어' 또는 '7월 15일이야'처럼 말해주세요.", "results": []}


async def _handle_delete(user_id: str, delete_query: str, source_folder: str | None = None) -> dict:
    # 출처 폴더가 지정된 경우 해당 폴더 내에서만 검색
    if source_folder:
        collections = await get_collections(user_id)
        existing_names = [c["name"] for c in collections]
        clean_sf = _strip_particles(source_folder)
        best_sf, sf_ratio = _best_match(clean_sf, existing_names)
        matched_folder = best_sf if sf_ratio >= 0.45 else None
        if matched_folder:
            col = next(c for c in collections if c["name"] == matched_folder)
            folder_items = await get_collection_items(user_id, col["id"])
            # 키워드 매칭으로 필터링
            kw = delete_query.lower().replace(" ", "")
            results = [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "url": r["url"],
                    "one_line_summary": r.get("one_line_summary", ""),
                    "thumbnail_url": r.get("thumbnail_url", ""),
                    "similarity": 1.0,
                }
                for r in folder_items
                if kw in r.get("title", "").lower().replace(" ", "")
                or kw in r.get("one_line_summary", "").lower().replace(" ", "")
            ]
            if results:
                titles = "\n".join([f"- {r['title']}" for r in results])
                return {
                    "answer": f"'{matched_folder}' 폴더에서 '{delete_query}' 관련 {len(results)}개를 찾았어요:\n{titles}\n\n삭제할까요?",
                    "needs_confirmation": True,
                    "pending_delete_ids": [r["id"] for r in results],
                    "results": results,
                }
            # 폴더 내 없으면 전체 검색으로 폴백
            return {"answer": f"'{matched_folder}' 폴더에서 '{delete_query}' 관련 콘텐츠를 찾지 못했어요.", "results": []}

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

async def process_chat(user_id: str, query: str, history: list[dict[str, Any]] = [], shown_ids: list[str] = [], content_id: str | None = None) -> dict:
    """의도 파악 후 적절한 핸들러 호출. history로 대화 맥락 유지."""
    intent_data = await _detect_intent(query, history)
    intent = intent_data.get("intent", "general")
    folder_name = intent_data.get("folder_name")
    delete_query = intent_data.get("delete_query")
    source_folder = intent_data.get("source_folder")
    move_query = intent_data.get("move_query")
    target_folder = intent_data.get("target_folder")
    merge_target = intent_data.get("merge_target")
    deadline_edit_type = intent_data.get("deadline_edit_type")
    deadline_edit_date = intent_data.get("deadline_edit_date")
    deadline_edit_note = intent_data.get("deadline_edit_note")
    second_intent = intent_data.get("second_intent")
    second_query = intent_data.get("second_query")

    if intent == "deadline_edit" and content_id:
        result = await _handle_deadline_edit(user_id, content_id, deadline_edit_type or "", deadline_edit_date, deadline_edit_note)
    elif intent == "search":
        if source_folder:
            result = await _handle_folder_search(user_id, source_folder, extra_query=query, shown_ids=shown_ids)
        else:
            result = await _handle_search(user_id, query, history, shown_ids)
    elif intent == "deadline":
        result = await _handle_deadline(user_id)
    elif intent == "folder" and folder_name:
        result = await _handle_folder(user_id, folder_name)
    elif intent == "cleanup":
        result = await _handle_cleanup(user_id)
    elif intent == "merge" and merge_target:
        result = await _handle_merge(user_id, merge_target)
    elif intent == "move" and target_folder:
        result = await _handle_move(user_id, move_query or "", target_folder, source_folder, shown_ids)
    elif intent == "move" and (source_folder or shown_ids):
        result = await _handle_move_no_target(user_id, source_folder, shown_ids)
    elif intent == "delete" and delete_query:
        result = await _handle_delete(user_id, delete_query, source_folder)
    else:
        result = await _handle_search(user_id, query, history, shown_ids)

    # 두 번째 요청이 감지된 경우 안내 메시지 추가
    if second_intent and second_query:
        notice = f"\n\n💡 두 번째 요청 ('{second_query}' {second_intent})은 이게 끝난 후 말씀해주시면 처리할게요!"
        result["answer"] = (result.get("answer") or "") + notice

    result["intent"] = intent
    return result
