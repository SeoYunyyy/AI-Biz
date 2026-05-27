# tests/conftest.py

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

import app.http_client as _http_client
from app.main import app
from app.auth import get_current_user_id

TEST_USER_ID = "test-user-uuid-1234"
AUTH_HEADER = {"Authorization": "Bearer test-token"}

# ── 인증 의존성 오버라이드 ────────────────────────────────────────────────────

async def _mock_auth() -> str:
    return TEST_USER_ID

app.dependency_overrides[get_current_user_id] = _mock_auth


# ── 기본 샘플 데이터 ─────────────────────────────────────────────────────────

SAMPLE_METADATA = {
    "title": "테스트 콘텐츠",
    "platform": "web",
    "summary": "테스트용 요약 내용입니다.",
    "thumbnail": "https://example.com/thumb.jpg",
    "author": "테스터",
    "date": "2026-05-27",
    "original_url": "https://example.com/article",
}

SAMPLE_ANALYSIS = {
    "one_line_summary": "테스트 한 줄 요약",
    "detailed_summary": "테스트 상세 요약입니다. 두 문장 정도 됩니다.",
    "tags": ["테스트", "샘플", "API"],
    "category": "IT/기술",
    "sub_category": "테스트",
    "save_purpose": "테스트용 저장",
    "has_deadline": False,
    "deadline_date": None,
    "deadline_note": None,
    "deadline_items": [],
    "user_collection": None,
}

SAMPLE_EMBEDDING = [0.1] * 1536

SAMPLE_CONTENT = {
    "id": "content-id-001",
    "title": "테스트 콘텐츠",
    "thumbnail_url": "https://example.com/thumb.jpg",
    "platform": "web",
    "category": "IT/기술",
    "one_line_summary": "테스트 한 줄 요약",
    "tags": ["테스트"],
    "has_deadline": False,
    "deadline_date": None,
    "deadline_note": None,
    "sub_category": "테스트",
    "analysis_status": "completed",
}


# ── 픽스처 ────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """공유 http 클라이언트 초기화 후 테스트 앱 클라이언트 반환."""
    await _http_client.startup()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    await _http_client.shutdown()
