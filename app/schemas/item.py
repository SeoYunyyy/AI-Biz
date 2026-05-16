# app/schemas/item.py

from pydantic import BaseModel, HttpUrl
from typing import Optional, List


class ItemCreate(BaseModel):
    url: HttpUrl


class ItemResponse(BaseModel):
    id: int
    source_url: str
    source_type: str
    title: Optional[str]
    description: Optional[str]
    thumbnail_url: Optional[str]
    summary: Optional[str]
    tags: Optional[List[str]]

    class Config:
        from_attributes = True