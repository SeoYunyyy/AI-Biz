# 일반 웹 URL 메타데이터 추출 (OG 태그 기반)

import requests
from bs4 import BeautifulSoup
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


def extract(url: str) -> dict:
    try:
        response = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        response.encoding = response.apparent_encoding
        html = response.text
    except requests.RequestException as e:
        return _empty_result(url, error=str(e))

    soup = BeautifulSoup(html, "html.parser")

    title       = _get_og(soup, "title") or _get_tag_text(soup, "title")
    description = _get_og(soup, "description") or _get_meta(soup, "description")
    thumbnail   = _get_og(soup, "image") or ""
    date        = _get_og(soup, "article:published_time") or _extract_date(soup, html)
    body_text   = _extract_body(soup)
    platform    = "news" if _is_news(soup, body_text) else "web"

    return {
        "title": _clean(title),
        "date": _normalize_date(date),
        "summary": _build_summary(description, body_text),
        "tags": [],
        "thumbnail": thumbnail,
        "platform": platform,
        "original_url": url,
    }


def _is_news(soup: BeautifulSoup, body_text: str) -> bool:
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
    tag = soup.find("meta", property=f"og:{property}") or \
          soup.find("meta", attrs={"name": f"og:{property}"})
    return tag.get("content") if tag else None


def _get_meta(soup: BeautifulSoup, name: str) -> Optional[str]:
    tag = soup.find("meta", attrs={"name": name})
    return tag.get("content") if tag else None


def _get_tag_text(soup: BeautifulSoup, tag: str) -> Optional[str]:
    el = soup.find(tag)
    return el.get_text(strip=True) if el else None


def _extract_body(soup: BeautifulSoup) -> str:
    candidates = (
        soup.find("article") or
        soup.find("div", class_=re.compile(r"(content|article|body|main)", re.I)) or
        soup.find("body")
    )
    if not candidates:
        return ""
    paragraphs = candidates.find_all("p")
    text = " ".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)
    return text[:3500]


def _extract_date(soup: BeautifulSoup, html: str) -> Optional[str]:
    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        return time_tag["datetime"]
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if match:
        return match.group(1)
    return None


def _normalize_date(raw: Optional[str]) -> str:
    if not raw:
        return ""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    return match.group(1) if match else ""


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _build_summary(description: Optional[str], body: str) -> str:
    parts = []
    if description:
        parts.append(_clean(description))
    if body:
        parts.append(body[:1500])
    return " ".join(parts)


def _empty_result(url: str, error: str = "") -> dict:
    return {
        "title": "",
        "date": "",
        "summary": "",
        "tags": [],
        "thumbnail": "",
        "platform": "web",
        "original_url": url,
        "error": error,
    }
