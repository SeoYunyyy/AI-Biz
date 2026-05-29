# 유튜브 URL 메타데이터 추출 (YouTube Data API v3 → oEmbed 폴백)

import requests
import re
import os
from typing import Optional

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"


def _extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract(url: str) -> dict:
    video_id = _extract_video_id(url)
    if not video_id:
        return _empty_result(url, error="유튜브 영상 ID를 찾을 수 없습니다")

    result = _fetch_from_api(video_id, url)
    if result:
        return result

    result = _fetch_from_oembed(url)
    if result:
        return result

    return _empty_result(url, error="메타데이터 추출 실패")


def _fetch_from_api(video_id: str, original_url: str) -> Optional[dict]:
    if not YOUTUBE_API_KEY:
        return None
    try:
        response = requests.get(
            YOUTUBE_API_URL,
            params={"id": video_id, "key": YOUTUBE_API_KEY, "part": "snippet"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        if not items:
            return None
        snippet = items[0]["snippet"]
        thumbnails = snippet.get("thumbnails", {})
        thumbnail = (
            thumbnails.get("maxres", {}).get("url") or
            thumbnails.get("high", {}).get("url") or
            thumbnails.get("medium", {}).get("url") or ""
        )
        return {
            "title": snippet.get("title", ""),
            "date": snippet.get("publishedAt", "")[:10],
            "summary": snippet.get("description", "")[:3500],
            "tags": snippet.get("tags", [])[:5],
            "thumbnail": thumbnail,
            "platform": "youtube",
            "original_url": original_url,
        }
    except Exception:
        return None


def _fetch_from_oembed(url: str) -> Optional[dict]:
    try:
        response = requests.get(
            f"https://www.youtube.com/oembed?url={url}&format=json",
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "title": data.get("title", ""),
            "date": "",
            "summary": "",
            "tags": [],
            "thumbnail": data.get("thumbnail_url", ""),
            "platform": "youtube",
            "original_url": url,
        }
    except Exception:
        return None


def _empty_result(url: str, error: str = "") -> dict:
    return {
        "title": "",
        "date": "",
        "summary": "",
        "tags": [],
        "thumbnail": "",
        "platform": "youtube",
        "original_url": url,
        "error": error,
    }
