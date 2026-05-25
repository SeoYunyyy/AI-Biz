-- Supabase SQL Editor에서 실행하는 초기 마이그레이션 스크립트
-- 1) pgvector 확장 활성화
CREATE EXTENSION IF NOT EXISTS vector;

-- 2) users 테이블 (Supabase auth.users 와 별개의 앱 측 사용자 메타)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);

-- 3) contents 테이블
CREATE TABLE IF NOT EXISTS contents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    platform TEXT,
    title TEXT,
    description TEXT,
    thumbnail_url TEXT,
    category TEXT,
    summary TEXT,
    mood TEXT,
    embedding vector(1536),
    saved_at TIMESTAMP DEFAULT now(),
    last_viewed_at TIMESTAMP,
    view_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_contents_user_id ON contents(user_id);
CREATE INDEX IF NOT EXISTS idx_contents_category ON contents(category);
CREATE INDEX IF NOT EXISTS idx_contents_saved_at ON contents(saved_at);

-- pgvector 코사인 거리 인덱스 (대규모일 때 검색 가속)
CREATE INDEX IF NOT EXISTS idx_contents_embedding
    ON contents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 4) tags 테이블
CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    content_id UUID REFERENCES contents(id) ON DELETE CASCADE,
    tag TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tags_content_id ON tags(content_id);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);

-- 5) events 테이블
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT,
    payload JSONB,
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);

-- 6) Row-Level Security (사용자별 데이터 격리)
ALTER TABLE contents ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

-- 본인 데이터만 SELECT/INSERT/UPDATE/DELETE 가능
CREATE POLICY "Own contents only" ON contents
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "Own events only" ON events
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
