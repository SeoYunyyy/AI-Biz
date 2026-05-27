# tests/test_pipeline.py
"""
_run_pipeline 백그라운드 함수 단위 테스트.
모든 외부 호출을 mock하고 성공/실패 케이스를 검증.
"""

import pytest
from unittest.mock import AsyncMock, patch, call

from app.main import _run_pipeline
from tests.conftest import (
    SAMPLE_METADATA,
    SAMPLE_ANALYSIS,
    SAMPLE_EMBEDDING,
)

CONTENT_ID = "pipeline-test-id"
USER_ID = "test-user-uuid-1234"
URL = "https://example.com/article"


@patch("app.main.update_content", new_callable=AsyncMock, return_value=True)
@patch("app.main.find_similar_contents", new_callable=AsyncMock, return_value=[])
@patch("app.main.embed", new_callable=AsyncMock, return_value=SAMPLE_EMBEDDING)
@patch("app.main.get_or_create_collection", new_callable=AsyncMock, return_value=None)
@patch("app.main.classify", new_callable=AsyncMock, return_value=SAMPLE_ANALYSIS)
@patch("app.main.analyze_thumbnail", new_callable=AsyncMock, return_value="썸네일 설명")
@patch("app.main.dispatch", new_callable=AsyncMock, return_value=SAMPLE_METADATA)
async def test_pipeline_success(
    mock_dispatch,
    mock_thumb,
    mock_classify,
    mock_collection,
    mock_embed,
    mock_similar,
    mock_update,
):
    """정상 파이프라인: 각 단계가 순서대로 호출되고 update_content가 completed로 저장."""
    await _run_pipeline(CONTENT_ID, URL, USER_ID, "", None)

    mock_dispatch.assert_awaited_once_with(URL)
    mock_thumb.assert_awaited_once()
    mock_classify.assert_awaited_once()
    # Fix 4: embed()가 한 번만 호출되고 반환값을 find_similar_contents에 재사용
    mock_embed.assert_awaited_once_with(CONTENT_ID, SAMPLE_METADATA, SAMPLE_ANALYSIS, "썸네일 설명")
    mock_similar.assert_awaited_once_with(USER_ID, SAMPLE_EMBEDDING)
    mock_update.assert_awaited_once()


@patch("app.main.update_content", new_callable=AsyncMock, return_value=True)
@patch("app.main.find_similar_contents", new_callable=AsyncMock, return_value=[])
@patch("app.main.embed", new_callable=AsyncMock, return_value=SAMPLE_EMBEDDING)
@patch(
    "app.main.get_or_create_collection",
    new_callable=AsyncMock,
    return_value="col-uuid-new",
)
@patch(
    "app.main.classify",
    new_callable=AsyncMock,
    return_value={**SAMPLE_ANALYSIS, "user_collection": "생비과제"},
)
@patch("app.main.analyze_thumbnail", new_callable=AsyncMock, return_value="")
@patch("app.main.dispatch", new_callable=AsyncMock, return_value=SAMPLE_METADATA)
async def test_pipeline_creates_collection(
    mock_dispatch, mock_thumb, mock_classify, mock_collection, mock_embed, mock_similar, mock_update
):
    """AI가 user_collection을 반환하면 get_or_create_collection 호출."""
    await _run_pipeline(CONTENT_ID, URL, USER_ID, "", None)

    mock_collection.assert_awaited_once_with(USER_ID, "생비과제")
    _, call_kwargs = mock_update.call_args
    assert call_kwargs.get("collection_id") == "col-uuid-new"


@patch("app.main.update_content", new_callable=AsyncMock, return_value=True)
@patch("app.main.find_similar_contents", new_callable=AsyncMock, return_value=[])
@patch("app.main.embed", new_callable=AsyncMock, return_value=[])   # 임베딩 실패
@patch("app.main.get_or_create_collection", new_callable=AsyncMock)
@patch("app.main.classify", new_callable=AsyncMock, return_value=SAMPLE_ANALYSIS)
@patch("app.main.analyze_thumbnail", new_callable=AsyncMock, return_value="")
@patch("app.main.dispatch", new_callable=AsyncMock, return_value=SAMPLE_METADATA)
async def test_pipeline_embedding_failure_continues(
    mock_dispatch, mock_thumb, mock_classify, mock_collection, mock_embed, mock_similar, mock_update
):
    """임베딩 실패해도 파이프라인이 계속돼 update_content까지 도달 (graceful degradation)."""
    await _run_pipeline(CONTENT_ID, URL, USER_ID, "", None)

    # 임베딩 빈 리스트 → find_similar_contents 호출 안 됨
    mock_similar.assert_not_awaited()
    # 하지만 update_content는 정상 호출
    mock_update.assert_awaited_once()


@patch("app.main.dispatch", new_callable=AsyncMock, side_effect=Exception("크롤링 오류"))
async def test_pipeline_dispatch_failure_raises(mock_dispatch):
    """dispatch 예외 발생 시 _run_pipeline이 예외를 그대로 올림.
    (mark_failed는 엔드포인트 레벨의 try/except에서 호출됨)"""
    with pytest.raises(Exception, match="크롤링 오류"):
        await _run_pipeline(CONTENT_ID, URL, USER_ID, "", None)
