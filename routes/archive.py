import json
import os
from flask import Blueprint, request, jsonify
from database.db import get_db
from services.fetcher import fetch_url_content
from services.analyzer import analyze_content
from supabase import create_client

archive_bp = Blueprint('archive', __name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@archive_bp.route('/api/save', methods=['POST'])
def save():
    data = request.json or {}
    url = data.get('url', '').strip()
    deadline = data.get('deadline')

    if not url:
        return jsonify({'error': 'URL을 입력해주세요'}), 400

    try:
        content = fetch_url_content(url)
        analysis = analyze_content(content, deadline)
    except Exception as e:
        return jsonify({'error': f'분석 중 오류: {str(e)}'}), 500

    thumbnail = content.get('thumbnail', '')
    conn = get_db()
    conn.execute(
        'INSERT INTO items (url, title, category, subcategory, summary, content_type, tags, deadline, thumbnail) VALUES (?,?,?,?,?,?,?,?,?)',
        (url, analysis['title'], analysis['category'], analysis['subcategory'],
         analysis.get('summary'), analysis['content_type'],
         json.dumps(analysis.get('tags', []), ensure_ascii=False), deadline, thumbnail)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'item': {**analysis, 'url': url, 'thumbnail': thumbnail}})


# ── 카테고리 목록 (Supabase) ──
@archive_bp.route('/api/categories')
def categories():
    user_id = request.args.get('user_id', DEFAULT_USER_ID)
    try:
        rows = _sb().table("contents") \
            .select("category, sub_category") \
            .eq("user_id", user_id) \
            .eq("analysis_status", "completed") \
            .execute().data

        cats = {}
        for row in rows:
            cat = row.get("category") or "기타/알쓸신잡"
            sub = row.get("sub_category") or "기타"
            if cat not in cats:
                cats[cat] = {}
            cats[cat][sub] = cats[cat].get(sub, 0) + 1

        result = {
            cat: [{"name": sub, "count": cnt} for sub, cnt in subs.items()]
            for cat, subs in cats.items()
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({}), 200


# ── 카테고리별 아이템 (Supabase) ──
@archive_bp.route('/api/items')
def items():
    category = request.args.get('category', '')
    subcategory = request.args.get('subcategory', '')
    user_id = request.args.get('user_id', DEFAULT_USER_ID)

    try:
        q = _sb().table("contents") \
            .select("id, url, title, category, sub_category, description, content_type, topics, thumbnail_url, has_deadline, deadline_date, deadline_note") \
            .eq("user_id", user_id) \
            .eq("analysis_status", "completed")

        if category:
            q = q.eq("category", category)
        if subcategory:
            q = q.eq("sub_category", subcategory)

        rows = q.order("saved_at", desc=True).execute().data

        result = []
        for r in rows:
            result.append({
                "id": r.get("id"),
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "category": r.get("category", ""),
                "subcategory": r.get("sub_category", ""),
                "summary": r.get("description", ""),
                "content_type": r.get("content_type", "other"),
                "tags": r.get("topics") or [],
                "thumbnail": r.get("thumbnail_url", ""),
                "has_deadline": r.get("has_deadline", False),
                "deadline_date": r.get("deadline_date"),
                "deadline_note": r.get("deadline_note"),
            })

        return jsonify({"items": result})
    except Exception as e:
        return jsonify({"items": []}), 200
