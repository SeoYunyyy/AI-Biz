# ── URL 콘텐츠 수집 ──

import requests
from bs4 import BeautifulSoup


def detect_platform(url: str) -> str:
    # URL 패턴으로 contents_content_type_check 제약 허용값 결정
    u = url.lower()
    if 'youtube.com' in u or 'youtu.be' in u:
        return 'youtube'
    if 'blog.naver.com' in u:
        return 'naver_blog'
    if 'news.naver.com' in u or 'n.news.naver.com' in u:
        return 'naver_news'
    if 'map.naver.com' in u or 'place.naver.com' in u:
        return 'naver_map'
    if 'map.kakao.com' in u or 'place.map.kakao.com' in u:
        return 'kakao_map'
    if 'coupang.com' in u or 'smartstore.naver.com' in u or 'shopping.naver.com' in u:
        return 'shopping'
    return 'web'


def fetch_url_content(url: str) -> dict:
    platform = detect_platform(url)

    # 유튜브는 oEmbed API로 정확한 메타데이터 수집
    if platform == 'youtube':
        oembed = requests.get(
            f'https://www.youtube.com/oembed?url={url}&format=json', timeout=5
        )
        if oembed.status_code == 200:
            data = oembed.json()
            return {
                'title': data.get('title', ''),
                'text': f"채널: {data.get('author_name', '')}",
                'url': url,
                'thumbnail': data.get('thumbnail_url', ''),
                'platform': platform,
            }

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, 'lxml')

    title = (soup.title.get_text() or '').strip() if soup.title else ''

    og_desc  = soup.find('meta', property='og:description')
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    description = (
        og_desc.get('content', '') if og_desc
        else meta_desc.get('content', '') if meta_desc
        else ''
    )

    og_image     = soup.find('meta', property='og:image')
    twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
    thumbnail = (
        og_image.get('content', '') if og_image
        else twitter_image.get('content', '') if twitter_image
        else ''
    )

    paragraphs = ' '.join(p.get_text() for p in soup.find_all('p'))[:2000]

    return {
        'title': title,
        'text': f"{description} {paragraphs}".strip(),
        'url': url,
        'thumbnail': thumbnail,
        'platform': platform,
    }

# YouTube oEmbed 또는 일반 HTML 파싱으로 URL의 제목·본문·썸네일 추출
