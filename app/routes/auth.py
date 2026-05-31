# app/routes/auth.py
import os
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

KAKAO_CLIENT_ID     = os.getenv("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI  = os.getenv("KAKAO_REDIRECT_URI", "http://localhost:8000/auth/kakao/callback")


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


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


# ── Kakao ───────────────────────────────────────────────────────

@router.get("/auth/kakao")
async def kakao_login():
    import logging
    logging.warning(f"KAKAO_CLIENT_ID 앞 6자리: '{KAKAO_CLIENT_ID[:6]}', 길이: {len(KAKAO_CLIENT_ID)}")
    logging.warning(f"KAKAO_REDIRECT_URI: '{KAKAO_REDIRECT_URI}'")
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

    user = await _upsert_oauth_user("kakao", kakao_id, nickname, email)
    return RedirectResponse(f"/?user_id={user['id']}&username={user['username']}")
