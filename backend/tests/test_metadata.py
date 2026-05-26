"""메타데이터 추출 단위 테스트.

실행: pytest tests/test_metadata.py -v
"""
import pytest

from app.services.metadata.router import extract_metadata


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
])
def test_youtube_extraction(url):
    result = extract_metadata(url)
    assert result["platform"] == "youtube"
    assert result["title"]  # 비어있지 않음
    assert result["thumbnail_url"]


@pytest.mark.parametrize("url", [
    "https://www.naver.com/",
])
def test_general_extraction(url):
    result = extract_metadata(url)
    assert result["platform"] == "general"
    assert "title" in result


def test_required_keys():
    """모든 추출기는 동일한 키 셋을 반환해야 한다."""
    required = {"platform", "title", "description", "thumbnail_url",
                "author", "published_at", "raw_text"}
    result = extract_metadata("https://example.com")
    assert required.issubset(result.keys())
