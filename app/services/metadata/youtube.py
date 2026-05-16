# app/services/metadata/youtube.py

import re
import httpx
from typing import Optional

from app.utils.config import YOUTUBE_API_KEY
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"

def extract_video_id(url: str) -> Optional[str]:
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


async def get_youtube_metadata(url: str) -> dict:
    video_id = extract_video_id(url)

    if not video_id:
        return {
            "title": None,
            "description": None,
            "thumbnail_url": None,
            "author": None,
            "published_at": None,
        }

    if not YOUTUBE_API_KEY:
        return {
            "title": "YouTube Video",
            "description": "YouTube API key is missing.",
            "thumbnail_url": None,
            "author": None,
            "published_at": None,
        }

    params = {
        "part": "snippet",
        "id": video_id,
        "key": YOUTUBE_API_KEY,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(YOUTUBE_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

    items = data.get("items", [])

    if not items:
        return {
            "title": None,
            "description": None,
            "thumbnail_url": None,
            "author": None,
            "published_at": None,
        }

    snippet = items[0]["snippet"]

    return {
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url"),
        "author": snippet.get("channelTitle"),
        "published_at": snippet.get("publishedAt"),
    }