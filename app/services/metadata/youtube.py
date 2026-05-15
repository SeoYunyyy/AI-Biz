# app/services/metadata/youtube.py

import httpx
from typing import Optional
import re
import os

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "AIzaSyBDyF4JAoRXlxUkEJ781NyCwk4JK2FdAaU")

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"


def _extract_video_id(url: str) -> Optional[str]:
    """유튜브 URL에서 영상 ID 추출 (다양한 형식 지원)"""
    patterns = [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",   # 일반 URL
        r"youtu\.be/([a-zA-Z0-9_-]{11})",                 # 단축 URL
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",        # 임베드 URL
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",       # 쇼츠 URL
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


async def extract(url: str) -> dict:
    """
    유튜브 URL에서 메타데이터 추출.
    1차: YouTube Data API v3
    폴백: oEmbed API (API 키 불필요)
    """
    video_id = _extract_video_id(url)
    if not video_id:
        return _empty_result(url, error="유튜브 영상 ID를 찾을 수 없습니다")

    # 1차: YouTube Data API
    result = await _fetch_from_api(video_id, url)
    if result:
        return result

    # 폴백: oEmbed API
    result = await _fetch_from_oembed(url)
    if result:
        return result

    return _empty_result(url, error="메타데이터 추출 실패")


async def _fetch_from_api(video_id: str, original_url: str) -> Optional[dict]:
    """YouTube Data API v3로 메타데이터 추출"""
    params = {
        "id": video_id,
        "key": YOUTUBE_API_KEY,
        "part": "snippet",  # 제목, 설명, 썸네일, 날짜 포함
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(YOUTUBE_API_URL, params=params)
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
            "date": snippet.get("publishedAt", "")[:10],  # YYYY-MM-DD만
            "summary": snippet.get("description", "")[:200],
            "category": "영상",
            "tags": snippet.get("tags", [])[:5],  # 최대 5개
            "thumbnail": thumbnail,
            "platform": "youtube",
            "original_url": original_url,
        }

    except httpx.HTTPError:
        return None


async def _fetch_from_oembed(url: str) -> Optional[dict]:
    """oEmbed API로 기본 메타데이터 추출 (API 키 불필요, 폴백용)"""
    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(oembed_url)
            response.raise_for_status()
            data = response.json()

        return {
            "title": data.get("title", ""),
            "date": "",  # oEmbed는 날짜 제공 안 함
            "summary": "",
            "category": "영상",
            "tags": [],
            "thumbnail": data.get("thumbnail_url", ""),
            "platform": "youtube",
            "original_url": url,
        }

    except httpx.HTTPError:
        return None


def _empty_result(url: str, error: str = "") -> dict:
    return {
        "title": "",
        "date": "",
        "summary": "",
        "category": "영상",
        "tags": [],
        "thumbnail": "",
        "platform": "youtube",
        "original_url": url,
        "error": error,
    }
