"""
기존 Supabase contents 테이블 매핑 모델
(Next.js 프로토타입에서 사용 중인 테이블 그대로 읽기)
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB

from database import Base


class Content(Base):
    __tablename__ = "contents"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(UUID(as_uuid=True), nullable=False)
    url             = Column(Text, nullable=False)
    title           = Column(String)
    description     = Column(Text)
    thumbnail_url   = Column(Text)
    author          = Column(String)
    content_type    = Column(String)          # "youtube" | "blog" | "other"
    topics          = Column(ARRAY(String))   # AI 분석 결과
    moods           = Column(ARRAY(String))
    intent          = Column(ARRAY(String))
    hashtags        = Column(ARRAY(String))
    energy          = Column(String)
    analysis_status = Column(String)          # "pending" | "completed" | "failed"
    collection_id   = Column(UUID(as_uuid=True), nullable=True)
    meta_data       = Column("metadata", JSONB, nullable=True)  # 'metadata'는 SQLAlchemy 예약어라 속성명만 변경
    saved_at        = Column(DateTime(timezone=True), default=datetime.utcnow)
    analyzed_at     = Column(DateTime(timezone=True), nullable=True)
