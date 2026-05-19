-- ==============================================
-- Gamification 아이템 시스템 스키마
-- Supabase SQL Editor에서 실행하세요
-- ==============================================

-- 1. 아이템 정의 테이블 (12개 카테고리 아이템)
CREATE TABLE IF NOT EXISTS items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    category    TEXT NOT NULL UNIQUE,   -- "카페/음료", "뉴스/사회" 등
    emoji       TEXT,                   -- "☕", "📰" 등
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 사용자별 카테고리별 저장 카운트 추적
CREATE TABLE IF NOT EXISTS user_category_counts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL,
    category     TEXT NOT NULL,
    count        INTEGER DEFAULT 1,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, category)
);

-- 3. 사용자 보유 아이템 (pending → claimed)
CREATE TABLE IF NOT EXISTS user_items (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id   UUID NOT NULL,
    item_id   UUID NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    category  TEXT NOT NULL,
    status    TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'claimed')),
    earned_at TIMESTAMPTZ DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    UNIQUE (user_id, item_id)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_user_category_counts_user_id ON user_category_counts (user_id);
CREATE INDEX IF NOT EXISTS idx_user_items_user_id ON user_items (user_id);
CREATE INDEX IF NOT EXISTS idx_user_items_status ON user_items (user_id, status);

-- ==============================================
-- 초기 아이템 데이터 (12개 카테고리)
-- ==============================================
INSERT INTO items (name, category, emoji, description) VALUES
    ('커피컵',   '카페/음료',   '☕', '아늑한 카페 분위기를 방에 담아보세요'),
    ('신문',     '뉴스/사회',   '📰', '세상 돌아가는 소식을 놓치지 않는 당신'),
    ('노트북',   'IT/기술',    '💻', '기술에 관심 많은 당신의 방에 딱!'),
    ('냄비',     '요리/식품',   '🍳', '요리를 사랑하는 당신을 위한 아이템'),
    ('지구본',   '여행',       '🌍', '세계 곳곳을 꿈꾸는 여행자의 방'),
    ('TV',       '영상/엔터',   '📺', '엔터테인먼트를 즐기는 당신의 방'),
    ('레코드판', '음악',        '🎵', '음악으로 가득 찬 감성 방'),
    ('책장',     '독서/책',    '📚', '지식을 쌓아가는 독서가의 방'),
    ('옷걸이',   '패션/뷰티',   '👗', '스타일리시한 당신의 방'),
    ('덤벨',     '운동/건강',   '🏋️', '건강을 챙기는 당신의 방'),
    ('연필꽂이', '교육/학습',   '✏️', '배움을 멈추지 않는 당신의 방'),
    ('팔레트',   '예술/디자인', '🎨', '창의적인 당신의 방')
ON CONFLICT (category) DO NOTHING;
