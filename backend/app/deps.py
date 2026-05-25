"""공통 의존성.

FastAPI의 Depends()로 라우터에 주입되는 인증 의존성.
HTTPBearer 스킴을 써야 Swagger UI(/docs)의 Authorize 버튼이 자동으로
Authorization 헤더를 추가해 줍니다.
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.services.supabase_client import supabase


# Swagger UI 의 "Authorize" 버튼을 활성화시키는 표준 Bearer 스킴
security = HTTPBearer(auto_error=True)


@dataclass
class CurrentUser:
    id: str
    email: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """Bearer 토큰을 Supabase Auth로 검증하여 사용자 정보 반환.

    프론트엔드/Swagger UI는 Supabase 로그인 후 access_token을
    `Authorization: Bearer <token>` 헤더로 보냅니다.
    """
    token = credentials.credentials  # "Bearer " 접두사는 자동 제거됨

    try:
        user_resp = supabase.auth.get_user(token)
        user = user_resp.user
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return CurrentUser(id=user.id, email=user.email or "")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
        )