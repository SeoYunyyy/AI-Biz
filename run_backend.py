# ── FastAPI 백엔드 서버 실행 ──
# 사용법: python run_backend.py

import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

# FastAPI 백엔드를 포트 8000에서 실행 (Flask는 5000)
