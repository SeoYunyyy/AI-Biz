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
    thumbnail = _get_og(soup, "image") or ""
    body = _extract_naver_body(soup)
    date = _extract_naver_date(soup, html)

    return {
        "title": _clean(title),
        "date": date,
        "summary": body[:3500] if body else "",
        "category": "뉴스",
        "tags": [],
        "thumbnail": thumbnail,
        "platform": "naver_news",
        "original_url": url,
    }


def _extract_naver_body(soup: BeautifulSoup) -> str:
    body_div = (
        soup.find("div", id="dic_area") or
        soup.find("div", id="newsct_article") or
        soup.find("div", class_="newsct_article") or
        soup.find("article")
    )
    if not body_div:
        return ""
    for tag in body_div.find_all(["script", "style", "figure"]):
        tag.decompose()
    text = body_div.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _extract_naver_date(soup: BeautifulSoup, html: str) -> str:
    date_tag = soup.find("span", attrs={"data-date-time": True}) or \
               soup.find("em", class_=re.compile(r"datestamp"))
    if date_tag:
        raw = date_tag.get("data-date-time") or date_tag.get_text(strip=True)
        match = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
        if match:
            return match.group(1)
    span = soup.find("span", class_=re.compile(r"datestamp"))
    if span:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", span.get_text())
        if match:
            return match.group(1)
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if match:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", match.group(1))
        if date_match:
            return date_match.group(1)
    return ""


def _get_og(soup: BeautifulSoup, property: str) -> Optional[str]:
    tag = soup.find("meta", property=f"og:{property}") or \
          soup.find("meta", attrs={"name": f"og:{property}"})
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
        "title": "", "date": "", "summary": "", "category": "뉴스",
        "tags": [], "thumbnail": "", "platform": "naver_news",
        "original_url": url, "error": error,
    }
