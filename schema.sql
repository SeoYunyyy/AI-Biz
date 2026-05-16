-- =============================================================
-- 취향 정리집 — 실제 Supabase DB 구조 (참고용, 실행 X)
-- =============================================================

-- ── 확장 ──────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ── 1. profiles ───────────────────────────────────────────────
-- auth.users 생성 시 트리거로 자동 생성됨
CREATE TABLE profiles (
  id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email       TEXT,
  display_name TEXT,
  avatar_url  TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── 2. collections ────────────────────────────────────────────
CREATE TABLE collections (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID REFERENCES profiles(id) ON DELETE CASCADE,
  name             TEXT NOT NULL,
  emoji            TEXT DEFAULT '📁',
  cluster_centroid vector(1536),          -- F-6.2: 재명명 판단용 클러스터 중심
  content_count    INTEGER DEFAULT 0,
  is_user_renamed  BOOLEAN DEFAULT FALSE,
  last_accessed_at TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── 3. contents ───────────────────────────────────────────────
CREATE TABLE contents (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID REFERENCES profiles(id) ON DELETE CASCADE,
  url              TEXT NOT NULL,
  content_type     TEXT NOT NULL DEFAULT 'other'
                     CHECK (content_type IN ('youtube', 'blog', 'other')),
  title            TEXT,
  description      TEXT,
  thumbnail_url    TEXT,
  author           TEXT,
  metadata         JSONB,             -- 타입별 추가 정보 (channel_name 등)
  topics           TEXT[] DEFAULT '{}',
  moods            TEXT[] DEFAULT '{}',
  intent           TEXT[] DEFAULT '{}',
  energy           TEXT,
  hashtags         TEXT[] DEFAULT '{}',
  collection_id    UUID REFERENCES collections(id) ON DELETE SET NULL,  -- 1:N
  analysis_status  TEXT DEFAULT 'pending'
                     CHECK (analysis_status IN ('pending','processing','completed','failed')),
  saved_at         TIMESTAMPTZ DEFAULT NOW(),
  analyzed_at      TIMESTAMPTZ,
  UNIQUE(user_id, url)
);

-- ── 4. embeddings (분리된 테이블) ──────────────────────────────
CREATE TABLE embeddings (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content_id UUID UNIQUE REFERENCES contents(id) ON DELETE CASCADE,
  embedding  vector(1536) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── 5. content_views ──────────────────────────────────────────
CREATE TABLE content_views (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID REFERENCES profiles(id) ON DELETE CASCADE,
  content_id UUID REFERENCES contents(id) ON DELETE CASCADE,
  viewed_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── 인덱스 ────────────────────────────────────────────────────
CREATE INDEX idx_contents_user_id       ON contents(user_id);
CREATE INDEX idx_contents_collection    ON contents(collection_id);
CREATE INDEX idx_contents_status        ON contents(user_id, analysis_status);
CREATE INDEX idx_contents_saved_at      ON contents(user_id, saved_at DESC);
CREATE INDEX idx_collections_user_id   ON collections(user_id);
CREATE INDEX idx_embeddings_content_id ON embeddings(content_id);
CREATE INDEX idx_content_views_user    ON content_views(user_id, viewed_at DESC);
CREATE INDEX idx_embeddings_vector     ON embeddings
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── RPC: 벡터 유사도 검색 ─────────────────────────────────────
-- 실제 함수명: match_user_contents
CREATE OR REPLACE FUNCTION match_user_contents(
  query_embedding  vector(1536),
  user_id_param    UUID,
  match_count      INT DEFAULT 5
)
RETURNS TABLE (
  id             UUID,
  url            TEXT,
  content_type   TEXT,
  title          TEXT,
  thumbnail_url  TEXT,
  author         TEXT,
  metadata       JSONB,
  hashtags       TEXT[],
  topics         TEXT[],
  moods          TEXT[],
  collection_id  UUID,
  saved_at       TIMESTAMPTZ,
  similarity     FLOAT
)
LANGUAGE SQL STABLE AS $$
  SELECT
    c.id, c.url, c.content_type, c.title, c.thumbnail_url,
    c.author, c.metadata, c.hashtags, c.topics, c.moods,
    c.collection_id, c.saved_at,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM contents c
  JOIN embeddings e ON e.content_id = c.id
  WHERE c.user_id = user_id_param
    AND c.analysis_status = 'completed'
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- ── profiles 자동 생성 트리거 ──────────────────────────────────
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO profiles (id, email)
  VALUES (NEW.id, NEW.email)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ── RLS ───────────────────────────────────────────────────────
ALTER TABLE profiles       ENABLE ROW LEVEL SECURITY;
ALTER TABLE contents       ENABLE ROW LEVEL SECURITY;
ALTER TABLE collections    ENABLE ROW LEVEL SECURITY;
ALTER TABLE embeddings     ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_views  ENABLE ROW LEVEL SECURITY;
