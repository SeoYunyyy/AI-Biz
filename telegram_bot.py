"""
Keepit 텔레그램 봇
- URL 공유 → 자동 저장
- /link USER_ID → Keepit 계정 연동
- 핸폰에서 링크 공유하기 → 텔레그램 봇 채팅 → Keepit DB 저장
"""

import os
import asyncio
import json
import re
import httpx
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
KEEPIT_URL  = os.getenv("KEEPIT_BASE_URL", "http://localhost:8000")
USERS_FILE  = Path("telegram_users.json")

TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
URL_RE  = re.compile(r'https?://[^\s]+')

# 대화 맥락 (메모리 내 유지, 재시작 시 초기화)
chat_histories: dict[str, list] = {}   # chat_id → [{role, content}, ...]
shown_ids_map:  dict[str, list] = {}   # chat_id → [content_id, ...]


# ── 유저 매핑 (telegram chat_id → keepit user_id) ──────────────────────────

def _load_users() -> dict:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}

def _save_users(users: dict):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Telegram API 헬퍼 ────────────────────────────────────────────────────────

async def send(chat_id: int, text: str, parse_mode: str = "HTML"):
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{TG_BASE}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        })


# ── 메시지 핸들러 ────────────────────────────────────────────────────────────

async def handle(message: dict, users: dict):
    chat_id = message["chat"]["id"]
    text    = message.get("text", "") or ""

    # ── /help ──
    if text.startswith("/help"):
        await send(chat_id,
            "📚 <b>Keepit 봇 사용법</b>\n\n"
            "🔗 <b>링크 저장</b>\n"
            "URL을 그냥 보내면 자동으로 저장돼요.\n\n"
            "🔍 <b>콘텐츠 검색</b>\n"
            "자연어로 찾고 싶은 걸 말해보세요.\n"
            "예: <i>저번에 저장한 딥러닝 영상 찾아줘</i>\n\n"
            "📅 <b>마감기한 확인</b>\n"
            "<code>/deadlines</code> 또는 <i>마감 임박한 거 뭐야</i>\n\n"
            "📂 <b>폴더 관리</b>\n"
            "<i>주식 폴더에 있는 거 찾아줘</i>\n"
            "<i>이거 IT 폴더로 옮겨줘</i>\n\n"
            "🔗 <b>계정 연동</b>\n"
            "<code>/link YOUR_USER_ID</code>"
        )
        return

    # ── /deadlines ──
    if text.startswith("/deadlines"):
        user_id = users.get(str(chat_id))
        if not user_id:
            await send(chat_id, "❗ 먼저 <code>/link YOUR_USER_ID</code> 로 연동해주세요.")
            return
        await _handle_chat(chat_id, user_id, "마감 임박한 거 정리해줘")
        return

    # ── /link USER_ID 연동 ──
    if text.startswith("/link") or text.startswith("/start"):
        parts = text.split()
        if len(parts) >= 2:
            user_id = parts[1].strip()
            users[str(chat_id)] = user_id
            _save_users(users)
            await send(chat_id,
                "✅ <b>Keepit 연동 완료!</b>\n"
                "이제 링크를 보내면 자동으로 저장해드려요.\n\n"
                "📱 핸폰에서: 링크 → 공유하기 → 텔레그램 → 이 채팅"
            )
        else:
            await send(chat_id,
                "👋 Keepit 봇이에요!\n\n"
                "연동하려면 Keepit 웹사이트에서 user_id를 복사한 뒤:\n"
                "<code>/link YOUR_USER_ID</code>\n\n"
                "user_id는 브라우저 콘솔에서 확인:\n"
                "<code>localStorage.getItem('keepit_user_id')</code>"
            )
        return

    # ── 연동 확인 ──
    user_id = users.get(str(chat_id))
    if not user_id:
        await send(chat_id,
            "❗ 먼저 Keepit 계정을 연동해주세요.\n"
            "<code>/link YOUR_USER_ID</code>"
        )
        return

    # ── URL 감지 → 저장 ──
    urls = URL_RE.findall(text)
    if urls:
        for url in urls:
            await send(chat_id, f"⏳ 저장 중...")
            try:
                async with httpx.AsyncClient(timeout=40) as client:
                    res = await client.post(f"{KEEPIT_URL}/ingest", json={
                        "url": url,
                        "user_id": user_id,
                    })
                data = res.json()

                if data.get("duplicate"):
                    content = data.get("content", {})
                    title = content.get("title") or data.get("title", "")
                    cat   = content.get("category") or ""
                    sub   = content.get("sub_category") or ""
                    cat_label = f"{cat} / {sub}" if sub else cat
                    await send(chat_id,
                        f"📌 <b>이미 저장된 링크예요</b>\n"
                        f"{title}\n"
                        f"📂 {cat_label}"
                    )
                elif res.is_success:
                    title = data.get("title", "")
                    cat   = data.get("category", "")
                    sub   = data.get("sub_category", "")
                    cat_label = f"{cat} / {sub}" if sub else cat
                    summary   = data.get("one_line_summary", "")
                    await send(chat_id,
                        f"✅ <b>저장 완료!</b>\n"
                        f"<b>{title}</b>\n"
                        f"📂 {cat_label}\n"
                        + (f"💬 {summary}" if summary else "")
                    )
                else:
                    await send(chat_id, f"❌ 저장 실패. 다시 시도해주세요.\n({res.status_code})")

            except Exception as e:
                await send(chat_id, f"❌ 오류가 발생했어요: {e}")
        return

    # ── URL 없는 일반 텍스트 → AI 채팅 ──
    await _handle_chat(chat_id, user_id, text)


# ── AI 채팅 핸들러 ──────────────────────────────────────────────────────────

def _fmt_results(results: list) -> str:
    """콘텐츠 목록을 텔레그램용 텍스트로 포맷"""
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title") or "(제목 없음)"
        url   = r.get("url", "")
        summary = r.get("one_line_summary") or r.get("description") or ""
        cat   = r.get("category") or ""
        sub   = r.get("sub_category") or ""
        cat_label = f"{cat} / {sub}" if sub else cat

        line = f"{i}. <b>{title}</b>"
        if cat_label:
            line += f"\n   📂 {cat_label}"
        if summary:
            line += f"\n   💬 {summary}"
        if url:
            line += f"\n   🔗 <a href='{url}'>{url[:60]}{'…' if len(url) > 60 else ''}</a>"
        lines.append(line)
    return "\n\n".join(lines)


async def _handle_chat(chat_id: int, user_id: str, text: str):
    key = str(chat_id)
    history   = chat_histories.get(key, [])
    s_ids     = shown_ids_map.get(key, [])

    history.append({"role": "user", "content": text})

    await send(chat_id, "⏳ 찾는 중...")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(f"{KEEPIT_URL}/chat", json={
                "query":      text,
                "user_id":    user_id,
                "history":    history[:-1],   # 현재 메시지 제외한 이전 맥락
                "shown_ids":  s_ids,
            })
        data = res.json()
    except Exception as e:
        await send(chat_id, f"❌ 오류가 발생했어요: {e}")
        return

    answer   = data.get("answer") or data.get("message") or ""
    results  = data.get("results") or []
    follow_q = data.get("follow_up_questions") or []

    # shown_ids 업데이트
    new_ids = [r["id"] for r in results if r.get("id")]
    if new_ids:
        shown_ids_map[key] = list(dict.fromkeys(s_ids + new_ids))

    # 어시스턴트 응답 기록
    history.append({"role": "assistant", "content": answer})
    chat_histories[key] = history[-20:]   # 최대 20개 메시지만 유지

    # 응답 조합
    parts = []
    if answer:
        parts.append(answer)
    if results:
        parts.append(_fmt_results(results))
    if follow_q and isinstance(follow_q[0], str):
        parts.append("💡 " + " / ".join(follow_q[:3]))

    reply = "\n\n".join(parts) if parts else "이해하지 못했어요. 다시 말씀해 주세요."
    await send(chat_id, reply)


# ── 폴링 루프 ────────────────────────────────────────────────────────────────

async def _register_commands():
    """Telegram 앱 하단 '/' 메뉴에 커맨드 등록"""
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{TG_BASE}/setMyCommands", json={"commands": [
            {"command": "link",      "description": "Keepit 계정 연동"},
            {"command": "help",      "description": "사용법 안내"},
            {"command": "deadlines", "description": "마감기한 확인"},
        ]})


async def poll():
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN이 .env에 없습니다.")
        return

    await _register_commands()

    users  = _load_users()
    offset = 0
    print(f"✅ Keepit 텔레그램 봇 시작 (서버: {KEEPIT_URL})")
    print("   종료: Ctrl+C\n")

    async with httpx.AsyncClient() as client:
        while True:
            try:
                res = await client.get(
                    f"{TG_BASE}/getUpdates",
                    params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                    timeout=35,
                )
                updates = res.json().get("result", [])
                for upd in updates:
                    offset = upd["update_id"] + 1
                    if "message" in upd:
                        await handle(upd["message"], users)

            except httpx.ReadTimeout:
                pass  # long polling 정상 동작
            except Exception as e:
                print(f"⚠️  에러: {e}")
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(poll())
