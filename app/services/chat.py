# app/services/chat.py

import os
import httpx
import json
import random
from difflib import SequenceMatcher
from datetime import datetime, timezone

from app.services.embedding import generate_embedding
from app.services.query_expander import expand_query
from app.services.database import (
    search_contents,
    get_deadlines,
    get_old_contents,
    get_or_create_collection,
    move_content_collection,
    get_recent_contents,
    get_contents_by_ids,
    get_collections,
    get_collection_contents,
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

INTENT_PROMPT = """너는 Keepit(개인 콘텐츠 아카이브) 비서야. 사용자 메시지의 의도를 분류해. 반드시 JSON만 응답.
직전 대화 맥락이 있으면 "방금 거", "그중 두번째" 같은 표현을 그 맥락으로 해석해.

의도 종류:
- search    : 저장한 콘텐츠를 찾거나 검색하는 요청 ("OO 찾아줘", "OO 저장한 거 있어?")
- summarize : 저장한 콘텐츠를 요약하거나 설명해 달라는 요청
              ("이거 요약해줘", "방금 저장한 거 설명해줘", "OO 영상 요약해줘", "내용 정리해줘")
- deadline  : 마감기한 관련 질문 ("마감 언제야", "임박한 거 뭐야" 등)
- folder    : 폴더를 새로 만들거나, 특정 주제의 콘텐츠들을 한 폴더로 묶어/모아 달라는 요청
              ("OO 폴더 만들어줘", "OO 콘텐츠들끼리 묶어줘", "OO끼리 묶어줘", "OO 관련된 거 묶어줘", "OO끼리 모아줘")
              → folder_name엔 그 주제(폴더명)를 넣어라. '묶어/모아'는 거의 항상 folder 의도다.
- move      : 이미 있는 특정 폴더로 '옮겨/이동'하는 요청
              ("음악 관련 링크들 노래 폴더로 옮겨줘", "OO 폴더로 이동해줘" — 목적지 폴더명이 분명할 때)
- cleanup   : 오래된·만료된 콘텐츠 정리 또는 리마인드 요청 ("오래된 거 정리해줘", "쌓인 거 뭐 있어")
- delete    : 특정 콘텐츠 삭제 요청 ("OO 관련 삭제해줘", "이거 지워줘" 등)
- general   : 그 외 일반 대화 (인사, 잡담, 서비스 무관 질문 포함)

응답 형식:
{"intent": "search", "folder_name": null, "delete_query": null, "move_query": null, "target_folder": null, "summarize_query": null, "target_collection": null}

folder_name: folder 의도일 때만 폴더명 추출, 없으면 null
delete_query: delete 의도일 때 삭제 대상 키워드 추출 (예: "딥러닝"), 없으면 null
move_query: move 의도일 때 이동할 콘텐츠 주제·키워드 (예: "음악"), 없으면 null
target_folder: move 의도일 때 목적지 폴더명 (예: "노래"), 없으면 null
summarize_query: summarize 의도일 때 대상이 명시되면 주제 추출(예: "딥러닝 영상"), "이거/방금 거"처럼 모호하면 null
target_collection: 사용자가 특정 컬렉션·폴더 안의 콘텐츠를 가리키면 그 컬렉션 이름만 추출
                   (예: "대선 관련 뉴스 컬렉션에 있는 것들 요약해줘" → "대선 관련 뉴스",
                    "OO 폴더 안의 거 요약" → "OO"). '컬렉션/폴더' 단어가 없어도 폴더를 가리키는 맥락이면 추출. 아니면 null"""


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


async def _detect_intent(query: str, history: list = None) -> dict:
    history = history or []
    try:
        messages = [{"role": "system", "content": INTENT_PROMPT}]
        # 직전 맥락 일부 포함 → "방금 거", "그중 두번째" 등 후속 발화 해석
        for h in history[-4:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": str(h["content"])[:300]})
        messages.append({"role": "user", "content": query})

        raw = await _llm(
            messages=messages,
            model="gpt-4o-mini",
            max_tokens=100,
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

    # 후보 15개 → shown_ids 제외 → 전체 필드 보강 → detailed_summary 기반 엄격 필터 → 상위 5개
    candidates = await search_contents(user_id, embedding, limit=15)
    candidates = [r for r in candidates if r.get("id") not in shown_ids]

    results = []
    if candidates:
        ids = [r["id"] for r in candidates]
        full = await get_contents_by_ids(user_id, ids)
        order = {cid: i for i, cid in enumerate(ids)}
        full.sort(key=lambda r: order.get(r.get("id"), 999))
        # 제목만 보던 느슨한 장르 필터 대신, 요약 내용으로 주제에 맞는 것만 선별
        filtered = await _filter_by_topic(query, full)
        results = _to_cards(filtered[:5])

    if not results:
        none_msgs = [
            "저장한 것 중엔 못 찾았어요. 제목이나 키워드를 조금 더 구체적으로 알려주시겠어요?",
            "관련 콘텐츠를 찾지 못했어요. 어떤 주제·단어였는지 알려주시면 다시 찾아볼게요.",
            "아직 그런 콘텐츠는 안 보이네요. 키워드를 바꿔서 다시 말씀해 주실래요?",
        ]
        return {"answer": random.choice(none_msgs), "results": []}

    if len(results) == 1:
        one_msgs = [
            "이거 찾으시는 것 같아요. 맞나요?",
            "이거 어떠세요?",
            "찾았어요! 이거 맞을까요?",
        ]
        return {"answer": random.choice(one_msgs), "results": results}

    multi_msgs = [
        f"관련해서 {len(results)}개 찾았어요.",
        f"{len(results)}개 나왔어요. 한번 보세요.",
        f"이런 게 있네요 — 총 {len(results)}개예요.",
    ]
    return {"answer": random.choice(multi_msgs), "results": results}


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
    """폴더명(주제)에 맞는 콘텐츠를 찾아 '선택/전체 묶기'로 제시 (실제 묶기는 사용자가 결정)."""
    related = await _find_relevant_contents(user_id, folder_name, limit=12)

    if not related:
        # 후보가 없으면 빈 폴더만 생성
        collection_id = await get_or_create_collection(user_id, folder_name)
        return {
            "answer": f"'{folder_name}' 폴더를 만들었어요! 지금은 묶을 만한 관련 콘텐츠를 찾지 못했어요. 관련 링크를 저장하면 채워드릴게요.",
            "results": [],
            "action": "folder_created",
            "collection_id": collection_id,
            "collection_name": folder_name,
        }

    # 후보를 카드로 제시 → 사용자가 선택하거나 전체를 묶는다 (일부만 묶이는 문제 해결)
    msg = random.choice([
        f"'{folder_name}'(으)로 묶을 만한 게 {len(related)}개 있어요. 선택하거나 전체로 묶어보세요.",
        f"이만큼 모였어요! '{folder_name}' 폴더에 담을 걸 골라주세요.",
        f"'{folder_name}' 관련해서 {len(related)}개 찾았어요. 선택 묶기 / 전체 묶기 중에 골라주세요.",
    ])
    return {
        "answer": msg,
        "results": _to_cards(related),
        "action": "folder_select",
        "collection_name": folder_name,
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
    """주제에 맞는 콘텐츠를 정확히 찾아 폴더로 이동 (폴더 없으면 생성)."""
    results = await _find_relevant_contents(user_id, move_query, limit=10)
    if not results:
        return {
            "answer": f"'{move_query}' 관련 저장된 콘텐츠를 찾지 못했어요. 먼저 관련 링크를 저장해보세요.",
            "results": [],
        }

    collection_id = await get_or_create_collection(user_id, target_folder)
    if not collection_id:
        return {"answer": f"'{target_folder}' 폴더를 만드는 데 실패했어요.", "results": []}

    moved_items = []
    for r in results:
        if await move_content_collection(r["id"], user_id, collection_id):
            moved_items.append(r)
    moved = len(moved_items)

    return {
        "answer": random.choice([
            f"'{move_query}' 관련 {moved}개를 '{target_folder}' 폴더로 옮겼어요.",
            f"{moved}개 정리해서 '{target_folder}'에 담아뒀어요.",
            f"'{target_folder}'로 {moved}개 이동 완료!",
        ]),
        "results": _to_cards(moved_items),
        "action": "folder_created",
        "collection_id": collection_id,
        "collection_name": target_folder,
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


# ── 콘텐츠 검색/정규화 공통 헬퍼 ───────────────────────────────────────────────

# 콘텐츠를 프론트 카드 형태로 정규화 (썸네일·요약 포함)
def _to_cards(items: list[dict]) -> list[dict]:
    return [
        {
            "id": r.get("id"),
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "thumbnail": r.get("thumbnail_url") or r.get("thumbnail") or "",
            "summary": r.get("detailed_summary") or r.get("one_line_summary") or r.get("description", ""),
        }
        for r in items
    ]


async def _search_full(user_id: str, topic: str, candidate_limit: int = 15) -> list[dict]:
    """주제로 임베딩 검색 후, 각 후보의 전체 필드(detailed_summary·thumbnail_url 등)를 불러온다."""
    expanded = await expand_query(topic)
    embedding = await generate_embedding(expanded)
    if not embedding:
        return []
    cands = await search_contents(user_id, embedding, limit=candidate_limit)
    if not cands:
        return []
    ids = [c["id"] for c in cands]
    full = await get_contents_by_ids(user_id, ids)
    order = {cid: i for i, cid in enumerate(ids)}
    full.sort(key=lambda r: order.get(r.get("id"), 999))
    return full


async def _filter_by_topic(topic: str, items: list[dict]) -> list[dict]:
    """title + detailed_summary 기준으로 주제에 '명확히' 맞는 항목만 LLM이 선별 (오매칭 제거)."""
    if not items:
        return []
    listing = "\n".join(
        f"[{i}] 제목: {it.get('title', '')}\n    요약: {(it.get('detailed_summary') or it.get('one_line_summary') or '')[:200]}"
        for i, it in enumerate(items)
    )
    try:
        raw = await _llm(
            messages=[{"role": "user", "content": (
                f"주제: '{topic}'\n\n아래 콘텐츠 중 이 주제에 '명확히' 해당하는 것의 번호만 골라줘. "
                f"주제와 무관하면(예: 야구 주제에 축구·정치) 절대 포함하지 마. 요약 내용을 근거로 판단해.\n\n"
                f"{listing}\n\n"
                '반드시 JSON만: {"indices": [번호들]}'
            )}],
            model="gpt-4o-mini",
            max_tokens=150,
            json_mode=True,
        )
        idxs = json.loads(raw).get("indices", [])
        picked = [items[i] for i in idxs if isinstance(i, int) and 0 <= i < len(items)]
        return picked
    except Exception:
        return items


async def _find_relevant_contents(user_id: str, topic: str, limit: int = 10) -> list[dict]:
    """주제에 맞는 콘텐츠를 detailed_summary 기반으로 정확히 찾아 반환 (요약·묶기 공통)."""
    full = await _search_full(user_id, topic, candidate_limit=15)
    filtered = await _filter_by_topic(topic, full)
    return filtered[:limit]


def _match_collection(name: str, collections: list[dict]) -> dict | None:
    """발화 속 폴더명을 실제 컬렉션과 매칭 (공백 무시 정확 매칭 → 유사도 매칭)."""
    if not name or not collections:
        return None
    target = name.replace(" ", "").lower()
    for c in collections:
        if (c.get("name") or "").replace(" ", "").lower() == target:
            return c
    names = [c.get("name", "") for c in collections]
    best = _fuzzy_match(name, names, threshold=0.6)
    if best:
        for c in collections:
            if c.get("name") == best:
                return c
    return None


async def _handle_summarize(user_id: str, query: str, summarize_query: str = None,
                            target_collection: str = None, recent_saved_ids: list = None) -> dict:
    """요약 대상 후보를 카드로 제시 → 사용자가 선택하면 /summarize 로 실제 요약."""
    recent_saved_ids = recent_saved_ids or []

    # 0) 방금 저장한 콘텐츠를 가리키는 경우("이 콘텐츠/방금 거") → 바로 그것을 요약
    #    대상이 특정되지 않은(주제·컬렉션 미지정) 모호한 요청일 때만 방금 저장분으로 직행
    if recent_saved_ids and not summarize_query and not target_collection:
        return await summarize_contents(user_id, recent_saved_ids)

    # 1) 컬렉션을 가리키면(이름이 실제 컬렉션과 매칭되면) 그 폴더의 멤버를 그대로 요약 대상으로
    name_hint = target_collection or summarize_query
    if name_hint:
        collections = await get_collections(user_id)
        matched = _match_collection(name_hint, collections)
        if matched:
            items = await get_collection_contents(user_id, matched["id"])
            if items:
                msg = random.choice([
                    f"'{matched['name']}' 폴더에 {len(items)}개 있네요. 어떤 걸 요약할까요?",
                    f"'{matched['name']}' 컬렉션 안에서 골라주세요 (여러 개 가능).",
                    f"여기 '{matched['name']}' 콘텐츠 {len(items)}개예요. 요약할 것 선택!",
                ])
                return {"answer": msg, "results": _to_cards(items), "action": "summarize_select"}
            return {"answer": f"'{matched['name']}' 폴더가 아직 비어 있어요. 콘텐츠를 먼저 담아주세요.", "results": []}

    # 2) 주제가 명시되면 detailed_summary 기반으로 정확히 관련 콘텐츠만 찾기
    if summarize_query:
        candidates = await _find_relevant_contents(user_id, summarize_query, limit=5)
        if candidates:
            msg = random.choice([
                f"'{summarize_query}' 관련해서 이만큼 찾았어요. 요약할 걸 골라주세요.",
                f"'{summarize_query}' 쪽으로 {len(candidates)}개 있네요 (여러 개 선택 가능).",
                f"이 중에서 요약할 '{summarize_query}' 콘텐츠를 선택해 주세요.",
            ])
            return {"answer": msg, "results": _to_cards(candidates), "action": "summarize_select"}
        return {
            "answer": random.choice([
                f"'{summarize_query}' 관련 콘텐츠가 안 보이네요. 다른 키워드로 말씀해 주실래요?",
                f"음, '{summarize_query}'로는 저장된 게 없어요. 주제를 바꿔볼까요?",
            ]),
            "results": [],
        }

    # 3) 모호("이거/방금 거")인데 방금 저장분도 없을 때 → 최근 저장 3개 제시
    recent = await get_recent_contents(user_id, limit=3)
    if not recent:
        return {"answer": "아직 저장한 콘텐츠가 없어요. 링크를 먼저 보내주시면 저장하고 요약해드릴게요!", "results": []}
    return {
        "answer": random.choice([
            "최근 저장한 것들이에요. 어떤 걸 요약할까요?",
            "방금까지 저장한 콘텐츠 중에 골라주세요.",
            "이 중에 요약할 걸 선택해 주세요 (여러 개 가능).",
        ]),
        "results": _to_cards(recent),
        "action": "summarize_select",
    }


SUMMARY_PROMPT = """너는 콘텐츠 아카이브 전문 분석가야. 사용자가 나중에 이 요약만 보고도 원문을 안 봐도 될 정도로 상세하게 요약해.

═══ 절대 원칙 ═══
1. 원문에 실제로 있는 사실·수치·고유명사만 사용. 없는 내용 절대 생성 금지.
2. '유익합니다', '흥미롭습니다' 같은 추상적 평가 금지. 구체적 사실만.
3. 한국어. 인사말·사족 없이 바로 시작.
4. 원문이 짧더라도 최대한 정보를 빠짐없이 추출.

═══ 콘텐츠 유형별 요약 원칙 ═══
[뉴스/시사]
→ 무슨 일이 일어났고, 왜 일어났고, 어떤 영향이 있는지 서술.
→ 핵심 수치와 인용이 있으면 반드시 포함.
→ 반론이나 다른 시각이 있으면 함께.

[유튜브 영상]
→ 영상이 다루는 주제와 흐름을 시간순/구성순으로 정리.
→ 핵심 장면이나 발언이 있으면 포함.
→ 어떤 사람이 보면 좋을지.

[블로그/아티클]
→ 글쓴이의 핵심 주장과 근거 정리.
→ 실용적 팁이 있으면 구체적으로 추출.
→ 개인 경험담이면 어떤 상황/결론인지.

[쇼핑/제품]
→ 제품명, 가격대, 핵심 스펙.
→ 어떤 용도에 적합한지.
→ 리뷰 요약이 있으면 장단점.

[음악/플레이리스트]
→ 전체 분위기와 장르.
→ 대표곡 2~3개와 아티스트.
→ 어떤 상황에 어울리는지 (새벽, 운동, 집중 등).

[레시피/요리]
→ 요리명, 핵심 재료, 조리 시간.
→ 난이도와 포인트 (이게 맛있어지는 핵심).
→ 몇 인분인지.

[교육/학습]
→ 무엇을 가르치는 콘텐츠인지.
→ 핵심 개념 2~3개 추출.
→ 선수 지식이 필요한지, 난이도.

[위에 해당 안 되는 경우]
→ 콘텐츠의 핵심을 네가 판단해서 가장 유용한 방식으로 요약.
→ 형식에 얽매이지 말고 정보 밀도를 높여.

═══ 출력 형식 ('콘텐츠 유형별 요약 원칙'에 따라 출력 형식안에서 최적의 요약을 하도록 해) ═══

🔑 핵심 한 줄
(이 콘텐츠가 무엇에 대한 것인지 누가 봐도 바로 이해할 수 있는 한 문장. 주어+동사+목적어 구조로. 30자 이상.)

📌 상세 요약
(원문의 핵심 논점을 문단 형태로 서술. 단순 나열이 아니라 흐름이 있게 연결. 최소 150자 이상.)
- 무엇이 일어났는가 / 무엇을 다루는가
- 왜 그런 일이 일어났는가 / 배경 원인
- 어떤 결과 또는 결론이 있는가
- 반론, 논쟁, 다른 시각이 있다면 포함

📊 핵심 팩트
(원문에서 추출 가능한 구체적 사실만. 없으면 "해당 없음")
- 수치/통계: (금액, 퍼센트, 순위, 날짜 등)
- 인물/기관: (언급된 사람 이름, 회사, 기관)
- 지역/장소: (관련 지역이 있다면)
- 시점: (언제 일어난 일인지, 또는 콘텐츠 발행 시점 기준)

🏷️ 주제 키워드
(이 콘텐츠를 나중에 검색할 때 쓸 법한 키워드 5~8개. 쉼표 구분.)
예: 대선, 여론조사, 이재명, 지지율, 2028, 대통령 선거

🔗 관련 맥락
(이 콘텐츠가 어떤 큰 흐름/이슈의 일부인지 1~2문장. 예: "2028 대선을 앞두고 각 후보 캠프의 전략이 본격화되는 시점의 뉴스")

"""


async def _summarize_one(item: dict) -> str:
    """콘텐츠 1개를 원문(description) 기반으로 상세 요약 (요약 내용만 반환)."""
    # description(저장 시 본문 ~1500자)을 1순위 입력으로 사용 → 진짜 디테일 확보
    body = item.get("description") or item.get("detailed_summary", "")
    block = (
        f"[제목] {item.get('title', '')}\n"
        f"[원문 내용] {body}\n"
        f"[저장 시 한줄/요약] {item.get('one_line_summary', '')} / {item.get('detailed_summary', '')}\n"
        f"[태그] {', '.join(item.get('topics') or [])}\n"
        f"[썸네일 설명] {item.get('thumbnail_description', '') or ''}"
    )
    return await _llm(
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": f"위 형식에 맞춰 아래 콘텐츠를 상세히 요약해줘.\n\n{block}"},
        ],
        model="gpt-4o",
        max_tokens=600,
    )


async def summarize_contents(user_id: str, content_ids: list[str]) -> dict:
    """선택된 콘텐츠들을 각각 분리해서 요약 (콘텐츠별 요약 + 카드)."""
    items = await get_contents_by_ids(user_id, content_ids)
    if not items:
        return {"answer": "앗, 요약할 콘텐츠를 찾지 못했어요. 다시 선택해 주실래요?", "results": []}

    # 요청한 순서 유지
    order = {cid: i for i, cid in enumerate(content_ids)}
    items.sort(key=lambda r: order.get(r.get("id"), 999))

    summaries = []
    for it in items:
        text = await _summarize_one(it)
        summaries.append({
            "id": it.get("id"),
            "title": it.get("title", ""),
            "url": it.get("url", ""),
            "thumbnail": it.get("thumbnail_url") or "",
            "summary_text": text,
        })

    if len(items) == 1:
        intro = random.choice(["요약해볼게요.", "이 콘텐츠 핵심만 정리했어요.", "내용 정리해드릴게요."])
    else:
        intro = random.choice([
            f"{len(items)}개 하나씩 정리했어요.",
            f"선택하신 {len(items)}개, 각각 요약했어요.",
            f"{len(items)}개 핵심만 따로따로 모았어요.",
        ])
    return {
        "answer": intro,
        "summaries": summaries,
        "action": "summary_result",
        "intent": "summarize",
    }


GENERAL_PERSONA = (
    "너는 Keepit의 아카이브 비서야. 핵심 역할은 세 가지 — "
    "① 링크 저장, ② 저장한 콘텐츠를 폴더로 묶고 정리, ③ 저장한 콘텐츠 요약·설명.\n"
    "사용자의 말과 맥락에 정확히 맞춰 사람처럼 자연스럽게 대화해:\n"
    "- 인사('안녕')엔 그냥 가볍게 인사로만 답해. 묻지도 않은 폴더·콘텐츠 정보를 먼저 꺼내지 마.\n"
    "- 답변 첫머리를 매번 똑같이 시작하지 마. 특히 '아~'·'~이시군요'·'~해드릴게요' 같은 상투적 패턴을 반복하지 말고 표현을 그때그때 다양하게 바꿔.\n"
    "서비스와 무관한 일반 질문(날씨·코딩·잡담 등)엔 짧게 답하고 부드럽게 본업으로 안내해. "
    "절대 범용 챗봇처럼 장황하게 답하지 마. 한국어로 1~3문장.\n"
    "중요: '~해드릴게요, 잠시만 기다려주세요, 완료되면 알려드릴게요'처럼 실제로 수행하지도 않을 행동을 약속하지 마. "
    "행동이 필요한 요청이면 약속만 하지 말고 실제 기능이 처리하도록 둬."
)


async def _handle_general(user_id: str, query: str, history: list = None) -> dict:
    """도메인 범위 안에서 맥락에 맞게 자연스럽게 대화 + 필요 시 본업으로 안내."""
    history = history or []

    # 폴더 정보를 강제로 끼워넣지 않는다 (맥락 없이 폴더 얘기를 꺼내는 문제 방지)
    messages = [{"role": "system", "content": GENERAL_PERSONA}]
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])})
    messages.append({"role": "user", "content": query})

    answer = await _llm(messages=messages, model="gpt-4o", max_tokens=220)
    # 일반 대화(인사·잡담)에는 행동 유도 버튼을 붙이지 않는다.
    # 행동 유도는 사용자가 실제 기능(검색·요약·폴더 등)을 요청했을 때만 해당 핸들러에서 제안한다.
    return {"answer": answer, "results": []}


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

async def process_chat(user_id: str, query: str, history: list = None, shown_ids: list = None,
                       recent_saved_ids: list = None) -> dict:
    """의도 파악 후 적절한 핸들러 호출."""
    history = history or []
    shown_ids = shown_ids or []
    recent_saved_ids = recent_saved_ids or []

    intent_data = await _detect_intent(query, history=history)
    intent = intent_data.get("intent", "general")
    folder_name = intent_data.get("folder_name")
    delete_query = intent_data.get("delete_query")
    move_query = intent_data.get("move_query")
    target_folder = intent_data.get("target_folder")
    summarize_query = intent_data.get("summarize_query")
    target_collection = intent_data.get("target_collection")

    if intent == "search":
        result = await _handle_search(user_id, query, shown_ids=shown_ids, history=history)
    elif intent == "summarize":
        result = await _handle_summarize(user_id, query, summarize_query, target_collection, recent_saved_ids)
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
        # general 및 미매칭 → 검색이 아니라 도메인 대화로
        result = await _handle_general(user_id, query, history=history)

    result["intent"] = intent
    return result
