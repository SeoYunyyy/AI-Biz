# ── SQLite(knowledge.db) → Supabase contents 테이블 마이그레이션 ──
# 실행 방법: python scripts/migrate_to_supabase.py

import sys
import sqlite3
import json
from pathlib import Path

# 프로젝트 루트 기준으로 .env 로드
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

import os
from supabase import create_client
from services.category_mapper import map_topics_to_category

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
USER_ID      = os.getenv('SUPABASE_USER_ID')

if not SUPABASE_URL or not SUPABASE_KEY:
    print('❌ .env에 SUPABASE_URL, SUPABASE_SERVICE_KEY를 설정해주세요.')
    sys.exit(1)

if not USER_ID:
    print('❌ .env에 SUPABASE_USER_ID를 설정해주세요.')
    print('   Supabase 대시보드 → Authentication → Users 에서 본인 UUID 확인')
    sys.exit(1)

# DB 파일 탐색 (knowledge.db 우선)
db_path = None
for name in ['knowledge.db', 'keepit.db']:
    p = ROOT / name
    if p.exists():
        db_path = p
        break

if not db_path:
    print('❌ SQLite DB 파일을 찾을 수 없습니다.')
    sys.exit(1)

print(f'📂 DB: {db_path.name}')

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# 테이블 구조 확인
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
if 'items' not in tables:
    print(f'❌ items 테이블이 없습니다. 테이블 목록: {tables}')
    conn.close()
    sys.exit(1)

rows = conn.execute('SELECT * FROM items').fetchall()
print(f'📊 총 {len(rows)}개 항목 발견')

if not rows:
    print('마이그레이션할 데이터가 없습니다.')
    conn.close()
    sys.exit(0)

# 첫 행으로 컬럼 구조 파악
cols = rows[0].keys()
has_source_url  = 'source_url'  in cols   # knowledge.db 구조
has_url         = 'url'         in cols   # keepit.db / 현재 items 구조
has_subcategory = 'subcategory' in cols

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

success = 0
failed  = 0

for row in rows:
    r = dict(row)

    # ── URL ──
    url = r.get('url') or r.get('source_url') or ''
    if not url:
        print(f'  ⏭ URL 없음, 건너뜀')
        continue

    # ── tags / hashtags ──
    raw_tags = r.get('tags') or r.get('hashtags') or '[]'
    try:
        tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
    except Exception:
        tags = []

    # ── topics (subcategory 또는 tags 기반) ──
    if has_subcategory and r.get('subcategory'):
        topics = [r['subcategory'].strip()]
    elif tags:
        topics = [t.lstrip('#') for t in tags[:3]]  # 첫 3개 태그를 topics로
    else:
        topics = []

    # ── content_type ──
    content_type = r.get('content_type') or r.get('source_type') or 'other'

    # ── 카테고리 (metadata에 저장) ──
    category = r.get('category') or map_topics_to_category(topics)

    metadata = {'category': category}
    if r.get('deadline'):
        metadata['deadline'] = r['deadline']

    # ── saved_at 형식 변환 ──
    saved_at = r.get('saved_at') or r.get('created_at') or r.get('published_at')
    if saved_at and isinstance(saved_at, str) and 'T' not in saved_at:
        saved_at = saved_at.replace(' ', 'T') + '+00:00'

    content = {
        'user_id':         USER_ID,
        'url':             url,
        'title':           r.get('title') or '',
        'description':     r.get('summary') or r.get('description') or '',
        'thumbnail_url':   r.get('thumbnail_url') or r.get('thumbnail') or '',
        'author':          r.get('author') or '',
        'content_type':    content_type,
        'topics':          topics,
        'hashtags':        tags,
        'analysis_status': 'completed',
        'metadata':        metadata,
    }
    if saved_at:
        content['saved_at'] = saved_at

    try:
        supabase.table('contents').insert(content).execute()
        print(f'  ✅ {(r.get("title") or url)[:50]}')
        success += 1
    except Exception as e:
        print(f'  ❌ 실패: {(r.get("title") or url)[:40]} — {e}')
        failed += 1

conn.close()
print(f'\n✅ 완료: 성공 {success}개 / 실패 {failed}개')
print('이제 python app.py 실행 후 주간 레포트를 확인하세요!')
