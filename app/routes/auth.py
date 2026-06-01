# ── 인증 라우트 (FastAPI) — Supabase 로그인 + JWT 세션 ──
# 프론트(login.js)가 Supabase 로그인 성공 시 user/access_token을 보내면
# 서버가 자체 JWT를 발급해 httpOnly 쿠키에 담고, 이후 요청은 이 쿠키로 인증한다.

import os
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

JWT_SECRET = os.getenv("JWT_SECRET") or os.getenv("FLASK_SECRET_KEY", "keep-it-secret-key-2024")
JWT_ALGORITHM = "HS256"
JWT_EXP_DAYS = 7
COOKIE_NAME = "keepit_token"


def create_token(user: dict) -> str:
    payload = {
        "sub": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name", ""),
        "avatar": user.get("avatar", ""),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXP_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name", ""),
        "avatar": payload.get("avatar", ""),
    }


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if current_user(request):
        return RedirectResponse("/")
    return templates.TemplateResponse(request, "login.html", {
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", ""),
    })


@router.get("/auth/callback")
async def auth_callback():
    return RedirectResponse("/")


@router.post("/api/auth/session")
async def save_session(request: Request):
    data = await request.json()
    if not data or "user" not in data:
        raise HTTPException(status_code=400, detail="유저 정보 없음")
    u = data["user"]
    meta = u.get("user_metadata") or {}
    user = {
        "id": u.get("id"),
        "email": u.get("email"),
        "name": meta.get("full_name", ""),
        "avatar": meta.get("avatar_url", ""),
    }
    token = create_token(user)
    resp = JSONResponse({"status": "ok", "user": user})
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True, max_age=JWT_EXP_DAYS * 86400, samesite="lax",
    )
    return resp


@router.get("/api/auth/user")
async def get_current_user(request: Request):
    user = current_user(request)
    if user:
        return {"user": user}
    return JSONResponse({"user": None}, status_code=401)


@router.post("/api/auth/logout")
async def logout():
    resp = JSONResponse({"status": "ok", "redirect": "/login"})
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ── 개발용 테스트 로그인 (로컬 전용) ──────────────────────────────────────────
TEST_EMAIL    = "test@keepit.local"
TEST_PASSWORD = "dev@keepit"

@router.post("/api/auth/test-login")
async def test_login(request: Request):
    """테스트 계정으로 Supabase 없이 직접 세션 발급."""
    data = await request.json()
    if data.get("email") == TEST_EMAIL and data.get("password") == TEST_PASSWORD:
        test_user = {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": TEST_EMAIL,
            "name": "테스트 유저",
            "avatar": "",
        }
        token = create_token(test_user)
        resp = JSONResponse({"status": "ok", "user": test_user})
        resp.set_cookie(
            COOKIE_NAME, token,
            httponly=True, max_age=JWT_EXP_DAYS * 86400, samesite="lax", path="/",
        )
        return resp
    raise HTTPException(status_code=401, detail="테스트 계정 정보가 올바르지 않습니다.")
