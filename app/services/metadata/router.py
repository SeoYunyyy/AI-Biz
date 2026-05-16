# app/services/metadata/router.py

from app.services.metadata.youtube import get_youtube_metadata
from app.services.metadata.webpage import get_webpage_metadata
from app.services.metadata.article import get_article_metadata
from app.services.metadata.blog import get_blog_metadata
from app.services.metadata.map import get_map_metadata
from app.services.metadata.social import get_social_metadata


async def get_metadata(source_type: str, url: str) -> dict:
    if source_type == "youtube":
        return await get_youtube_metadata(url)

    if source_type == "article":
        return await get_article_metadata(url)

    if source_type == "blog":
        return await get_blog_metadata(url)

    if source_type == "map":
        return await get_map_metadata(url)

    if source_type == "social":
        return await get_social_metadata(url)

    return await get_webpage_metadata(url)