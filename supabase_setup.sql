-- ============================================================
-- 0. pgvector 확장 활성화
-- ============================================================
create extension if not exists vector;


-- ============================================================
-- 1. embeddings 테이블 vec 컬럼 → vector(1536) 타입으로 변환
--    (기존에 text/json 형태로 저장된 경우 ::vector 캐스팅 적용)
-- ============================================================
alter table embeddings
  alter column vec type vector(1536)
  using vec::vector;


-- ============================================================
-- 2. 코사인 유사도 인덱스 생성 (HNSW 방식)
--    - IVFFlat은 빌드 시 전체 벡터를 메모리에 올려 Supabase
--      무료/스타터 플랜의 maintenance_work_mem(32MB) 초과 에러 발생
--    - HNSW는 점진적 빌드 방식이라 메모리 제한에 걸리지 않음
--    - 검색 정확도(recall)도 IVFFlat보다 일반적으로 높음
--    - m            : 그래프 연결 수 (기본 16, 정확도↑ → 빌드 시간↑)
--    - ef_construction : 빌드 탐색 범위 (기본 64, 클수록 정확도↑)
-- ============================================================
create index if not exists idx_embeddings_vec_cosine
  on embeddings
  using hnsw (vec vector_cosine_ops)
  with (m = 16, ef_construction = 64);


-- ============================================================
-- 3. match_contents RPC 함수
--    - query_embedding : 검색어를 임베딩한 벡터 (1536차원)
--    - match_threshold : 코사인 유사도 최솟값 (0~1, 권장 0.3)
--    - match_count     : 반환할 최대 결과 수 (권장 3~5)
--    - p_user_id       : 본인 콘텐츠만 검색하기 위한 사용자 ID
-- ============================================================
create or replace function match_contents(
  query_embedding  vector(1536),
  match_threshold  float,
  match_count      int,
  p_user_id        uuid
)
returns table (
  id             uuid,
  title          text,
  thumbnail_url  text,
  hashtags       text[],
  category       text,
  summary        text,
  similarity     float
)
language sql stable
as $$
  select
    c.id,
    c.title,
    c.thumbnail_url,
    c.hashtags,
    c.category,
    c.summary,
    -- 코사인 유사도 = 1 - 코사인 거리
    (1 - (e.vec <=> query_embedding))::float as similarity
  from contents c
  join embeddings e on e.content_id = c.id
  where c.user_id          = p_user_id
    and c.analysis_status  = 'completed'
    and (1 - (e.vec <=> query_embedding)) > match_threshold
  order by e.vec <=> query_embedding  -- 거리 오름차순 = 유사도 내림차순
  limit match_count;
$$;
