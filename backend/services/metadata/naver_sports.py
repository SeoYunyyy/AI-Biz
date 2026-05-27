# app/services/metadata/naver_sports.py
# Naver Sports 페이지 메타데이터 추출
# sports.naver.com은 JS 클라이언트 렌더링 방식이라 본문을 직접 파싱 불가.
# OG 태그에 의존하고, 유니코드 이스케이프 문자열을 디코딩해서 반환.

import httpx
import re
from bs4 import BeautifulSoup
from typing import Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


async def extract(url: str) -> dict:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.get(url, headers=HEADERS)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError as e:
        return _empty_result(url, error=str(e))

    soup = BeautifulSoup(html, "html.parser")

    # OG 태그에서 제목·설명·썸네일 추출 (JS 렌더링 전에도 meta 태그는 존재)
    title = _get_og(soup, "title") or _get_tag_text(soup, "title") or ""
    description = _get_og(soup, "description") or ""
    thumbnail = _get_og(soup, "image") or ""
    date = _extract_date(html)

    return {
        "title": _decode_unicode(_clean(title)),
        "date": date,
        "summary": _decode_unicode(_clean(description)),
        "category": "스포츠",
        "tags": [],
        "thumbnail": thumbnail,
        "platform": "naver_sports",
        "original_url": url,
    }


def _decode_unicode(text: str) -> str:
    """\\uXXXX 형태의 유니코드 이스케이프를 실제 한글로 변환"""
    try:
        return re.sub(
            r'\\u([0-9a-fA-F]{4})',
            lambda m: chr(int(m.group(1), 16)),
            text
        )
    except Exception:
        return text


def _get_og(soup: BeautifulSoup, property: str) -> Optional[str]:
    tag = (
        soup.find("meta", property=f"og:{property}") or
        soup.find("meta", attrs={"name": f"og:{property}"})
    )
    return tag.get("content") if tag else None


def _get_tag_text(soup: BeautifulSoup, tag: str) -> Optional[str]:
    el = soup.find(tag)
    return el.get_text(strip=True) if el else None


def _extract_date(html: str) -> str:
    """JSON-LD 또는 패턴 매칭으로 날짜 추출"""
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if match:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", match.group(1))
        if date_match:
            return date_match.group(1)
    match = re.search(r'(\d{4}\.\d{2}\.\d{2})', html)
    if match:
        return match.group(1).replace(".", "-")
    return ""


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _empty_result(url: str, error: str = "") -> dict:
    return {
        "title": "",
        "date": "",
        "summary": "",
        "category": "스포츠",
        "tags": [],
        "thumbnail": "",
        "platform": "naver_sports",
        "original_url": url,
        "error": error,
    }

# OG 태그 기반으로 제목·요약 추출 후 유니코드 이스케이프(\uXXXX) 디코딩하여 한글 복원
