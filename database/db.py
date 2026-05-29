# ── Supabase 클라이언트 연결 및 DB 헬퍼 함수 ──

import os
from datetime import datetime, timezone, timedelta
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
        'one_line_summary': row.get('one_line_summary', ''),
        'topics':       topics,
        'similarity':   row.get('similarity', 0),
    }


# ── URL 저장 파이프라인용 헬퍼 ─────────────────────────────────────────────────

def check_duplicate(user_id: str, url: str) -> dict | None:
    """같은 유저가 같은 URL 저장 시 기존 데이터 반환, 없으면 None"""
    try:
        result = (
            _client.table('contents')
            .select('id,title,analysis_status,hashtags')
            .eq('user_id', user_id)
            .eq('url', url)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[database] 중복 체크 오류: {e}")
        return None


def save_content_initial(user_id: str, url: str) -> dict | None:
    """1단계: URL만 즉시 저장 (analysis_status = 'processing')"""
    try:
        result = (
            _client.table('contents')
            .insert({
                "user_id":         user_id,
                "url":             url,
                "content_type":    "other",
                "analysis_status": "processing",
                "saved_at":        datetime.now(timezone.utc).isoformat(),
            })
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[database] 초기 저장 오류: {e}")
        return None


def update_content_completed(content_id: str, metadata: dict, analysis: dict, thumbnail_description: str = "") -> bool:
    """2단계: 분석 완료 후 나머지 필드 업데이트 (analysis_status = 'completed')"""
    try:
        _client.table('contents').update({
            "content_type":        metadata.get("platform", "other"),
            "title":               metadata.get("title", ""),
            "description":         metadata.get("summary") or analysis.get("detailed_summary", ""),
            "thumbnail_url":       metadata.get("thumbnail", ""),
            "metadata": {
                "date":         metadata.get("date", ""),
                "original_url": metadata.get("original_url", ""),
            },
            "one_line_summary":    analysis.get("one_line_summary", ""),
            "detailed_summary":    analysis.get("detailed_summary", ""),
            "save_purpose":        analysis.get("save_purpose", ""),
            "topics":              analysis.get("tags", []),
            "hashtags":            [f"#{t}" for t in analysis.get("tags", [])],
            "category":            analysis.get("category", "기타/알쓸신잡"),
            "sub_category":        analysis.get("sub_category", ""),
            "has_deadline":        analysis.get("has_deadline", False),
            "deadline_date":       analysis.get("deadline_date"),
            "deadline_note":       analysis.get("deadline_note"),
            "thumbnail_description": thumbnail_description or None,
            "analysis_status":     "completed",
            "analyzed_at":         datetime.now(timezone.utc).isoformat(),
        }).eq('id', content_id).execute()
        return True
    except Exception as e:
        print(f"[database] 업데이트 오류: {e}")
        return False


def mark_failed(content_id: str) -> None:
    """분석 실패 시 status만 failed로 업데이트"""
    try:
        _client.table('contents').update({"analysis_status": "failed"}).eq('id', content_id).execute()
    except Exception as e:
        print(f"[database] 실패 처리 오류: {e}")


# ── 벡터 검색 ─────────────────────────────────────────────────────────────────

def search_contents(user_id: str, query_embedding: list, limit: int = 3, threshold: float = 0.3) -> list:
    """벡터 유사도 검색 (match_user_contents RPC 호출)"""
    try:
        result = _client.rpc('match_user_contents', {
            "query_embedding": query_embedding,
            "user_id_param":   user_id,
            "match_count":     limit * 3,
        }).execute()
        filtered = [r for r in result.data if r.get("similarity", 0) >= threshold]
        return filtered[:limit]
    except Exception as e:
        print(f"[database] 검색 오류: {e}")
        return []


def find_similar_contents(user_id: str, embedding: list, threshold: float = 0.5, limit: int = 3) -> list:
    """새로 저장할 콘텐츠와 유사한 기존 콘텐츠 검색 (중복/관련 알림용)"""
    try:
        result = _client.rpc('match_user_contents', {
            "query_embedding": embedding,
            "user_id_param":   user_id,
            "match_count":     limit,
        }).execute()
        return [r for r in result.data if r.get("similarity", 0) >= threshold]
    except Exception as e:
        print(f"[database] 유사 콘텐츠 검색 오류: {e}")
        return []


# ── 마감기한 ──────────────────────────────────────────────────────────────────

def get_deadlines(user_id: str) -> list:
    """마감기한 있는 콘텐츠를 마감일 오름차순으로 반환"""
    try:
        result = (
            _client.table('contents')
            .select('id,title,url,deadline_date,deadline_note,thumbnail_url')
            .eq('user_id', user_id)
            .eq('has_deadline', True)
            .order('deadline_date', desc=False)
            .execute()
        )
        return result.data
    except Exception as e:
        print(f"[database] 마감기한 조회 오류: {e}")
        return []


def get_old_contents(user_id: str, days: int = 365) -> list:
    """저장한 지 days일 이상 지난 콘텐츠 반환"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        result = (
            _client.table('contents')
            .select('id,title,url,saved_at,category')
            .eq('user_id', user_id)
            .lt('saved_at', cutoff)
            .order('saved_at', desc=False)
            .execute()
        )
        return result.data
    except Exception as e:
        print(f"[database] 오래된 콘텐츠 조회 오류: {e}")
        return []


# ── 컬렉션(폴더) ───────────────────────────────────────────────────────────────

def get_or_create_collection(user_id: str, name: str) -> str | None:
    """폴더 이름으로 조회, 없으면 생성해서 collection_id 반환"""
    try:
        result = (
            _client.table('collections')
            .select('id')
            .eq('user_id', user_id)
            .eq('name', name)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]['id']

        created = (
            _client.table('collections')
            .insert({"user_id": user_id, "name": name, "is_user_renamed": True})
            .execute()
        )
        return created.data[0]['id'] if created.data else None
    except Exception as e:
        print(f"[database] 컬렉션 오류: {e}")
        return None


def get_collections(user_id: str) -> list:
    """사용자 폴더 목록 전체 조회"""
    try:
        result = (
            _client.table('collections')
            .select('id,name,emoji,content_count,created_at')
            .eq('user_id', user_id)
            .order('created_at', desc=False)
            .execute()
        )
        return result.data
    except Exception as e:
        print(f"[database] 폴더 목록 조회 오류: {e}")
        return []


def move_content_collection(content_id: str, user_id: str, collection_id: str | None) -> bool:
    """콘텐츠의 폴더(collection_id) 변경"""
    try:
        _client.table('contents').update(
            {"collection_id": collection_id}
        ).eq('id', content_id).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        print(f"[database] 폴더 이동 오류: {e}")
        return False


def update_deadline(content_id: str, user_id: str, has_deadline: bool, deadline_date: str | None, deadline_note: str | None) -> bool:
    """마감기한 수정 (채팅에서 사용자가 정정할 때)"""
    try:
        _client.table('contents').update({
            "has_deadline":  has_deadline,
            "deadline_date": deadline_date,
            "deadline_note": deadline_note,
        }).eq('id', content_id).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        print(f"[database] 마감기한 수정 오류: {e}")
        return False


def get_all_contents_for_reclassify(user_id: str) -> list:
    """재분류용 전체 콘텐츠 조회"""
    try:
        result = (
            _client.table('contents')
            .select('id,title,content_type,description,url,metadata')
            .eq('user_id', user_id)
            .eq('analysis_status', 'completed')
            .execute()
        )
        return result.data
    except Exception as e:
        print(f"[database] 전체 조회 오류: {e}")
        return []


def update_ai_fields(content_id: str, analysis: dict) -> bool:
    """AI 분류 결과 필드만 업데이트 (재분류용)"""
    try:
        _client.table('contents').update({
            "category":         analysis.get("category", "기타/알쓸신잡"),
            "sub_category":     analysis.get("sub_category", ""),
            "one_line_summary": analysis.get("one_line_summary", ""),
            "detailed_summary": analysis.get("detailed_summary", ""),
            "save_purpose":     analysis.get("save_purpose", ""),
            "topics":           analysis.get("tags", []),
            "hashtags":         [f"#{t}" for t in analysis.get("tags", [])],
            "has_deadline":     analysis.get("has_deadline", False),
            "deadline_date":    analysis.get("deadline_date"),
            "deadline_note":    analysis.get("deadline_note"),
        }).eq('id', content_id).execute()
        return True
    except Exception as e:
        print(f"[database] AI 필드 업데이트 오류: {e}")
        return False

# Supabase 클라이언트 반환 및 contents row → item dict 변환 헬퍼, 파이프라인용 DB 함수 모음
