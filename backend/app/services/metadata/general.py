"""일반 웹/뉴스 — OpenGraph 우선, 폴백으로 <title>/<meta description>."""
import httpx
from bs4 import BeautifulSoup
from loguru import logger


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SNSArchiveBot/0.1; "
        "+https://github.com/sns-archive-team/sns-archive)"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def _get_meta(soup: BeautifulSoup, prop: str) -> str | None:
    """og:title, description 등 메타 태그 값 추출."""
    el = soup.find("meta", attrs={"property": prop}) \
        or soup.find("meta", attrs={"name": prop})
    return el.get("content") if el else None


def extract(url: str) -> dict:
    try:
        resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"HTTP 실패 {url}: {e}")
        return {
            "platform": "general", "title": "", "description": None,
            "thumbnail_url": None, "author": None,
            "published_at": None, "raw_text": None,
        }

    soup = BeautifulSoup(resp.text, "html.parser")

    title = _get_meta(soup, "og:title") or (
        soup.title.string.strip() if soup.title and soup.title.string else ""
    )
    description = _get_meta(soup, "og:description") or _get_meta(soup, "description") or ""
    thumbnail = _get_meta(soup, "og:image")
    author = _get_meta(soup, "article:author") or _get_meta(soup, "author")
    published = _get_meta(soup, "article:published_time")

    # 본문 첫 500자 폴백 — RAG·임베딩 품질 향상
    raw_text = ""
    article = soup.find("article") or soup.find("main") or soup.body
    if article:
        raw_text = article.get_text(separator=" ", strip=True)[:500]

    return {
        "platform": "general",
        "title": title,
        "description": (description or "")[:500],
        "thumbnail_url": thumbnail,
        "author": author,
        "published_at": published,
        "raw_text": raw_text,
    }
