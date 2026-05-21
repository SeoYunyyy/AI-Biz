-- 1. pgvector 확장 활성화 (필수)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 핵심 3기능을 위한 심플한 contents 테이블 생성
CREATE TABLE IF NOT EXISTS public.contents (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    url text NOT NULL,
    title text,
    summary text,
    thumbnail_url text,
    category text,
    analysis_status text DEFAULT 'processing',
    created_at timestamp with time zone DEFAULT now()
);

-- 검색 속도 향상을 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_contents_user_category ON public.contents(user_id, category);

-- 3. 벡터 임베딩 저장용 테이블 분리 생성
CREATE TABLE IF NOT EXISTS public.embeddings (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    content_id uuid REFERENCES public.contents(id) ON DELETE CASCADE,
    vec vector(1536)
);

-- 4. 에러 없는 시맨틱 검색 함수 생성
CREATE OR REPLACE FUNCTION search_user_contents(
    query_embedding vector(1536),
    p_user_id uuid,
    p_category text DEFAULT NULL,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id uuid,
    url text,
    title text,
    summary text,
    thumbnail_url text,
    category text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT c.id, c.url, c.title, c.summary, c.thumbnail_url, c.category,
           1 - (e.vec <=> query_embedding) AS similarity
    FROM contents c
    JOIN embeddings e ON e.content_id = c.id
    WHERE c.user_id = p_user_id 
      AND (p_category IS NULL OR c.category = p_category)
    ORDER BY e.vec <=> query_embedding
    LIMIT match_count;
END;
$$;