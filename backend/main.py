"""
MyThing FastAPI 백엔드
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import gamification, calendar

app = FastAPI(
    title="MyThing API",
    description="나만의 자료 아카이브 + 캐릭터 방 꾸미기 게이미피케이션",
    version="0.1.0",
)

# CORS 설정 (Next.js 프론트엔드 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(gamification.router)
app.include_router(calendar.router)


@app.get("/health", tags=["health"])
async def health_check():
    """서버 상태 확인"""
    return {"status": "ok", "service": "MyThing API"}
