"""SQLAlchemy 모델.

테이블:
  - users    : Supabase Auth와 연동되는 사용자 (id는 auth.users.id와 동일)
  - contents : 저장된 콘텐츠 메타데이터 + 임베딩
  - tags     : 콘텐츠별 태그 (1:N)
  - events   : 사용자 행동 로그 (검색·열람·수정)
"""
from datetime import datetime
import uuid

from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Content(Base):
    __tablename__ = "contents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    url = Column(Text, nullable=False)
    platform = Column(String)             # youtube | naver_blog | general ...

    title = Column(Text)
    description = Column(Text)
    thumbnail_url = Column(Text)

    category = Column(String, index=True) # FOOD | TRAVEL | ...
    summary = Column(Text)
    mood = Column(String, nullable=True)

    # text-embedding-3-small 의 출력 차원 = 1536
    embedding = Column(Vector(1536))

    saved_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_viewed_at = Column(DateTime, nullable=True)
    view_count = Column(Integer, default=0)

    tags = relationship("Tag", back_populates="content", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(UUID(as_uuid=True), ForeignKey("contents.id", ondelete="CASCADE"))
    tag = Column(String, nullable=False, index=True)
    content = relationship("Content", back_populates="tags")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    event_type = Column(String)           # search | view | edit | report
    payload = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
