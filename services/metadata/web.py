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
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
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

    title = _get_og(soup, "title") or _get_tag_text(soup, "title")
    description = _get_og(soup, "description") or _get_meta(soup, "description")
    thumbnail = _get_og(soup, "image")
    date = _get_og(soup, "article:published_time") or _extract_date(soup, html)
    body_text = _extract_body(soup)

    return {
        "title": _clean(title),
        "date": _normalize_date(date),
        "summary": _build_summary(description, body_text),
        "category": "웹",
        "tags": [],
        "thumbnail": thumbnail or "",
        "platform": "web",
        "original_url": url,
    }


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


def _empty_result(url: str, error: str = "") -> dict:
    return {
        "title": "", "date": "", "summary": "", "category": "웹",
        "tags": [], "thumbnail": "", "platform": "web",
        "original_url": url, "error": error,
    }


def _build_summary(description: Optional[str], body: str) -> str:
    parts = []
    if description:
        parts.append(_clean(description))
    if body:
        parts.append(body[:1500])
    return " ".join(parts)
