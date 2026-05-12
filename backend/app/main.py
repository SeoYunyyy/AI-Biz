from fastapi import FastAPI

# FastAPI 앱 생성
app = FastAPI(
    title="AI-Biz API",
    description="나만의 자료 dump 서비스",
    version="0.1.0"
)

# 기본 테스트 API
@app.get("/")
def root():
    return {
        "message": "AI-Biz backend is running"
    }

