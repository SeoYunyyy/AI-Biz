# app/services/metadata/naver_sports.py
# Naver Sports 페이지 메타데이터 추출
# sports.naver.com은 서버사이드 렌더링이지만 본문이 <p> 대신 <span>/<div>로 구성됨.
# OG 태그(제목·썸네일) + article.get_text()로 본문 추출.

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
            # 바이트로 받아서 utf-8 디코딩 (httpx 자동 인코딩 오류 방지)
            html = response.content.decode("utf-8", errors="replace")
    except httpx.HTTPError as e:
        return _empty_result(url, error=str(e))

    soup = BeautifulSoup(html, "html.parser")

    # OG 태그에서 제목·썸네일 추출
    title = _get_og(soup, "title") or _get_tag_text(soup, "title") or ""
    thumbnail = _get_og(soup, "image") or ""
    date = _extract_date(html)

    # 본문: Naver Sports는 <p> 없이 <span>/<div>에 내용이 있으므로 article get_text() 사용
    body = _extract_body(soup)

    return {
        "title": _clean(title),
        "date": date,
        "summary": body,
        "category": "스포츠",
        "tags": [],
        "thumbnail": thumbnail,
        "platform": "naver_news",   # Supabase content_type 제약: naver_sports 미허용 → naver_news 사용
        "original_url": url,
    }


def _extract_body(soup: BeautifulSoup) -> str:
    """Naver Sports 본문 추출: <article> → <p> 없음 → get_text() 사용"""
    article = (
        soup.find("article", id="comp_news_article") or
        soup.find("article", class_=re.compile(r"article", re.I)) or
        soup.find("div", id="comp_news_article")
    )
    if not article:
        return ""
    # 광고·스크립트 제거
    for tag in article.find_all(["script", "style", "figure"]):
        tag.decompose()
    text = article.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()[:3500]


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
        "platform": "naver_news",
        "original_url": url,
        "error": error,
    }

# OG 태그로 제목·썸네일, article.get_text()로 본문 추출 (p 태그 없는 Naver Sports 구조 대응)
