"""URL → 적절한 추출기 선택.

각 추출기는 동일한 dict 형식을 반환:
{
    "platform": str,
    "title": str,
    "description": str | None,
    "thumbnail_url": str | None,
    "author": str | None,
    "published_at": str | None,
    "raw_text": str | None,
}
"""
from urllib.parse import urlparse

from app.services.metadata import youtube, naver_blog, general


def extract_metadata(url: str) -> dict:
    host = urlparse(url).netloc.lower()

    if "youtube.com" in host or "youtu.be" in host:
        return youtube.extract(url)
    if "blog.naver.com" in host or "m.blog.naver.com" in host:
        return naver_blog.extract(url)

    # 기본: OpenGraph 일반 추출
    return general.extract(url)
