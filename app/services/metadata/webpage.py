# app/services/metadata/webpage.py

import httpx
from bs4 import BeautifulSoup


async def get_webpage_metadata(url: str) -> dict:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, timeout=10)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    title = None
    description = None
    thumbnail_url = None

    if soup.title:
        title = soup.title.string

    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag:
        description = desc_tag.get("content")

    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_image = soup.find("meta", property="og:image")

    if og_title:
        title = og_title.get("content")

    if og_desc:
        description = og_desc.get("content")

    if og_image:
        thumbnail_url = og_image.get("content")

    return {
        "title": title,
        "description": description,
        "thumbnail_url": thumbnail_url,
        "author": None,
        "published_at": None,
    }