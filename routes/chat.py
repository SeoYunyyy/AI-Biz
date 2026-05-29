# ── LLM 대화 — 의도 분류 기반 채팅 인터페이스 ──

import json
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, session
from openai import OpenAI
import os

from database.db import (
    search_contents, get_deadlines, get_collections, get_old_contents,
)
from services.embedding import generate_embedding
from services.query_expander import expand_query

chat_bp = Blueprint('chat', __name__)
client  = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

INTENT_PROMPT = """사용자 메시지와 대화 맥락을 보고 의도를 분류하세요. 반드시 JSON만 응답.

의도 종류:
- search   : 저장한 콘텐츠를 찾거나 검색하는 요청 (이전 검색의 후속 답변 포함)
- deadline : 마감기한 관련 질문 ("마감 언제야", "임박한 거 뭐야" 등)
- folder   : 폴더 생성·지정·관리 ("이 링크 OO 폴더에 넣어줘" 등)
- move     : 콘텐츠를 다른 폴더로 이동 ("OO 폴더로 옮겨줘" 등)
- cleanup  : 오래된·만료된 콘텐츠 정리 또는 리마인드 요청
- delete   : 특정 콘텐츠 삭제 요청 ("OO 관련 삭제해줘" 등)
- general  : 그 외

응답 형식:
{"intent": "search", "folder_name": null, "delete_query": null, "move_query": null, "target_folder": null}

folder_name: 폴더 의도일 때만 폴더명 추출, 없으면 null
delete_query: 삭제 의도일 때 삭제 대상 키워드, 없으면 null
move_query: 이동 의도일 때 이동할 콘텐츠 키워드, 없으면 null
target_folder: 이동 의도일 때 목적지 폴더명, 없으면 null"""

DISSATISFACTION_SIGNALS = ["없", "아니", "못 찾", "모르겠", "그거 말고", "다른 거", "없는데", "아닌데", "틀렸"]
_FOLLOWUP_ASKED_MARKERS = [
    "아래 질문으로 범위를 좁혀볼게요",
    "조금 더 알려주시면 다시 찾아볼게요",
    "기억나시나요",
    "유튜브 영상이었나요",
]


def _llm(messages: list, model: str = "gpt-4o-mini", max_tokens: int = 500, json_mode: bool = False) -> str:
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**body)
    return response.choices[0].message.content.strip()


def _detect_intent(query: str, history: list) -> dict:
    try:
        messages = [{"role": "system", "content": INTENT_PROMPT}]
        messages += history[-20:]
        messages += [{"role": "user", "content": query}]
        raw = _llm(messages, model="gpt-4o-mini", max_tokens=80, json_mode=True)
        return json.loads(raw)
    except Exception:
        return {"intent": "general", "folder_name": None}


def _filter_results(query: str, results: list) -> list:
    """LLM으로 검색 결과 중 명백히 무관한 항목만 제거"""
    if not results:
        return results
    try:
        items = "\n".join([
            f"- id:{r['id']} | 제목:{r.get('title','')} | 태그:{','.join(r.get('topics', []))}"
            for r in results
        ])
        raw = _llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "검색 결과에서 명백히 무관한 항목만 제거하세요. "
                        "한국어 줄임말이나 영어 표기 등 표현이 다를 수 있으므로, 확실하지 않으면 포함시키세요. "
                        "관련 있을 가능성이 있는 결과의 id를 JSON 배열로 반환. 예: [\"id1\", \"id2\"]"
                    ),
                },
                {"role": "user", "content": f"검색어: {query}\n\n결과:\n{items}"},
            ],
            model="gpt-4o-mini",
            max_tokens=200,
        )
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if not match:
            return results
        valid_ids = json.loads(match.group())
        filtered = [r for r in results if r["id"] in valid_ids]
        return filtered if filtered else results
    except Exception:
        return results


def _build_context_query(query: str, history: list) -> str:
    """이전 대화 맥락을 반영한 통합 검색 쿼리 생성"""
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
        refined = _llm(messages, model="gpt-4o-mini", max_tokens=80)
        return refined or query
    except Exception:
        return query


def _fuzzy_match(name: str, candidates: list, threshold: float = 0.75) -> str | None:
    name_norm = name.replace(" ", "").lower()
    best_ratio, best_match = 0.0, None
    for c in candidates:
        ratio = SequenceMatcher(None, name_norm, c.replace(" ", "").lower()).ratio()
        if ratio > best_ratio:
            best_ratio, best_match = ratio, c
    return best_match if best_ratio >= threshold else None


def _is_dissatisfied(query: str, history: list) -> bool:
    if not history:
        return False
    return any(s in query for s in DISSATISFACTION_SIGNALS)


def _already_asked_followup(history: list) -> bool:
    return any(
        any(marker in m.get("content", "") for marker in _FOLLOWUP_ASKED_MARKERS)
        for m in history
        if m.get("role") == "assistant"
    )


# ── 핸들러 ────────────────────────────────────────────────────────────────────

def _handle_search(user_id: str, query: str, history: list, shown_ids: list) -> dict:
    already_asked = _already_asked_followup(history)

    if _is_dissatisfied(query, history) and already_asked:
        return {
            "answer": "그 조건으로도 찾지 못했어요. 제목에 포함된 단어나 저장 시기를 조금 더 알려주시면 다시 찾아볼게요.",
            "results": [],
            "follow_up_questions": [],
        }

    if _is_dissatisfied(query, history) and not already_asked:
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

    context_query = _build_context_query(query, history) if history else query
    expanded  = expand_query(context_query)
    embedding = generate_embedding(expanded)

    if not embedding:
        return {"answer": "검색어 처리 중 문제가 생겼어요. 다시 시도해주세요.", "results": [], "follow_up_questions": []}

    threshold   = 0.4 if shown_ids else 0.3
    raw_results = search_contents(user_id, embedding, limit=10, threshold=threshold)
    candidates  = [r for r in raw_results if r.get("id") not in shown_ids]
    candidates  = _filter_results(expanded, candidates)
    results     = candidates[:5]

    if not results:
        if already_asked:
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
            "follow_up_questions": ["맞아요", "아니요, 다른 거예요"],
        }

    count    = len(results)
    answer   = f"관련 콘텐츠 {count}개 찾았어요."
    follow_up = ["이 중에 없으면 '없어'라고 해주세요."] if count >= 3 else []

    return {"answer": answer, "results": results, "follow_up_questions": follow_up}


def _handle_deadline(user_id: str) -> dict:
    deadlines  = get_deadlines(user_id)
    today      = datetime.now(timezone.utc).date()
    today_str  = today.isoformat()
    week_later = (today + timedelta(days=7)).isoformat()

    urgent  = [d for d in deadlines if today_str <= d.get("deadline_date", "9999") <= week_later]
    relaxed = [d for d in deadlines if d.get("deadline_date", "9999") > week_later]
    expired = [d for d in deadlines if d.get("deadline_date", "9999") < today_str]

    if not urgent and not relaxed and not expired:
        return {"answer": "마감기한이 있는 콘텐츠가 없어요.", "results": []}

    context_parts = []
    if urgent:
        context_parts.append("[ 마감 임박 — 7일 이내 ]")
        context_parts += [f"- {d.get('title','')}: {d.get('deadline_date','')} ({d.get('deadline_note','')})" for d in urgent]
    if relaxed:
        context_parts.append("\n[ 여유 있음 — 7일 초과 ]")
        context_parts += [f"- {d.get('title','')}: {d.get('deadline_date','')} ({d.get('deadline_note','')})" for d in relaxed[:5]]
    if expired:
        context_parts.append("\n[ 만료됨 ]")
        context_parts += [f"- {d.get('title','')}: {d.get('deadline_date','')} ({d.get('deadline_note','')})" for d in expired[:3]]

    answer = _llm(
        messages=[
            {
                "role": "system",
                "content": (
                    "사용자의 마감기한 목록입니다. "
                    "7일 이내 임박한 것은 긴박하게 강조하고, "
                    "여유 있는 것은 가볍게 언급하고, "
                    "만료된 것은 정리를 권유하세요. 친근하게. 한국어로. 3~4문장."
                ),
            },
            {"role": "user", "content": "\n".join(context_parts)},
        ],
        model="gpt-4o",
        max_tokens=220,
    )

    return {"answer": answer, "urgent": urgent, "relaxed": relaxed[:5], "expired": expired[:3]}


def _handle_folder(user_id: str, folder_name: str) -> dict:
    collections    = get_collections(user_id)
    existing_names = [c["name"] for c in collections]
    matched        = _fuzzy_match(folder_name, existing_names)

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


def _handle_cleanup(user_id: str) -> dict:
    deadlines    = get_deadlines(user_id)
    today        = datetime.now(timezone.utc).date().isoformat()
    expired      = [d for d in deadlines if d.get("deadline_date", "9999") < today]
    old_contents = get_old_contents(user_id, days=365)

    if not expired and not old_contents:
        return {"answer": "정리할 콘텐츠가 없어요. 저장 목록이 깔끔하네요!", "results": []}

    context_parts = []
    if expired:
        context_parts.append(f"[ 마감 만료 — {len(expired)}개 ]")
        context_parts += [f"- {d.get('title','')}: {d.get('deadline_date','')} 만료" for d in expired[:5]]
    if old_contents:
        context_parts.append(f"\n[ 1년 이상 된 콘텐츠 — {len(old_contents)}개 ]")
        context_parts += [f"- {c.get('title','')} ({c.get('saved_at','')[:10]} 저장)" for c in old_contents[:5]]

    answer = _llm(
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

    return {"answer": answer, "expired": expired[:5], "old_contents": old_contents[:5], "action": "cleanup_suggested"}


def _handle_move(user_id: str, move_query: str, target_folder: str) -> dict:
    expanded  = expand_query(move_query)
    embedding = generate_embedding(expanded)
    if not embedding:
        return {"answer": "이동할 콘텐츠를 찾지 못했어요.", "results": []}

    results = search_contents(user_id, embedding, limit=5)
    if not results:
        return {"answer": f"'{move_query}' 관련 콘텐츠를 찾지 못했어요.", "results": []}

    collections    = get_collections(user_id)
    existing_names = [c["name"] for c in collections]
    matched_folder = _fuzzy_match(target_folder, existing_names) or target_folder

    titles = "\n".join([f"- {r.get('title','제목 없음')}" for r in results])
    return {
        "answer": (
            f"'{move_query}' 관련 콘텐츠 {len(results)}개를 찾았어요:\n{titles}\n\n"
            f"'{matched_folder}' 폴더로 이동할까요?"
        ),
        "needs_confirmation": True,
        "pending_move_ids":   [r["id"] for r in results],
        "target_folder":      matched_folder,
        "results":            results,
    }


def _handle_delete(user_id: str, delete_query: str) -> dict:
    expanded  = expand_query(delete_query)
    embedding = generate_embedding(expanded)
    if not embedding:
        return {"answer": "삭제할 콘텐츠를 찾지 못했어요.", "results": []}

    results = search_contents(user_id, embedding, limit=5)
    if not results:
        return {"answer": f"'{delete_query}' 관련 콘텐츠를 찾지 못했어요.", "results": []}

    titles = "\n".join([f"- {r.get('title','제목 없음')}" for r in results])
    return {
        "answer": f"'{delete_query}' 관련 콘텐츠 {len(results)}개를 찾았어요:\n{titles}\n\n삭제할까요?",
        "needs_confirmation":  True,
        "pending_delete_ids":  [r["id"] for r in results],
        "results":             results,
    }


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    """
    의도 자동 파악 후 처리:
    - search  : 벡터 검색 → 불만족 감지 → 유도 질문
    - deadline: 마감기한 정리
    - folder  : 유사 폴더 감지 → 확인 요청
    - move    : 콘텐츠 폴더 이동
    - delete  : 콘텐츠 삭제 확인
    - cleanup : 만료/오래된 콘텐츠 정리 안내
    """
    user_id = (session.get('user') or {}).get('id', '')
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    data      = request.json
    message   = (data.get('message') or '').strip()
    history   = data.get('history', [])       # [{"role": "user"/"assistant", "content": "..."}]
    shown_ids = data.get('shown_ids', [])     # 이미 보여준 콘텐츠 ID (재검색 시 제외)

    if not message:
        return jsonify({'error': '메시지를 입력해주세요'}), 400

    intent_data   = _detect_intent(message, history)
    intent        = intent_data.get('intent', 'general')
    folder_name   = intent_data.get('folder_name')
    delete_query  = intent_data.get('delete_query')
    move_query    = intent_data.get('move_query')
    target_folder = intent_data.get('target_folder')

    if intent == 'search':
        result = _handle_search(user_id, message, history, shown_ids)
    elif intent == 'deadline':
        result = _handle_deadline(user_id)
    elif intent == 'folder' and folder_name:
        result = _handle_folder(user_id, folder_name)
    elif intent == 'cleanup':
        result = _handle_cleanup(user_id)
    elif intent == 'move' and move_query and target_folder:
        result = _handle_move(user_id, move_query, target_folder)
    elif intent == 'delete' and delete_query:
        result = _handle_delete(user_id, delete_query)
    else:
        result = _handle_search(user_id, message, history, shown_ids)

    result['intent'] = intent
    return jsonify(result)

# 의도 분류 후 search/deadline/folder/move/delete/cleanup 핸들러로 분기, 대화 히스토리 유지
