# app/services/metadata/dispatcher.py

import httpx
from app.services.metadata import youtube, web, news, naver_blog, map, shopping

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _detect_type(url: str) -> str:
    url_lower = url.lower()

    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "n.news.naver.com" in url_lower:
        return "naver_news"
    elif "blog.naver.com" in url_lower or "m.blog.naver.com" in url_lower:
        return "naver_blog"
    elif "map.naver.com" in url_lower:
        return "naver_map"
    elif "map.kakao.com" in url_lower or "place.map.kakao.com" in url_lower:
        return "kakao_map"
    elif any(x in url_lower for x in ["coupang.com", "smartstore.naver.com", "gmarket.co.kr", "11st.co.kr", "musinsa.com", "ohou.se"]):
        return "shopping"
    elif any(x in url_lower for x in [
        "jtbc.co.kr", "sbs.co.kr", "kbs.co.kr", "mbc.co.kr",
        "chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr",
        "khan.co.kr", "yonhapnews.co.kr", "yna.co.kr", "newsis.com",
        "news1.kr", "heraldcorp.com", "mt.co.kr", "hankyung.com",
        "sedaily.com", "etnews.com", "zdnet.co.kr"
    ]):
        return "news"
    else:
        return "web"


async def _resolve_url(url: str) -> str:
    """단축 URL(naver.me 등)의 실제 목적지 URL을 반환. 실패 시 원본 반환."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=8.0, headers=_HEADERS
        ) as client:
            resp = await client.head(url)
            return str(resp.url)
    except Exception:
        return url


async def extract(url: str) -> dict:
    """URL 종류 판단 후 적절한 추출기 실행"""
    # naver.me 단축 URL은 리다이렉트 목적지를 먼저 확인
    resolved = await _resolve_url(url) if "naver.me" in url.lower() else url
    platform = _detect_type(resolved)

    if platform == "youtube":
        return await youtube.extract(resolved)
    elif platform == "naver_news":
        return await news.extract(resolved)
    elif platform == "naver_blog":
        return await naver_blog.extract(resolved)
    elif platform in ("naver_map", "kakao_map"):
        return await map.extract(url)   # 지도는 원본 단축 URL 유지
    elif platform == "shopping":
        return await shopping.extract(resolved)
    elif platform == "news":
        return await news.extract(resolved)
    else:
        return await web.extract(resolved)
