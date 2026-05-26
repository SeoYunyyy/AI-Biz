# ── Supabase 클라이언트 연결 ──
# Supabase SQL Editor에서 아래 SQL을 먼저 실행해주세요:
#
# CREATE TABLE IF NOT EXISTS groups (
#     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#     name TEXT NOT NULL,
#     item_ids JSONB DEFAULT '[]'::jsonb,
#     created_at TIMESTAMPTZ DEFAULT NOW()
# );

import os
from dotenv import load_dotenv
from supabase import create_client, Client
from services.category_mapper import map_topics_to_category

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL 또는 SUPABASE_SERVICE_KEY 환경변수가 없습니다. .env 파일을 확인하세요.")

_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_db() -> Client:
    return _client


def row_to_item(row: dict) -> dict:
    # contents 테이블 row → 프론트엔드 item 형식으로 변환
    metadata = row.get('metadata') or {}
    topics   = row.get('topics') or []
    category = metadata.get('category') or map_topics_to_category(topics)
    return {
        'id':           row.get('id', ''),
        'url':          row.get('url', ''),
        'title':        row.get('title', ''),
        'category':     category,
        'subcategory':  topics[0] if topics else '-',
        'summary':      row.get('description', ''),
        'content_type': row.get('content_type', 'other'),
        'tags':         row.get('hashtags') or [],
        'thumbnail':    row.get('thumbnail_url', ''),
        'deadline':     metadata.get('deadline'),
        'created_at':   row.get('saved_at', ''),
    }

# Supabase 클라이언트 반환 및 contents row → item dict 변환 헬퍼
