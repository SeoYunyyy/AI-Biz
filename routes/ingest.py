import asyncio
import json
from flask import Blueprint, request, jsonify
from database.db import get_db
from services.metadata.dispatcher import extract as dispatch
from services.ai_classifier import classify
from services.embedding import run as embed, generate_embedding, build_embed_text
from services.thumbnail_vision import analyze_thumbnail
from services.supabase_db import (
    save_content, update_content, mark_failed, check_duplicate,
    get_or_create_collection, find_similar_contents,
)

ingest_bp = Blueprint('ingest', __name__)


async def _run_pipeline(url: str, user_id: str, instruction: str, collection_id: str | None):
    # 1. 중복 체크
    existing = await check_duplicate(user_id, url)
    if existing:
        return {"duplicate": True, "content": existing}

    # 2. 즉시 저장 (processing)
    saved = await save_content(user_id, url)
    if not saved:
        return {"error": "초기 저장 실패"}, 500

    content_id = saved["id"]

    try:
        # 3. 메타데이터 추출
        metadata = await dispatch(url)

        # 4. 썸네일 Vision 분석 (실패해도 계속)
        thumbnail_description = await analyze_thumbnail(
            metadata.get("thumbnail", ""),
            metadata.get("title", ""),
        )

        # 5. AI 분류
        analysis = await classify(metadata, user_instruction=instruction)

        # 5-1. 폴더 처리
        final_collection_id = collection_id
        if not final_collection_id and analysis.get("user_collection"):
            final_collection_id = await get_or_create_collection(
                user_id, analysis["user_collection"]
            )

        # 6. 임베딩 생성 + 저장
        await embed(content_id, metadata, analysis, thumbnail_description)

        # 6-1. 유사 콘텐츠
        embed_text = build_embed_text(metadata, analysis, thumbnail_description)
        embedding = await generate_embedding(embed_text)
        similar = await find_similar_contents(user_id, embedding) if embedding else []

        # 7. Supabase 업데이트 (completed)
        await update_content(content_id, metadata, analysis, collection_id=final_collection_id, thumbnail_description=thumbnail_description)

        # 8. SQLite에도 저장 (기존 프론트엔드 호환)
        _save_to_sqlite(url, metadata, analysis)

        return {
            "id": content_id,
            "title": metadata.get("title", ""),
            "thumbnail": metadata.get("thumbnail", ""),
            "platform": metadata.get("platform", ""),
            "category": analysis.get("category", ""),
            "sub_category": analysis.get("sub_category", ""),
            "one_line_summary": analysis.get("one_line_summary", ""),
            "tags": analysis.get("tags", []),
            "has_deadline": analysis.get("has_deadline", False),
            "deadline_date": analysis.get("deadline_date"),
            "deadline_note": analysis.get("deadline_note"),
            "analysis_status": "completed",
            "similar_contents": [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "url": s["url"],
                    "similarity": round(s["similarity"], 2),
                    "one_line_summary": s.get("one_line_summary", ""),
                }
                for s in similar
            ],
        }

    except Exception as e:
        await mark_failed(content_id)
        raise e


def _save_to_sqlite(url: str, metadata: dict, analysis: dict):
    """기존 SQLite에도 저장 (아이템 목록 표시용)"""
    try:
        conn = get_db()
        conn.execute(
            'INSERT OR IGNORE INTO items (url, title, category, subcategory, summary, content_type, tags, thumbnail) VALUES (?,?,?,?,?,?,?,?)',
            (
                url,
                metadata.get("title", ""),
                analysis.get("category", "기타/알쓸신잡"),
                analysis.get("sub_category", ""),
                analysis.get("one_line_summary", ""),
                metadata.get("platform", "other"),
                json.dumps(analysis.get("tags", []), ensure_ascii=False),
                metadata.get("thumbnail", ""),
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ingest] SQLite 저장 오류 (무시): {e}")


@ingest_bp.route('/api/ingest', methods=['POST'])
def ingest():
    """
    URL 저장 + AI 분류 파이프라인.
    메타데이터 추출 → 썸네일 Vision → AI 분류 → 임베딩 → Supabase 저장
    """
    data = request.json or {}
    url = data.get('url', '').strip()
    user_id = data.get('user_id', '').strip()
    instruction = data.get('instruction', '')
    collection_id = data.get('collection_id')

    if not url:
        return jsonify({'error': 'URL이 필요합니다'}), 400
    if not user_id:
        return jsonify({'error': 'user_id가 필요합니다'}), 400

    try:
        result = asyncio.run(_run_pipeline(url, user_id, instruction, collection_id))
        if isinstance(result, tuple):
            return jsonify(result[0]), result[1]
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'분석 실패: {str(e)}'}), 500
