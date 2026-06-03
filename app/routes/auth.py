# ── 인증 라우트 (FastAPI) — Supabase 로그인 + JWT 세션 ──
# 기존 Flask(routes/auth.py) 로그인 로직을 FastAPI + JWT 기반으로 이식한 모듈.
# 프론트(login.js)가 Supabase 로그인 성공 시 user/access_token을 보내면
# 서버가 자체 JWT를 발급해 httpOnly 쿠키에 담고, 이후 요청은 이 쿠키로 인증한다.

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt  # PyJWT
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# JWT 설정 — 별도 JWT_SECRET이 없으면 기존 FLASK_SECRET_KEY를 재사용
JWT_SECRET = os.getenv("JWT_SECRET") or os.getenv("FLASK_SECRET_KEY", "keep-it-secret-key-2024")
JWT_ALGORITHM = "HS256"
JWT_EXP_DAYS = 7
COOKIE_NAME = "keepit_token"

# Supabase (OAuth 유저 upsert용)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# 카카오 OAuth 설정
KAKAO_CLIENT_ID     = os.getenv("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI  = os.getenv("KAKAO_REDIRECT_URI", "http://localhost:8000/auth/kakao/callback")


def create_token(user: dict) -> str:
    """유저 정보를 담은 JWT 발급"""
    payload = {
        "sub": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name", ""),
        "avatar": user.get("avatar", ""),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXP_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """JWT 검증 후 payload 반환 (실패 시 None)"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def current_user(request: Request) -> dict | None:
    """요청 쿠키의 JWT를 검증해 현재 로그인 유저를 반환 (미로그인 시 None)"""
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
    # 이미 로그인 상태면 메인으로
    if current_user(request):
        return RedirectResponse("/")
    return templates.TemplateResponse(request, "login.html", {
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", ""),
    })


@router.get("/auth/callback")
async def auth_callback():
    # Supabase OAuth 완료 후 돌아오는 URL → 클라이언트 JS가 세션 처리하므로 메인으로 리디렉트
    return RedirectResponse("/")


@router.post("/api/auth/session")
async def save_session(request: Request):
    # 프론트(Supabase)가 보낸 유저 정보로 JWT를 발급해 쿠키에 저장
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

# ── 카카오 OAuth ────────────────────────────────────────────────

def _supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def _upsert_oauth_user(provider: str, provider_id: str, display_name: str, email: str | None = None) -> dict:
    """OAuth 유저를 users 테이블에서 조회, 없으면 생성. {id, username, ...} 반환"""
    field = f"{provider}_id"
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/users",
            headers=_supabase_headers(),
            params={field: f"eq.{provider_id}", "select": "id,username,email"},
        )
        rows = res.json()
        if rows:
            return rows[0]

        user_data = {"username": display_name, field: provider_id}
        if email:
            user_data["email"] = email

        res = await client.post(
            f"{SUPABASE_URL}/rest/v1/users",
            headers={**_supabase_headers(), "Prefer": "return=representation"},
            json=user_data,
        )
        if not res.is_success:
            raise HTTPException(500, f"유저 생성 실패: {res.text}")
        return res.json()[0]


@router.get("/auth/kakao")
async def kakao_login():
    """카카오 인가 코드 요청 페이지로 리디렉트"""
    params = {
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "response_type": "code",
        "scope": "profile_nickname",
    }
    return RedirectResponse("https://kauth.kakao.com/oauth/authorize?" + urlencode(params))


@router.get("/auth/kakao/callback")
async def kakao_callback(code: str):
    """카카오 콜백 → 토큰 교환 → 유저 정보 조회 → users upsert → JWT 쿠키 발급 후 메인으로"""
    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(
            "https://kauth.kakao.com/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "client_id": KAKAO_CLIENT_ID,
                "client_secret": KAKAO_CLIENT_SECRET,
                "redirect_uri": KAKAO_REDIRECT_URI,
                "code": code,
            },
        )
        if not token_res.is_success:
            raise HTTPException(500, f"카카오 토큰 오류: {token_res.status_code} / {token_res.text}")
        access_token = token_res.json()["access_token"]

        info_res = await client.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info = info_res.json()

    kakao_id = str(info["id"])
    nickname = (
        info.get("kakao_account", {}).get("profile", {}).get("nickname")
        or f"user_{kakao_id[-4:]}"
    )
    email = info.get("kakao_account", {}).get("email")

    db_user = await _upsert_oauth_user("kakao", kakao_id, nickname, email)

    # AI-Biz JWT 쿠키 방식에 맞춰 토큰 발급
    user = {
        "id": db_user["id"],
        "email": db_user.get("email") or email or "",
        "name": db_user.get("username") or nickname,
        "avatar": "",
    }
    token = create_token(user)
    resp = RedirectResponse("/")
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True, max_age=JWT_EXP_DAYS * 86400, samesite="lax",
    )
    return resp


# 로그인 페이지·OAuth 콜백·JWT 세션 발급/조회/삭제·카카오 로그인 엔드포인트 (FastAPI 이식판)
