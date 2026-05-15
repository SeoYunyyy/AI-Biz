# app/services/metadata/dispatcher.py

import youtube, web, news, naver_blog, map, shopping


def _detect_type(url: str) -> str:
    """URL 보고 어떤 플랫폼인지 판단"""
    url_lower = url.lower()

    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "n.news.naver.com" in url_lower:
        return "naver_news"
    elif "blog.naver.com" in url_lower or "m.blog.naver.com" in url_lower:
        return "naver_blog"
    elif "naver.me" in url_lower:
        return "naver_map"  # 단축 URL은 일단 지도로 분류
    elif "map.naver.com" in url_lower:
        return "naver_map"
    elif "map.kakao.com" in url_lower or "place.map.kakao.com" in url_lower:
        return "kakao_map"
    elif any(x in url_lower for x in ["coupang.com", "smartstore.naver.com", "gmarket.co.kr", "11st.co.kr", "musinsa.com", "ohou.se"]):
        return "shopping"
    else:
        return "web"


async def extract(url: str) -> dict:
    """URL 종류 판단 후 적절한 추출기 실행"""
    platform = _detect_type(url)

    if platform == "youtube":
        return await youtube.extract(url)
    elif platform == "naver_news":
        return await news.extract(url)
    elif platform == "naver_blog":
        return await naver_blog.extract(url)
    elif platform in ("naver_map", "kakao_map"):
        return await map.extract(url)
    elif platform == "shopping":
        return await shopping.extract(url)
    else:
        return await web.extract(url)
