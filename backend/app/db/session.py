"""SQLAlchemy 세션 — pgvector 확장이 활성화된 PostgreSQL에 연결."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI Depends에서 사용할 세션 제공자."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
