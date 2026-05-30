# app/routes/auth.py

import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/signup")
async def signup(req: AuthRequest):
    if len(req.username) < 2:
        raise HTTPException(400, "아이디는 2자 이상이어야 해요")
    if len(req.password) < 4:
        raise HTTPException(400, "비밀번호는 4자 이상이어야 해요")

    async with httpx.AsyncClient(timeout=10) as client:
        check = await client.get(
            f"{SUPABASE_URL}/rest/v1/users",
            headers=_headers(),
            params={"username": f"eq.{req.username}", "select": "id"},
        )
        if check.json():
            raise HTTPException(400, "이미 사용 중인 아이디예요")

        res = await client.post(
            f"{SUPABASE_URL}/rest/v1/users",
            headers={**_headers(), "Prefer": "return=representation"},
            json={"username": req.username, "password_hash": pwd_context.hash(req.password)},
        )
        res.raise_for_status()
        user = res.json()[0]

    return {"user_id": user["id"], "username": user["username"]}


@router.post("/auth/login")
async def login(req: AuthRequest):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/users",
            headers=_headers(),
            params={"username": f"eq.{req.username}", "select": "id,username,password_hash"},
        )
        rows = res.json()

    if not rows or not pwd_context.verify(req.password, rows[0]["password_hash"]):
        raise HTTPException(401, "아이디 또는 비밀번호가 틀렸어요")

    return {"user_id": rows[0]["id"], "username": rows[0]["username"]}
