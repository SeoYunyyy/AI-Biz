# 쇼핑몰 URL 상품 메타데이터 추출 (OG 태그 + 가격 파싱)

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
    except requests.RequestException as e:
        return _empty_result(url, error=str(e))

    soup = BeautifulSoup(html, "html.parser")

    title       = _get_og(soup, "title") or _get_tag_text(soup, "title")
    description = _get_og(soup, "description") or _get_meta(soup, "description")
    thumbnail   = _get_og(soup, "image") or ""
    price       = _extract_price(soup, html)
    platform    = _detect_platform(url)

    summary = ""
    if price:
        summary = f"{price}원"
    elif description:
        summary = _clean(description)

    return {
        "title": _clean(title),
        "date": "",
        "summary": summary,
        "tags": [],
        "thumbnail": thumbnail,
        "platform": platform,
        "original_url": url,
    }


def _extract_price(soup: BeautifulSoup, html: str) -> Optional[str]:
    price_tag = soup.find("meta", property="product:price:amount") or \
                soup.find("meta", property="og:price:amount")
    if price_tag:
        return price_tag.get("content")

    match = re.search(r'"price"\s*:\s*"?(\d[\d,\.]+)"?', html)
    if match:
        return match.group(1)

    price_el = soup.find(class_=re.compile(r"(price|가격)", re.I))
    if price_el:
        text = price_el.get_text(strip=True)
        match = re.search(r"(\d[\d,]+)", text)
        if match:
            return match.group(1)

    return None


def _detect_platform(url: str) -> str:
    if "coupang.com" in url:
        return "coupang"
    elif "smartstore.naver.com" in url:
        return "naver_store"
    elif "gmarket.co.kr" in url:
        return "gmarket"
    elif "11st.co.kr" in url:
        return "11st"
    elif "musinsa.com" in url:
        return "musinsa"
    elif "ohou.se" in url:
        return "ohouse"
    return "shopping"


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
        "platform": "shopping",
        "original_url": url,
        "error": error,
    }
