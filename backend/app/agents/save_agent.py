"""저장 파이프라인 — LangGraph 기반 6단계 에이전트.

흐름:
    extract → dedup → classify → embed → save → END

각 단계는 SaveState 를 받아 업데이트된 SaveState 를 반환.
"""
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END
from loguru import logger

from app.services.metadata.router import extract_metadata
from app.services.ai_classifier import classify_content
from app.services.embedder import create_embedding
from app.services.supabase_client import is_duplicate, save_content


class SaveState(TypedDict, total=False):
    user_id: str
    url: str
    metadata: Optional[dict]
    is_duplicate: bool
    ai_result: Optional[dict]
    embedding: Optional[list]
    content_id: Optional[str]
    error: Optional[str]


def node_extract(state: SaveState) -> SaveState:
    """Tool 1: 메타데이터 추출."""
    try:
        state["metadata"] = extract_metadata(state["url"])
        logger.info(f"메타 추출 완료: {state['metadata'].get('title', '')[:30]}")
    except Exception as e:
        state["error"] = f"metadata: {e}"
        logger.exception("메타데이터 추출 실패")
    return state


def node_dedup(state: SaveState) -> SaveState:
    """Tool 2: 중복 검사."""
    state["is_duplicate"] = is_duplicate(state["user_id"], state["url"])
    if state["is_duplicate"]:
        logger.info(f"이미 저장된 URL: {state['url']}")
    return state


def node_classify(state: SaveState) -> SaveState:
    """Tool 3: AI 분류·태그·요약."""
    try:
        state["ai_result"] = classify_content(state["metadata"])
        logger.info(f"분류 완료: {state['ai_result'].get('category')}")
    except Exception as e:
        state["error"] = f"classify: {e}"
        logger.exception("AI 분류 실패")
    return state


def node_embed(state: SaveState) -> SaveState:
    """Tool 4: 임베딩 생성."""
    try:
        state["embedding"] = create_embedding(state["metadata"], state["ai_result"])
        logger.info("임베딩 생성 완료")
    except Exception as e:
        state["error"] = f"embed: {e}"
        logger.exception("임베딩 실패")
    return state


def node_save(state: SaveState) -> SaveState:
    """Tool 5: DB 저장."""
    try:
        state["content_id"] = save_content(state)
        logger.info(f"DB 저장 완료: {state['content_id']}")
    except Exception as e:
        state["error"] = f"save: {e}"
        logger.exception("DB 저장 실패")
    return state


def _should_continue(state: SaveState) -> str:
    """에러 또는 중복이면 즉시 종료."""
    if state.get("error"):
        return END
    if state.get("is_duplicate"):
        return END
    return "continue"


# 그래프 정의
_workflow = StateGraph(SaveState)
_workflow.add_node("extract", node_extract)
_workflow.add_node("dedup", node_dedup)
_workflow.add_node("classify", node_classify)
_workflow.add_node("embed", node_embed)
_workflow.add_node("save", node_save)

_workflow.set_entry_point("extract")
_workflow.add_edge("extract", "dedup")
_workflow.add_conditional_edges(
    "dedup",
    _should_continue,
    {"continue": "classify", END: END},
)
_workflow.add_edge("classify", "embed")
_workflow.add_edge("embed", "save")
_workflow.add_edge("save", END)

save_agent = _workflow.compile()
