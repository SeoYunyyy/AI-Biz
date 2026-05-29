# 카카오맵 / 네이버지도 URL 장소 메타데이터 추출

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
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def extract(url: str) -> dict:
    try:
        response = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        response.encoding = response.apparent_encoding
        html = response.text
        final_url = response.url
    except requests.RequestException as e:
        return _empty_result(url, error=str(e))

    soup = BeautifulSoup(html, "html.parser")

    title       = _get_og(soup, "title") or _get_tag_text(soup, "title")
    description = _get_og(soup, "description") or _get_meta(soup, "description")
    thumbnail   = _get_og(soup, "image") or ""

    place_name, address = _parse_place_info(title, description)
    platform = _detect_platform(str(final_url))

    return {
        "title": place_name or _clean(title),
        "date": "",
        "summary": address or _clean(description),
        "tags": [],
        "thumbnail": thumbnail,
        "platform": platform,
        "original_url": url,
    }


def _parse_place_info(title: Optional[str], description: Optional[str]):
    place_name = _clean(title) if title else ""
    address = ""
    if description:
        desc = _clean(description)
        for sep in [" · ", " : ", " | "]:
            if sep in desc:
                parts = desc.split(sep, 1)
                if not place_name:
                    place_name = parts[0].strip()
                address = parts[1].strip()
                break
        if not address:
            address = desc
    return place_name, address


def _detect_platform(url: str) -> str:
    if "naver" in url:
        return "naver_map"
    elif "kakao" in url:
        return "kakao_map"
    return "map"


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


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _empty_result(url: str, error: str = "") -> dict:
    return {
        "title": "",
        "date": "",
        "summary": "",
        "tags": [],
        "thumbnail": "",
        "platform": "map",
        "original_url": url,
        "error": error,
    }
