import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class Item(Base):
    """아이템 정의 테이블 (12개 카테고리 아이템 고정 데이터)"""
    __tablename__ = "items"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name        = Column(String, nullable=False)          # "커피컵"
    category    = Column(String, nullable=False, unique=True)  # "카페/음료"
    emoji       = Column(String)                          # "☕"
    description = Column(String)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)

    user_items = relationship("UserItem", back_populates="item")


class UserCategoryCount(Base):
    """사용자별 카테고리 저장 카운트 (아이템 지급 조건 추적용)"""
    __tablename__ = "user_category_counts"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id      = Column(UUID(as_uuid=True), nullable=False)
    category     = Column(String, nullable=False)
    count        = Column(Integer, default=1)
    last_updated = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_category"),
    )


class UserItem(Base):
    """사용자 보유 아이템 (pending: 미수령 / claimed: 수령 완료)"""
    __tablename__ = "user_items"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), nullable=False)
    item_id    = Column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)
    category   = Column(String, nullable=False)
    status     = Column(String, default="pending")   # "pending" | "claimed"
    earned_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    claimed_at = Column(DateTime(timezone=True), nullable=True)

    item = relationship("Item", back_populates="user_items")

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_user_item"),
    )
