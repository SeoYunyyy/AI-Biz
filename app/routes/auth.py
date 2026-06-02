# app/routes/auth.py — 카카오 OAuth + Google(Supabase OAuth) + JWT 세션

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt  # PyJWT
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

KAKAO_CLIENT_ID     = os.getenv("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI  = os.getenv("KAKAO_REDIRECT_URI", "http://localhost:8000/auth/kakao/callback")

JWT_SECRET    = os.getenv("JWT_SECRET") or os.getenv("FLASK_SECRET_KEY", "keep-it-secret-key-2024")
JWT_ALGORITHM = "HS256"
JWT_EXP_DAYS  = 7
COOKIE_NAME   = "keepit_token"


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


# ── JWT 헬퍼 ─────────────────────────────────────────────────────────────────

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


# ── Supabase users 테이블 upsert (카카오용) ──────────────────────────────────

async def _upsert_oauth_user(provider: str, provider_id: str, display_name: str, email: str = None) -> dict:
    field = f"{provider}_id"
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/users",
            headers=_headers(),
            params={field: f"eq.{provider_id}", "select": "id,username"},
        )
        rows = res.json()
        if rows:
            return rows[0]

        user_data = {"username": display_name, field: provider_id}
        if email:
            user_data["email"] = email

        res = await client.post(
            f"{SUPABASE_URL}/rest/v1/users",
            headers={**_headers(), "Prefer": "return=representation"},
            json=user_data,
        )
        if not res.is_success:
            raise HTTPException(500, f"유저 생성 실패: {res.text}")
        return res.json()[0]


# ── Google 로그인 (Supabase OAuth + JWT 세션) ────────────────────────────────

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
    resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=JWT_EXP_DAYS * 86400, samesite="lax")
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


# ── Kakao OAuth ──────────────────────────────────────────────────────────────

@router.get("/auth/kakao")
async def kakao_login():
    import logging
    logging.warning(f"KAKAO_CLIENT_ID 앞 6자리: '{KAKAO_CLIENT_ID[:6]}', 길이: {len(KAKAO_CLIENT_ID)}")
    params = {
        "client_id": KAKAO_CLIENT_ID,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "response_type": "code",
        "scope": "profile_nickname",
    }
    return RedirectResponse("https://kauth.kakao.com/oauth/authorize?" + urlencode(params))


@router.get("/auth/kakao/callback")
async def kakao_callback(code: str):
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
            raise HTTPException(500, f"카카오 토큰 오류: {token_res.status_code}")
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

    user = await _upsert_oauth_user("kakao", kakao_id, nickname, email)
    return RedirectResponse(f"/?user_id={user['id']}&username={user['username']}")
