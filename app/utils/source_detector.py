# app/utils/source_detector.py

from urllib.parse import urlparse


def detect_source_type(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    if "youtube.com" in domain or "youtu.be" in domain:
        return "youtube"

    if "instagram.com" in domain or "tiktok.com" in domain or "x.com" in domain or "twitter.com" in domain:
        return "social"

    if "maps.google" in domain or "map.naver" in domain or "kakaomap" in domain:
        return "map"

    if "blog.naver" in domain or "medium.com" in domain or "tistory.com" in domain:
        return "blog"

    if any(news_domain in domain for news_domain in ["news", "cnn", "bbc", "nytimes", "chosun", "joongang", "hani"]):
        return "article"

    return "webpage"