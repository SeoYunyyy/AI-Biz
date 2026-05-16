# app/services/metadata/article.py

import httpx
from bs4 import BeautifulSoup


async def get_article_metadata(url: str) -> dict:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, timeout=10)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    title = None
    description = None
    thumbnail_url = None
    author = None
    published_at = None

    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_image = soup.find("meta", property="og:image")

    author_tag = soup.find("meta", attrs={"name": "author"})
    published_tag = soup.find("meta", property="article:published_time")

    if og_title:
        title = og_title.get("content")
    elif soup.title:
        title = soup.title.string

    if og_desc:
        description = og_desc.get("content")

    if og_image:
        thumbnail_url = og_image.get("content")

    if author_tag:
        author = author_tag.get("content")

    if published_tag:
        published_at = published_tag.get("content")

    return {
        "title": title,
        "description": description,
        "thumbnail_url": thumbnail_url,
        "author": author,
        "published_at": published_at,
    }