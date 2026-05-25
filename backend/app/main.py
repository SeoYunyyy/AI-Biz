"""FastAPI 진입점.

실행:
    uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.routers import save, search, content, report


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting in {settings.app_env} mode")
    # 시작 시 1회 실행할 작업이 있다면 여기에
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="SNS Archive API",
    version="0.1.0",
    description="저장만 하세요. 찾는 건 AI가.",
    lifespan=lifespan,
)

# CORS — Next.js 프론트(localhost:3000, *.vercel.app)에서 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(save.router, prefix="/api", tags=["save"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(content.router, prefix="/api", tags=["content"])
app.include_router(report.router, prefix="/api", tags=["report"])


@app.get("/health")
def health():
    """헬스 체크 — 배포 후 살아있는지 확인용."""
    return {"status": "ok", "env": settings.app_env}
