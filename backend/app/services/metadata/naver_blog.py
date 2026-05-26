"""네이버 블로그 — 모바일 페이지의 OpenGraph 사용 (메타가 더 풍부함).

PC 페이지의 iframe 구조는 까다로워서 m.blog.naver.com 으로 변환 후 처리.
"""
import re

from app.services.metadata.general import extract as general_extract


def _to_mobile(url: str) -> str:
    """blog.naver.com → m.blog.naver.com 변환."""
    return re.sub(r"^https?://blog\.naver\.com", "https://m.blog.naver.com", url)


def extract(url: str) -> dict:
    mobile_url = _to_mobile(url)
    result = general_extract(mobile_url)
    result["platform"] = "naver_blog"
    return result
