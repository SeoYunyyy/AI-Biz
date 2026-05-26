# app/services/metadata/naver_blog.py

import httpx
from bs4 import BeautifulSoup
from typing import Optional
import re

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _to_mobile_url(url: str) -> str:
    """네이버 블로그 PC URL을 모바일 URL로 변환 (OG 태그 잘 나옴)"""
    # https://blog.naver.com/아이디/글번호 형식
    match = re.search(r"blog\.naver\.com/([^/]+)/(\d+)", url)
    if match:
        user_id, post_id = match.group(1), match.group(2)
        return f"https://m.blog.naver.com/{user_id}/{post_id}"
    return url


async def extract(url: str) -> dict:
    """
    네이버 블로그 URL에서 메타데이터 추출.
    1차: 모바일 페이지 OG 태그
    폴백: title + meta description
    """
    mobile_url = _to_mobile_url(url)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=10.0
        ) as client:
            response = await client.get(mobile_url, headers=HEADERS)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError as e:
        return _empty_result(url, error=str(e))

    soup = BeautifulSoup(html, "html.parser")

    title = _get_og(soup, "title") or _get_tag_text(soup, "title")
    description = _get_og(soup, "description") or _get_meta(soup, "description")
    thumbnail = _get_og(soup, "image") or ""
    date = _extract_date(soup, html)
    body = _extract_body(soup)

    return {
        "title": _clean(title),
        "date": date,
        "summary": _build_summary(description, body),
        "category": "블로그",
        "tags": [],
        "thumbnail": thumbnail,
        "platform": "naver_blog",
        "original_url": url,
    }


# ── 네이버 블로그 전용 파서 ───────────────────────────────────────────────────

def _extract_body(soup: BeautifulSoup) -> str:
    """네이버 블로그 본문 추출"""
    body_div = (
        soup.find("div", class_=re.compile(r"se-main-container")) or  # 스마트에디터
        soup.find("div", id="postViewArea") or                         # 구버전
        soup.find("div", class_=re.compile(r"post-view"))
    )
    if not body_div:
        return ""
    for tag in body_div.find_all(["script", "style"]):
        tag.decompose()
    text = body_div.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _extract_date(soup: BeautifulSoup, html: str) -> str:
    """날짜 추출"""
    # 1차: span.se_publishDate 또는 class에 date 포함
    date_tag = soup.find("span", class_=re.compile(r"(date|publish)", re.I))
    if date_tag:
        match = re.search(r"(\d{4}[.\-]\d{2}[.\-]\d{2})", date_tag.get_text())
        if match:
            return match.group(1).replace(".", "-")

    # 2차: JSON-LD
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if match:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", match.group(1))
        if date_match:
            return date_match.group(1)

    return ""


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

def _get_og(soup: BeautifulSoup, property: str) -> Optional[str]:
    tag = soup.find("meta", property=f"og:{property}") or \
          soup.find("meta", attrs={"name": f"og:{property}"})
    return tag.get("content") if tag else None


def _get_meta(soup: BeautifulSoup, name: str) -> Optional[str]:
    tag = soup.find("meta", attrs={"name": name})
    return tag.get("content") if tag else None


def _get_tag_text(soup: BeautifulSoup, tag: str) -> Optional[str]:
    el = soup.find(tag)
    return el.get_text(strip=True) if el else None


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _empty_result(url: str, error: str = "") -> dict:
    return {
        "title": "",
        "date": "",
        "summary": "",
        "category": "블로그",
        "tags": [],
        "thumbnail": "",
        "platform": "naver_blog",
        "original_url": url,
        "error": error,
    }


def _build_summary(description: Optional[str], body: str) -> str:
    """OG description + 본문 합쳐서 AI가 읽을 충분한 텍스트 제공"""
    parts = []
    if description:
        parts.append(_clean(description))
    if body:
        # 본문은 1500자까지 (마감기한 정보 놓치지 않게)
        parts.append(body[:1500])
    return " ".join(parts)