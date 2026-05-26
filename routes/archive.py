# ── 아카이브 (URL 저장 / 카테고리 조회 / 아이템 조회) ──

import os
from flask import Blueprint, request, jsonify
from database.db import get_db, row_to_item
from services.fetcher import fetch_url_content
from services.analyzer import analyze_content
from services.category_mapper import map_topics_to_category

archive_bp = Blueprint('archive', __name__)

USER_ID = os.getenv('SUPABASE_USER_ID')


@archive_bp.route('/api/save', methods=['POST'])
def save():
    data     = request.json
    url      = data.get('url', '').strip()
    deadline = data.get('deadline')

    if not url:
        return jsonify({'error': 'URL을 입력해주세요'}), 400

    if not USER_ID:
        return jsonify({'error': '.env에 SUPABASE_USER_ID를 설정해주세요'}), 500

    try:
        content  = fetch_url_content(url)
        analysis = analyze_content(content, deadline)
    except Exception as e:
        return jsonify({'error': f'분석 중 오류: {str(e)}'}), 500

    subcategory = (analysis.get('subcategory') or '').strip()
    metadata    = {'category': analysis.get('category', '기타')}
    if deadline:
        metadata['deadline'] = deadline

    row = {
        'user_id':          USER_ID,
        'url':              url,
        'title':            analysis.get('title', ''),
        'description':      analysis.get('summary'),
        'thumbnail_url':    content.get('thumbnail', ''),
        'content_type':     analysis.get('content_type', 'other'),
        'topics':           [subcategory] if subcategory else [],
        'hashtags':         analysis.get('tags', []),
        'analysis_status':  'completed',
        'metadata':         metadata,
    }

    db     = get_db()
    result = db.table('contents').insert(row).execute()
    saved  = result.data[0] if result.data else row

    return jsonify({'success': True, 'item': row_to_item(saved)})


@archive_bp.route('/api/categories')
def categories():
    db    = get_db()
    query = db.table('contents').select('metadata, topics')
    if USER_ID:
        query = query.eq('user_id', USER_ID)
    rows = query.execute().data

    cats = {}
    for row in rows:
        metadata = row.get('metadata') or {}
        topics   = row.get('topics') or []
        cat = metadata.get('category') or map_topics_to_category(topics)
        sub = topics[0] if topics else '기타'
        cats.setdefault(cat, {})
        cats[cat][sub] = cats[cat].get(sub, 0) + 1

    return jsonify({
        cat: [{'name': sub, 'count': cnt}
              for sub, cnt in sorted(subs.items(), key=lambda x: -x[1])]
        for cat, subs in cats.items()
    })


@archive_bp.route('/api/items')
def items():
    category    = request.args.get('category', '')
    subcategory = request.args.get('subcategory', '')

    db    = get_db()
    query = db.table('contents').select('*').order('saved_at', desc=True)
    if USER_ID:
        query = query.eq('user_id', USER_ID)
    all_rows = query.execute().data

    result = [
        row_to_item(r) for r in all_rows
        if row_to_item(r)['category'] == category and row_to_item(r)['subcategory'] == subcategory
    ]

    return jsonify({'items': result})

# URL 저장(AI 분석 포함), 카테고리 목록 조회, 카테고리별 아이템 조회 라우트
