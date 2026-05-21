# ── URL 콘텐츠 수집 ──

import requests
from bs4 import BeautifulSoup


def fetch_url_content(url: str) -> dict:
    # 유튜브는 oEmbed API로 정확한 메타데이터 수집
    if 'youtube.com' in url or 'youtu.be' in url:
        oembed = requests.get(
            f'https://www.youtube.com/oembed?url={url}&format=json', timeout=5
        )
        if oembed.status_code == 200:
            data = oembed.json()
            return {
                'title': data.get('title', ''),
                'text': f"채널: {data.get('author_name', '')}",
                'url': url
            }

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, 'lxml')

    title = (soup.title.get_text() or '').strip() if soup.title else ''

    og_desc = soup.find('meta', property='og:description')
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    description = (
        og_desc.get('content', '') if og_desc
        else meta_desc.get('content', '') if meta_desc
        else ''
    )

    paragraphs = ' '.join(p.get_text() for p in soup.find_all('p'))[:2000]

    return {'title': title, 'text': f"{description} {paragraphs}".strip(), 'url': url}

# YouTube oEmbed 또는 일반 HTML 파싱으로 URL의 제목·본문 추출
