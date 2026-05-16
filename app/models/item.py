# app/models/item.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    JSON
)

from datetime import datetime

from app.db.database import Base


class Item(Base):
    __tablename__ = "items"

    # 고유 ID
    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # 원본 URL
    source_url = Column(
        Text,
        nullable=False
    )

    # 데이터 유형
    # ex) youtube, article, blog, social ...
    source_type = Column(
        String,
        nullable=False
    )

    # 제목
    title = Column(
        String,
        nullable=True
    )

    # 설명 / 요약 설명
    description = Column(
        Text,
        nullable=True
    )

    # 썸네일 이미지 URL
    thumbnail_url = Column(
        Text,
        nullable=True
    )

    # 작성자 / 채널명 / 기자명
    author = Column(
        String,
        nullable=True
    )

    # 발행일
    published_at = Column(
        String,
        nullable=True
    )

    # 실제 추출된 본문
    content_text = Column(
        Text,
        nullable=True
    )

    # OpenAI 요약 결과
    summary = Column(
        Text,
        nullable=True
    )

    # 태그 리스트
    # ex) ["AI", "마케팅", "Python"]
    tags = Column(
        JSON,
        nullable=True
    )

    # OpenAI embedding 벡터
    # ex) [0.123, -0.532, ...]
    embedding = Column(
        JSON,
        nullable=True
    )

    # 저장 시간
    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )