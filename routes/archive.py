# ── 아카이브 (URL 저장 파이프라인 / 카테고리 조회 / 아이템 조회) ──

from flask import Blueprint, request, jsonify, session
from database.db import (
    get_db, row_to_item,
    check_duplicate, save_content_initial, update_content_completed,
    mark_failed, find_similar_contents,
    get_or_create_collection,
    get_all_contents_for_reclassify, update_ai_fields,
    delete_content,
)
from services.metadata.dispatcher import extract as dispatch
from services.analyzer import analyze_content
from services.embedding import run as embed, generate_embedding, build_embed_text
from services.thumbnail_vision import analyze_thumbnail
from services.category_mapper import map_topics_to_category

archive_bp = Blueprint('archive', __name__)


def _uid():
    return (session.get('user') or {}).get('id', '')


@archive_bp.route('/api/save', methods=['POST'])
def save():
    """
    URL 하나 받아서 끝까지 처리.

    흐름:
    1. 중복 체크
    2. 즉시 저장 (processing)
    3. 메타데이터 추출 (dispatcher)
    4. 썸네일 Vision 분석
    5. AI 분류
    6. 임베딩 생성 + 저장
    7. contents 업데이트 (completed)
    """
    user_id = _uid()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    data        = request.json
    url         = (data.get('url') or '').strip()
    instruction = data.get('instruction', '')   # "생비과제 폴더에 넣어줘" 같은 지시사항

    if not url:
        return jsonify({'error': 'URL을 입력해주세요'}), 400

    # 1. 중복 체크
    existing = check_duplicate(user_id, url)
    if existing:
        return jsonify({'duplicate': True, 'item': existing})

    # 2. 즉시 저장 (분석 전 — 사용자를 기다리게 하지 않음)
    saved = save_content_initial(user_id, url)
    if not saved:
        return jsonify({'error': '초기 저장 실패'}), 500

    content_id = saved['id']

    try:
        # 3. 메타데이터 추출 (URL 보고 적절한 추출기 선택)
        metadata = dispatch(url)

        # 4. 썸네일 Vision 분석 (thumbnail 있을 때만, 실패해도 파이프라인 계속)
        thumbnail_description = analyze_thumbnail(
            metadata.get('thumbnail', ''),
            metadata.get('title', ''),
        )

        # 5. AI 분류
        analysis = analyze_content(metadata, user_instruction=instruction)
        if instruction:
            analysis['save_purpose'] = instruction

        # 5-1. 사용자 지정 폴더 처리
        collection_id = None
        if analysis.get('user_collection'):
            collection_id = get_or_create_collection(user_id, analysis['user_collection'])

        # 6. 임베딩 생성 + embeddings 테이블 저장 (썸네일 설명 포함)
        embed(content_id, metadata, analysis, thumbnail_description)

        # 6-1. 유사 콘텐츠 검색
        embed_text = build_embed_text(metadata, analysis, thumbnail_description)
        embedding  = generate_embedding(embed_text)
        similar    = find_similar_contents(user_id, embedding) if embedding else []

        # 7. contents 업데이트 (completed)
        update_content_completed(content_id, metadata, analysis, thumbnail_description)

        # 유사 콘텐츠 리마인드 메시지 생성
        reminder_message = None
        if similar:
            top_title = similar[0].get('title', '')
            if len(similar) == 1:
                reminder_message = f"'{top_title}'과 비슷한 내용을 저장한 적 있어요."
            else:
                reminder_message = f"'{top_title}' 등 {len(similar)}개의 비슷한 내용을 저장한 적 있어요."

        return jsonify({
            'success':          True,
            'id':               content_id,
            'title':            metadata.get('title', ''),
            'thumbnail':        metadata.get('thumbnail', ''),
            'platform':         metadata.get('platform', ''),
            'category':         analysis.get('category', ''),
            'one_line_summary': analysis.get('one_line_summary', ''),
            'tags':             analysis.get('tags', []),
            'has_deadline':     analysis.get('has_deadline', False),
            'deadline_date':    analysis.get('deadline_date'),
            'deadline_note':    analysis.get('deadline_note'),
            'sub_category':     analysis.get('sub_category', ''),
            'analysis_status':  'completed',
            'reminder_message': reminder_message,
            'similar_contents': [
                {
                    'id':               s['id'],
                    'title':            s['title'],
                    'url':              s.get('url', ''),
                    'similarity':       round(s.get('similarity', 0), 2),
                    'one_line_summary': s.get('one_line_summary', ''),
                }
                for s in similar
            ],
            # 프론트 호환용 item 래퍼 (buildSavedItemContent에서 data.item 접근)
            'item': {
                'id':           content_id,
                'url':          url,
                'title':        metadata.get('title', ''),
                'category':     analysis.get('category', ''),
                'subcategory':  analysis.get('sub_category', ''),
                'summary':      analysis.get('one_line_summary', ''),
                'content_type': metadata.get('platform', 'web'),
                'tags':         analysis.get('tags', []),
                'thumbnail':    metadata.get('thumbnail', ''),
                'deadline':     analysis.get('deadline_date'),
                'created_at':   '',
            },
        })

    except Exception as e:
        mark_failed(content_id)
        return jsonify({'error': f'분석 실패: {str(e)}'}), 500


@archive_bp.route('/api/categories')
def categories():
    user_id = _uid()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    db   = get_db()
    rows = db.table('contents').select('metadata, topics, category').eq('user_id', user_id).execute().data

    cats = {}
    for row in rows:
        metadata = row.get('metadata') or {}
        topics   = row.get('topics') or []
        # AI 분류 결과 category 우선, 없으면 기존 방식으로 매핑
        cat = row.get('category') or metadata.get('category') or map_topics_to_category(topics)
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
    user_id     = _uid()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    category    = request.args.get('category', '')
    subcategory = request.args.get('subcategory', '')

    db       = get_db()
    all_rows = (
        db.table('contents').select('*')
        .eq('user_id', user_id)
        .order('saved_at', desc=True)
        .execute().data
    )

    result = [
        row_to_item(r) for r in all_rows
        if row_to_item(r)['category'] == category
        and row_to_item(r)['subcategory'] == subcategory
    ]

    return jsonify({'items': result})

@archive_bp.route('/api/contents/<content_id>', methods=['DELETE'])
def remove_content(content_id):
    user_id = _uid()
    if not user_id:
        return jsonify({'error': '로그인이 필요합니다'}), 401

    success = delete_content(content_id, user_id)
    if not success:
        return jsonify({'error': '삭제 실패'}), 500
    return jsonify({'success': True, 'deleted_id': content_id})


@archive_bp.route('/admin/reclassify/<user_id>', methods=['POST'])
def reclassify_all(user_id: str):
    """
    기존 저장 콘텐츠 전체를 AI로 재분류.
    category, sub_category, 요약, 태그 등 AI 필드만 업데이트.
    """
    contents = get_all_contents_for_reclassify(user_id)
    if not contents:
        return jsonify({"updated": 0, "message": "재분류할 콘텐츠가 없어요."})

    updated, failed = 0, 0
    for c in contents:
        try:
            metadata = {
                "title":        c.get("title", ""),
                "platform":     c.get("content_type", "web"),
                "summary":      c.get("description", ""),
                "original_url": c.get("url", ""),
            }
            analysis = analyze_content(metadata)
            success  = update_ai_fields(c["id"], analysis)
            if success:
                updated += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[reclassify] {c.get('id')} 실패: {e}")
            failed += 1

    return jsonify({"updated": updated, "failed": failed, "total": len(contents)})

# URL 저장 7단계 파이프라인, 카테고리 목록 조회, 카테고리별 아이템 조회, 재분류 라우트
