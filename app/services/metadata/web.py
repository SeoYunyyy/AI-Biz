# app/services/metadata/web.py

import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional
import re


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


async def extract(url: str) -> dict:
    """
    일반 웹/뉴스 URL에서 메타데이터 추출.
    1차: OpenGraph 태그
    폴백: <title> + meta description
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=10.0
        ) as client:
            response = await client.get(url, headers=HEADERS)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError as e:
        return _empty_result(url, error=str(e))

    soup = BeautifulSoup(html, "html.parser")

    title = _get_og(soup, "title") or _get_tag_text(soup, "title")
    description = _get_og(soup, "description") or _get_meta(soup, "description")
    thumbnail = _get_og(soup, "image")
    date = _get_og(soup, "article:published_time") or _extract_date(soup, html)

    # 본문 첫 200자 추출 (article > p 우선)
    body_text = _extract_body(soup)

    platform = "news" if _is_news(soup, body_text) else "web"

    return {
        "title": _clean(title),
        "date": _normalize_date(date),
        "summary": _build_summary(description, body_text),
        "category": "웹" if platform == "web" else "뉴스",
        "tags": [],
        "thumbnail": thumbnail or "",
        "platform": platform,
        "original_url": url,
    }


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _is_news(soup: BeautifulSoup, body_text: str) -> bool:
    """
    기사 여부 판단. 아래 중 하나라도 해당되면 news로 분류.
    1. og:type = "article"
    2. article:author 메타태그 존재
    3. 본문에 "OOO기자" 패턴
    4. 본문에 "기사원문" 텍스트
    """
    og_type = soup.find("meta", property="og:type")
    if og_type and og_type.get("content", "").lower() == "article":
        return True

    article_author = (
        soup.find("meta", property="article:author") or
        soup.find("meta", attrs={"name": "article:author"})
    )
    if article_author:
        return True

    if re.search(r"[\w가-힣]+\s*기자", body_text):
        return True

    if "기사원문" in body_text:
        return True

    return False


def _get_og(soup: BeautifulSoup, property: str) -> Optional[str]:
    """<meta property="og:X"> 또는 <meta name="og:X"> 에서 content 추출"""
    tag = soup.find("meta", property=f"og:{property}") or \
          soup.find("meta", attrs={"name": f"og:{property}"})
    return tag.get("content") if tag else None


def _get_meta(soup: BeautifulSoup, name: str) -> Optional[str]:
    """<meta name="description" content="..."> 추출"""
    tag = soup.find("meta", attrs={"name": name})
    return tag.get("content") if tag else None


def _get_tag_text(soup: BeautifulSoup, tag: str) -> Optional[str]:
    el = soup.find(tag)
    return el.get_text(strip=True) if el else None


def _extract_body(soup: BeautifulSoup) -> str:
    """본문 텍스트 추출: article > p 순서로 시도, 폴백으로 body 전체 p 태그"""
    candidates = (
        soup.find("article") or
        soup.find("div", class_=re.compile(r"(content|article|body|main)", re.I)) or
        soup.find("body")
    )
    if not candidates:
        return ""
    paragraphs = candidates.find_all("p")
    text = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)
    return text[:3500]  # ai_classifier에 넘길 여유분 포함


def _extract_date(soup: BeautifulSoup, html: str) -> Optional[str]:
    """OG 날짜 없을 때: <time datetime=""> 또는 JSON-LD에서 datePublished 추출"""
    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        return time_tag["datetime"]

    # JSON-LD에서 datePublished 찾기
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if match:
        return match.group(1)

    return None


def _normalize_date(raw: Optional[str]) -> str:
    """ISO 8601 or 유사 형식을 YYYY-MM-DD로 정규화"""
    if not raw:
        return ""
    # 날짜 부분(YYYY-MM-DD)만 추출
    match = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    return match.group(1) if match else ""


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _empty_result(url: str, error: str = "") -> dict:
    return {
        "title": "",
        "date": "",
        "summary": "",
        "category": "웹",
        "tags": [],
        "thumbnail": "",
        "platform": "web",
        "original_url": url,
        "error": error,
    }


def _build_summary(description: Optional[str], body: str) -> str:
    parts = []
    if description:
        parts.append(_clean(description))
    if body:
        parts.append(body[:1500])
    return " ".join(parts)