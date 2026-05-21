# ── 아카이브 (URL 저장 / 카테고리 조회 / 아이템 조회) ──

import json
from flask import Blueprint, request, jsonify
from database.db import get_db
from services.fetcher import fetch_url_content
from services.analyzer import analyze_content

archive_bp = Blueprint('archive', __name__)


@archive_bp.route('/api/save', methods=['POST'])
def save():
    data = request.json
    url = data.get('url', '').strip()
    deadline = data.get('deadline')

    if not url:
        return jsonify({'error': 'URL을 입력해주세요'}), 400

    try:
        content = fetch_url_content(url)
        analysis = analyze_content(content, deadline)
    except Exception as e:
        return jsonify({'error': f'분석 중 오류: {str(e)}'}), 500

    conn = get_db()
    conn.execute(
        'INSERT INTO items (url, title, category, subcategory, summary, content_type, tags, deadline) VALUES (?,?,?,?,?,?,?,?)',
        (
            url, analysis['title'], analysis['category'], analysis['subcategory'],
            analysis.get('summary'), analysis['content_type'],
            json.dumps(analysis.get('tags', []), ensure_ascii=False), deadline
        )
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'item': {**analysis, 'url': url}})


@archive_bp.route('/api/categories')
def categories():
    conn = get_db()
    rows = conn.execute(
        'SELECT category, subcategory, COUNT(*) as count FROM items GROUP BY category, subcategory ORDER BY count DESC'
    ).fetchall()
    conn.close()

    cats = {}
    for row in rows:
        cat = row['category']
        if cat not in cats:
            cats[cat] = []
        cats[cat].append({'name': row['subcategory'], 'count': row['count']})

    return jsonify(cats)


@archive_bp.route('/api/items')
def items():
    category = request.args.get('category', '')
    subcategory = request.args.get('subcategory', '')

    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM items WHERE category=? AND subcategory=? ORDER BY created_at DESC',
        (category, subcategory)
    ).fetchall()
    conn.close()

    result = [dict(r) for r in rows]
    for r in result:
        r['tags'] = json.loads(r['tags']) if r['tags'] else []

    return jsonify({'items': result})

# URL 저장(AI 분석 포함), 카테고리 목록 조회, 카테고리별 아이템 조회 라우트
