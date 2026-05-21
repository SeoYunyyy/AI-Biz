# app/services/content/extractor.py

import httpx
from bs4 import BeautifulSoup


async def extract_content(source_type: str, url: str) -> str:
    if source_type == "youtube":
        return "YouTube transcript extraction will be added later."

    if source_type == "map":
        return "Map URL does not usually provide long text content."

    if source_type == "social":
        return "Social media content extraction is limited."

    return await extract_webpage_text(url)


async def extract_webpage_text(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, timeout=10)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    return text