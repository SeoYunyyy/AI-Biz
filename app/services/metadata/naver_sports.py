# app/services/metadata/naver_sports.py

import httpx
from bs4 import BeautifulSoup
from typing import Optional
import re

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://m.sports.naver.com/",
}

# 스포츠 종목 → 카테고리 레이블
_SPORT_LABELS = {
    "kbaseball": "야구",
    "baseball":  "야구",
    "basketball": "농구",
    "football":  "축구",
    "soccer":    "축구",
    "golf":      "골프",
    "tennis":    "테니스",
    "esports":   "e스포츠",
    "volleyball": "배구",
    "badminton": "배드민턴",
    "swim":      "수영",
    "athletics": "육상",
    "hockey":    "하키",
    "boxing":    "권투",
}


def _sport_label(url: str) -> str:
    """URL 경로에서 종목명 추출"""
    for key, label in _SPORT_LABELS.items():
        if f"/{key}/" in url or f"/{key}" == url.split("?")[0].rstrip("/").rsplit("/", 2)[-2]:
            return label
    return "스포츠"


async def extract(url: str) -> dict:
    """
    네이버 스포츠 기사 URL에서 메타데이터 추출.
    1차: OG 태그 (제목, 썸네일)
    2차: 본문 크롤링 (기사 내용, 날짜)
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0
        ) as client:
            response = await client.get(url, headers=HEADERS)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPError as e:
        return _empty_result(url, error=str(e))

    soup = BeautifulSoup(html, "html.parser")

    title = _get_og(soup, "title") or _get_tag_text(soup, "title") or ""
    thumbnail = _get_og(soup, "image") or ""
    description = _get_og(soup, "description") or ""

    body = _extract_body(soup)
    date = _extract_date(soup, html)
    sport = _sport_label(url)

    summary = description
    if body and len(body) > len(description):
        summary = body[:3500]

    return {
        "title": _clean(title),
        "date": date,
        "summary": summary,
        "category": "스포츠",
        "tags": [sport] if sport != "스포츠" else [],
        "thumbnail": thumbnail,
        "platform": "naver_sports",
        "original_url": url,
    }


# ── 네이버 스포츠 전용 파서 ───────────────────────────────────────────────────

def _extract_body(soup: BeautifulSoup) -> str:
    """네이버 스포츠 기사 본문 추출"""
    body_div = (
        soup.find("div", id="newsEndContents") or          # 모바일 스포츠
        soup.find("div", class_=re.compile(r"news_end")) or
        soup.find("div", id="articeBody") or               # 일부 스포츠 기사
        soup.find("div", class_=re.compile(r"article_body")) or
        soup.find("div", id="dic_area") or                 # 일반 뉴스 구조 폴백
        soup.find("article")
    )
    if not body_div:
        # OG description만 있을 때 폴백 — 최소한 제목+설명은 넘겨줌
        return ""

    for tag in body_div.find_all(["script", "style", "figure", "aside"]):
        tag.decompose()

    text = body_div.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _extract_date(soup: BeautifulSoup, html: str) -> str:
    # 1차: <span class="info_date"> 또는 data-date-time 속성
    date_tag = (
        soup.find("span", attrs={"data-date-time": True}) or
        soup.find("span", class_=re.compile(r"info_date|date_info|news_date", re.I)) or
        soup.find("em", class_=re.compile(r"datestamp", re.I)) or
        soup.find("time", attrs={"datetime": True})
    )
    if date_tag:
        raw = (date_tag.get("data-date-time") or
               date_tag.get("datetime") or
               date_tag.get_text(strip=True))
        m = re.search(r"(\d{4}[.\-]\d{2}[.\-]\d{2})", raw or "")
        if m:
            return m.group(1).replace(".", "-")

    # 2차: JSON-LD
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if m:
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", m.group(1))
        if dm:
            return dm.group(1)

    # 3차: OG 날짜 메타
    og_date = soup.find("meta", property="article:published_time")
    if og_date:
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", og_date.get("content", ""))
        if dm:
            return dm.group(1)

    return ""


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _get_og(soup: BeautifulSoup, property: str) -> Optional[str]:
    tag = (soup.find("meta", property=f"og:{property}") or
           soup.find("meta", attrs={"name": f"og:{property}"}))
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
        "category": "스포츠",
        "tags": [],
        "thumbnail": "",
        "platform": "naver_sports",
        "original_url": url,
        "error": error,
    }
