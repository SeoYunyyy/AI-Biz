"""
SQLAlchemy 비동기 DB 연결 설정
Supabase PostgreSQL에 asyncpg로 접속
"""

import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

# .env에 DATABASE_URL=postgresql+asyncpg://user:password@host:port/dbname 형태로 설정
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.")

engine = create_async_engine(
    DATABASE_URL,
    echo=True,       # SQL 쿼리 로깅 (개발 중 True, 운영 시 False)
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI Depends()에서 사용하는 DB 세션 제공자"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
