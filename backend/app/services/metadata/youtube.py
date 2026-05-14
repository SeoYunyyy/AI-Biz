"""유튜브 메타데이터 추출.

1차: oEmbed API (인증 불필요)
2차: yt-dlp 로 설명·길이 등 보충
"""
import httpx
from loguru import logger


def _oembed(url: str) -> dict:
    """YouTube 공식 oEmbed — 제목, 썸네일, 채널명 추출."""
    resp = httpx.get(
        "https://www.youtube.com/oembed",
        params={"url": url, "format": "json"},
        timeout=5,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.json()


def _ytdlp(url: str) -> dict:
    """yt-dlp 로 description, duration 보충."""
    try:
        from yt_dlp import YoutubeDL
        with YoutubeDL({"quiet": True, "skip_download": True, "no_warnings": True}) as ydl:
            return ydl.extract_info(url, download=False) or {}
    except Exception as e:
        logger.warning(f"yt-dlp 실패: {e}")
        return {}


def extract(url: str) -> dict:
    try:
        oe = _oembed(url)
    except Exception as e:
        logger.warning(f"oEmbed 실패: {e}, yt-dlp 단독으로 진행")
        oe = {}

    info = _ytdlp(url)

    title = oe.get("title") or info.get("title", "")
    description = (info.get("description") or "")[:500]

    return {
        "platform": "youtube",
        "title": title,
        "description": description,
        "thumbnail_url": oe.get("thumbnail_url") or info.get("thumbnail"),
        "author": oe.get("author_name") or info.get("uploader"),
        "published_at": info.get("upload_date"),
        "raw_text": (info.get("description") or "")[:1000],
    }
