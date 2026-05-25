"""POST /api/search, /api/chat — 의미 검색 + RAG 챗봇."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from openai import OpenAI

from app.config import settings
from app.deps import get_current_user, CurrentUser
from app.services.search_engine import hybrid_search
from app.services.supabase_client import log_event


router = APIRouter()
client = OpenAI(api_key=settings.openai_api_key)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("/search")
def search(
    req: SearchRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """순수 의미 검색 — 답변 생성 없음, 결과 카드만."""
    results = hybrid_search(user.id, req.query, top_k=req.top_k)
    log_event(user.id, "search", {"query": req.query, "hits": len(results)})
    return {"results": results}


class ChatRequest(BaseModel):
    query: str


@router.post("/chat")
def chat(
    req: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """RAG 챗봇 — 저장된 콘텐츠를 컨텍스트로 LLM이 답변."""
    contexts = hybrid_search(user.id, req.query, top_k=5)

    # Self-RAG 폴백: 유사도가 너무 낮으면 환각 방지
    if not contexts or contexts[0]["score"] < 0.05:
        return {
            "answer": "저장하신 콘텐츠 중 관련 항목을 찾지 못했어요. 검색어를 바꿔보거나 더 저장해 보세요.",
            "sources": [],
        }

    context_text = "\n\n".join([
        f"- 제목: {c.get('title', '')}\n  요약: {c.get('summary', '')}\n  카테고리: {c.get('category', '')}"
        for c in contexts
    ])

    system = (
        "당신은 사용자의 개인 콘텐츠 큐레이터입니다. "
        "반드시 제공된 '저장된 콘텐츠'만을 근거로 답변하세요. "
        "근거에 없는 정보를 만들어내지 마세요. "
        "한국어로 친근한 톤으로 2~4문장 답변하고, 추천한 콘텐츠가 어떤 점에서 좋은지 간단히 언급하세요."
    )
    user_msg = f"질문: {req.query}\n\n저장된 콘텐츠:\n{context_text}"

    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.5,
    )
    answer = resp.choices[0].message.content

    log_event(user.id, "chat", {"query": req.query})
    return {"answer": answer, "sources": contexts}
