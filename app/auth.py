# app/auth.py

import os
import logging
import httpx
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# DEV_MODE=true 로 설정하면 Supabase 토큰 검증을 건너뜀 (로컬 테스트 전용)
_DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
_DEV_USER_ID = os.getenv("DEV_USER_ID", "dev-user-id")


async def get_current_user_id(authorization: str = Header(default="")) -> str:
    """
    Supabase JWT 검증.
    Authorization: Bearer <supabase-access-token> 헤더에서 user_id(UUID) 추출.
    DEV_MODE=true 이면 검증 없이 DEV_USER_ID 반환.
    """
    if _DEV_MODE:
        return _DEV_USER_ID

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization: Bearer <token> 형식이 필요합니다.",
        )

    token = authorization[len("Bearer "):]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {token}",
                },
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

        user_id: str = resp.json().get("id", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="토큰에서 사용자 정보를 찾을 수 없습니다.")

        return user_id

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[auth] 토큰 검증 오류: {e}")
        raise HTTPException(status_code=401, detail="토큰 검증에 실패했습니다.")
