# tests/test_auth.py
"""
실제 auth dependency 동작 검증.
conftest의 global override와 DEV_MODE를 모두 해제한 별도 fixture 사용.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock

import app.http_client as _http_client
import app.auth as _auth_module
from app.main import app
from app.auth import get_current_user_id
from tests.conftest import TEST_USER_ID


class _FakeSupabaseClient:
    """Supabase auth API를 흉내내는 fake httpx client"""
    def __init__(self, status: int, user_id: str = ""):
        self._status = status
        self._user_id = user_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, *a, **kw):
        m = MagicMock()
        m.status_code = self._status
        m.json.return_value = {"id": self._user_id}
        return m


@pytest_asyncio.fixture
async def real_auth_client():
    """auth override와 DEV_MODE를 모두 해제 — auth dependency가 실제로 동작."""
    original_override = app.dependency_overrides.pop(get_current_user_id, None)
    original_dev_mode = _auth_module._DEV_MODE
    _auth_module._DEV_MODE = False          # DEV_MODE 강제 비활성화

    await _http_client.startup()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    await _http_client.shutdown()

    _auth_module._DEV_MODE = original_dev_mode
    if original_override:
        app.dependency_overrides[get_current_user_id] = original_override


# ── 테스트 ────────────────────────────────────────────────────────────────────

async def test_missing_auth_header_returns_401(real_auth_client):
    """Authorization 헤더 없음 → 401.
    헤더가 optional(default="")이므로 FastAPI 422 대신 auth 로직에서 401 반환."""
    resp = await real_auth_client.post(
        "/ingest",
        json={"url": "https://example.com/article", "user_id": TEST_USER_ID},
    )
    assert resp.status_code == 401


async def test_invalid_bearer_format_returns_401(real_auth_client):
    """'Bearer ' 접두사 없는 토큰 → 401."""
    resp = await real_auth_client.post(
        "/ingest",
        json={"url": "https://example.com/article", "user_id": TEST_USER_ID},
        headers={"Authorization": "InvalidToken"},
    )
    assert resp.status_code == 401


async def test_invalid_token_returns_401(real_auth_client):
    """Supabase가 토큰 검증 실패 → 401."""
    with patch("app.auth.httpx.AsyncClient", return_value=_FakeSupabaseClient(401)):
        resp = await real_auth_client.post(
            "/ingest",
            json={"url": "https://example.com/article", "user_id": TEST_USER_ID},
            headers={"Authorization": "Bearer bad-token"},
        )
    assert resp.status_code == 401


async def test_valid_token_passes_auth(real_auth_client):
    """유효한 토큰 → auth 통과, 엔드포인트 로직 실행."""
    from tests.conftest import SAMPLE_METADATA, SAMPLE_ANALYSIS, SAMPLE_EMBEDDING

    with (
        patch("app.auth.httpx.AsyncClient", return_value=_FakeSupabaseClient(200, TEST_USER_ID)),
        patch("app.main.check_duplicate", new_callable=AsyncMock, return_value=None),
        patch("app.main.save_content", new_callable=AsyncMock, return_value={"id": "c-001"}),
        patch("app.main._run_pipeline", new_callable=AsyncMock, return_value={
            "id": "c-001", "title": "테스트", "analysis_status": "completed",
        }),
    ):
        resp = await real_auth_client.post(
            "/ingest",
            json={"url": "https://example.com/article", "user_id": TEST_USER_ID},
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 200
    assert resp.json()["analysis_status"] == "completed"
