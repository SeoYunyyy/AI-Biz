# tests/test_endpoints.py
"""
각 엔드포인트 정상/비정상 케이스 테스트.
외부 의존성(OpenAI, Supabase)은 모두 mock 처리.
"""

from unittest.mock import AsyncMock, patch, MagicMock

from tests.conftest import (
    TEST_USER_ID,
    AUTH_HEADER,
    SAMPLE_METADATA,
    SAMPLE_ANALYSIS,
    SAMPLE_EMBEDDING,
    SAMPLE_CONTENT,
)

# ── GET / ─────────────────────────────────────────────────────────────────────

async def test_health(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "Keepit API"}


# ── POST /ingest ──────────────────────────────────────────────────────────────

@patch("app.main.check_duplicate", new_callable=AsyncMock, return_value=None)
@patch("app.main.save_content", new_callable=AsyncMock, return_value={"id": "content-id-001"})
@patch("app.main._run_pipeline", new_callable=AsyncMock, return_value={
    "id": "content-id-001",
    "title": "테스트 콘텐츠",
    "analysis_status": "completed",
    "tags": ["테스트"],
    "has_deadline": False,
})
async def test_ingest_success(mock_pipeline, mock_save, mock_dup, client):
    """정상 저장 → 파이프라인 완료 결과 반환."""
    resp = await client.post(
        "/ingest",
        json={"url": "https://example.com/article", "user_id": TEST_USER_ID},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis_status"] == "completed"
    assert data["id"] == "content-id-001"
    mock_dup.assert_awaited_once()
    mock_save.assert_awaited_once()
    mock_pipeline.assert_awaited_once()


@patch(
    "app.main.check_duplicate",
    new_callable=AsyncMock,
    return_value={"id": "existing-id", "title": "기존 콘텐츠", "analysis_status": "completed", "hashtags": []},
)
async def test_ingest_duplicate(mock_dup, client):
    """중복 URL → duplicate:True 반환 (새 저장 없음)."""
    resp = await client.post(
        "/ingest",
        json={"url": "https://example.com/article", "user_id": TEST_USER_ID},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicate"] is True
    assert data["content"]["id"] == "existing-id"


async def test_ingest_invalid_url(client):
    """URL 형식 오류 → 422 Unprocessable Entity."""
    resp = await client.post(
        "/ingest",
        json={"url": "not-a-url", "user_id": TEST_USER_ID},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 422


async def test_ingest_wrong_user(client):
    """토큰 user_id ≠ 요청 user_id → 403."""
    resp = await client.post(
        "/ingest",
        json={"url": "https://example.com/article", "user_id": "other-user-id"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 403


@patch("app.main.check_duplicate", new_callable=AsyncMock, return_value=None)
@patch("app.main.save_content", new_callable=AsyncMock, return_value={"id": "content-id-001"})
@patch("app.main._run_pipeline", new_callable=AsyncMock, return_value={
    "id": "content-id-001", "analysis_status": "completed",
})
async def test_ingest_no_auth_with_override(mock_pipeline, mock_save, mock_dup, client):
    """
    conftest auth override 환경에서는 Authorization 헤더가 없어도 요청이 통과됨.
    실제 auth 미제공 → 422 동작은 tests/test_auth.py 에서 검증.
    """
    resp = await client.post(
        "/ingest",
        json={"url": "https://example.com/article", "user_id": TEST_USER_ID},
    )
    assert resp.status_code == 200


# ── GET /contents/{content_id} ────────────────────────────────────────────────

@patch("app.main.get_content", new_callable=AsyncMock, return_value=SAMPLE_CONTENT)
async def test_get_content_found(mock_get, client):
    resp = await client.get("/contents/content-id-001", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["analysis_status"] == "completed"


@patch("app.main.get_content", new_callable=AsyncMock, return_value=None)
async def test_get_content_not_found(mock_get, client):
    resp = await client.get("/contents/nonexistent-id", headers=AUTH_HEADER)
    assert resp.status_code == 404


# ── POST /search ──────────────────────────────────────────────────────────────

@patch("app.main.generate_embedding", new_callable=AsyncMock, return_value=SAMPLE_EMBEDDING)
@patch(
    "app.main.search_contents",
    new_callable=AsyncMock,
    return_value=[{"id": "c1", "title": "결과1", "description": "설명", "content_type": "web", "similarity": 0.85}],
)
async def test_search_found(mock_search, mock_embed, client):
    resp = await client.post(
        "/search",
        json={"query": "테스트 검색어", "user_id": TEST_USER_ID},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert len(data["results"]) == 1


@patch("app.main.generate_embedding", new_callable=AsyncMock, return_value=SAMPLE_EMBEDDING)
@patch("app.main.search_contents", new_callable=AsyncMock, return_value=[])
async def test_search_not_found(mock_search, mock_embed, client):
    resp = await client.post(
        "/search",
        json={"query": "전혀 없는 내용", "user_id": TEST_USER_ID},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is False
    assert len(data["follow_up_questions"]) > 0


@patch("app.main.generate_embedding", new_callable=AsyncMock, return_value=SAMPLE_EMBEDDING)
@patch("app.main.search_contents", new_callable=AsyncMock, return_value=[])
async def test_search_respects_limit(mock_search, mock_embed, client):
    """req.limit이 search_contents에 전달되는지 확인 (Fix 3)."""
    await client.post(
        "/search",
        json={"query": "테스트", "user_id": TEST_USER_ID, "limit": 10},
        headers=AUTH_HEADER,
    )
    _, kwargs = mock_search.call_args
    assert kwargs.get("limit") == 10 or mock_search.call_args[0][2] == 10


async def test_search_wrong_user(client):
    resp = await client.post(
        "/search",
        json={"query": "검색", "user_id": "other-user"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 403


# ── GET /deadlines/{user_id} ──────────────────────────────────────────────────

@patch(
    "app.main.fetch_deadlines",
    new_callable=AsyncMock,
    return_value=[
        {"id": "d1", "title": "마감 임박 콘텐츠", "deadline_date": "2026-06-01", "deadline_note": "신청 마감 6/1"}
    ],
)
async def test_deadlines(mock_fetch, client):
    resp = await client.get(f"/deadlines/{TEST_USER_ID}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "deadlines" in data
    assert data["deadlines"][0]["id"] == "d1"


async def test_deadlines_wrong_user(client):
    resp = await client.get("/deadlines/other-user-id", headers=AUTH_HEADER)
    assert resp.status_code == 403


# ── GET /collections/{user_id} ────────────────────────────────────────────────

@patch(
    "app.main.get_collections",
    new_callable=AsyncMock,
    return_value=[{"id": "col-1", "name": "생비과제", "emoji": None, "content_count": 3}],
)
async def test_get_collections(mock_get, client):
    resp = await client.get(f"/collections/{TEST_USER_ID}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["collections"][0]["name"] == "생비과제"


async def test_get_collections_wrong_user(client):
    resp = await client.get("/collections/other-user-id", headers=AUTH_HEADER)
    assert resp.status_code == 403


# ── POST /collections ─────────────────────────────────────────────────────────

@patch("app.main.get_or_create_collection", new_callable=AsyncMock, return_value="new-col-uuid")
async def test_create_collection(mock_create, client):
    """Fix 7: body로 user_id, name 전달."""
    resp = await client.post(
        "/collections",
        json={"user_id": TEST_USER_ID, "name": "새 폴더"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["collection_id"] == "new-col-uuid"
    assert data["name"] == "새 폴더"


@patch("app.main.get_or_create_collection", new_callable=AsyncMock, return_value=None)
async def test_create_collection_failure(mock_create, client):
    resp = await client.post(
        "/collections",
        json={"user_id": TEST_USER_ID, "name": "실패 폴더"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 500


async def test_create_collection_wrong_user(client):
    resp = await client.post(
        "/collections",
        json={"user_id": "other-user", "name": "폴더"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 403


# ── POST /chat ────────────────────────────────────────────────────────────────

@patch(
    "app.main.process_chat",
    new_callable=AsyncMock,
    return_value={"answer": "테스트 응답입니다.", "results": [], "intent": "search", "follow_up_questions": []},
)
async def test_chat(mock_chat, client):
    resp = await client.post(
        "/chat",
        json={"query": "내가 저장한 파이썬 자료 찾아줘", "user_id": TEST_USER_ID},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["intent"] == "search"


async def test_chat_wrong_user(client):
    resp = await client.post(
        "/chat",
        json={"query": "검색", "user_id": "other-user"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 403
