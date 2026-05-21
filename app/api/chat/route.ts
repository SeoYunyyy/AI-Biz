import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { generateEmbedding, generateChatResponse } from '@/lib/openai';
import type { ContentCard } from '@/types';

export const runtime = 'nodejs';
export const maxDuration = 30;

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

// ── 벡터 유사도 (코사인) ────────────────────────────────────────
function cosine(a: number[], b: number[]): number {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  const d = Math.sqrt(na) * Math.sqrt(nb);
  return d === 0 ? 0 : dot / d;
}

function parseVector(v: unknown): number[] {
  if (Array.isArray(v)) return v as number[];
  if (typeof v === 'string') return v.replace(/[\[\]]/g, '').split(',').map(Number);
  return [];
}

// ── 의도 감지 ───────────────────────────────────────────────────
function detectMode(query: string): 'memory' | 'collection' | 'general' {
  if (/예전에|전에|몇 달|며칠|지난|그때|기억|봤던|저장했던|뭐였더라|있었는데/.test(query))
    return 'memory';
  if (/보여줘|추천|찾아줘|컬렉션|모아|모음|폴더|목록|어때/.test(query))
    return 'collection';
  return 'general';
}

// ── 폴백: 수동 벡터 검색 ────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function manualSearch(
  db: any,
  userId: string,
  queryEmbedding: number[],
  limit = 5
): Promise<ContentCard[]> {
  // 1. 이 유저의 모든 임베딩 가져오기
  const { data: embedRows, error: embedError } = await db
    .from('embeddings')
    .select('content_id, embedding');

  if (embedError || !embedRows?.length) {
    // embeddings 테이블이 없거나 비어있으면 텍스트 기반 최신순 반환
    const { data: fallback } = await db
      .from('contents')
      .select('id, url, content_type, title, thumbnail_url, author, metadata, hashtags, topics, moods, collection_id, saved_at')
      .eq('user_id', userId)
      .order('saved_at', { ascending: false })
      .limit(limit);
    return (fallback || []).map((c: ContentRow) => toCard(c, 1));
  }

  // 2. 코사인 유사도 계산
  interface Scored { content_id: string; score: number; }
  const scored: Scored[] = (embedRows as { content_id: string; embedding: unknown }[])
    .map((row) => ({
      content_id: row.content_id,
      score: cosine(queryEmbedding, parseVector(row.embedding)),
    }))
    .sort((a: Scored, b: Scored) => b.score - a.score)
    .slice(0, limit);

  if (!scored.length) return [];

  // 3. 상위 content_id로 contents 조회 (user_id 필터 포함)
  const topIds = scored.map((s: Scored) => s.content_id);
  const { data: contents } = await db
    .from('contents')
    .select('id, url, content_type, title, thumbnail_url, author, metadata, hashtags, topics, moods, collection_id, saved_at')
    .eq('user_id', userId)
    .in('id', topIds);

  if (!contents?.length) return [];

  return (contents as ContentRow[])
    .map((c) => toCard(c, scored.find((s: Scored) => s.content_id === c.id)?.score ?? 0))
    .sort((a: ContentCard, b: ContentCard) => (b.similarity ?? 0) - (a.similarity ?? 0));
}

// ── 컬렉션 의도 처리 ─────────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function findBestCollection(
  db: any,
  userId: string,
  query: string,
  queryEmbedding: number[]
) {
  const { data: collections } = await db
    .from('collections')
    .select('id, name, emoji, content_count, cluster_centroid')
    .eq('user_id', userId)
    .order('content_count', { ascending: false });

  if (!collections?.length) return null;

  // 텍스트 매칭 먼저
  const queryLower = query.toLowerCase();
  const textMatch = collections.find(
    (c: { name: string }) =>
      queryLower.includes(c.name.toLowerCase()) ||
      c.name.toLowerCase().split(' ').some((w: string) => queryLower.includes(w))
  );
  if (textMatch) return textMatch;

  // centroid 유사도
  interface ColRow { id: string; name: string; emoji: string; content_count: number; cluster_centroid: unknown; }
  interface ColScored { col: ColRow; score: number; }
  const scored: ColScored[] = (collections as ColRow[])
    .map((c) => {
      const centroid = parseVector(c.cluster_centroid);
      return { col: c, score: centroid.length > 0 ? cosine(queryEmbedding, centroid) : 0 };
    })
    .sort((a: ColScored, b: ColScored) => b.score - a.score);

  return scored[0]?.score > 0.35 ? scored[0].col : collections[0];
}

// ── 타입 ─────────────────────────────────────────────────────────
interface ContentRow {
  id: string;
  url: string;
  content_type: 'youtube' | 'blog' | 'other';
  title: string | null;
  thumbnail_url: string | null;
  author: string | null;
  metadata: Record<string, unknown> | null;
  hashtags: string[];
  topics: string[];
  moods: string[];
  collection_id: string | null;
  saved_at: string;
}

function toCard(c: ContentRow, similarity: number): ContentCard {
  return {
    id: c.id,
    url: c.url,
    content_type: c.content_type,
    title: c.title || '제목 없음',
    thumbnail_url: c.thumbnail_url,
    author: c.author,
    metadata: c.metadata,
    hashtags: c.hashtags || [],
    topics: c.topics || [],
    moods: c.moods || [],
    collection_id: c.collection_id,
    saved_at: c.saved_at,
    similarity,
  };
}

function getCardLabel(index: number, similarity: number, savedAt: string): string {
  if (index === 0) return '가장 가능성 높은 매칭';
  const daysSinceSaved = Math.floor(
    (Date.now() - new Date(savedAt).getTime()) / (1000 * 60 * 60 * 24)
  );
  if (index === 1) return daysSinceSaved < 14 ? '비슷한 시기에 저장한 콘텐츠' : '비슷한 분위기의 콘텐츠';
  return similarity > 0.6 ? '혹시 이건 어때요?' : '같은 분위기인데 한참 안 보신 거예요';
}

// ── 메인 핸들러 ──────────────────────────────────────────────────
export async function POST(req: NextRequest) {
  try {
    const { query, userId } = await req.json();
    if (!query || !userId) {
      return NextResponse.json({ error: 'query와 userId가 필요합니다.' }, { status: 400 });
    }

    const db = admin();

    // 콘텐츠 수 확인 — analysis_status 필터 없이 (관대하게)
    const { count, error: countError } = await db
      .from('contents')
      .select('*', { count: 'exact', head: true })
      .eq('user_id', userId);

    if (countError) {
      console.error('count error:', countError);
    }

    if ((count ?? 0) === 0) {
      return NextResponse.json({
        message: '아직 저장된 콘텐츠가 없어요. 아래 + 버튼으로 유튜브나 블로그 링크를 저장해보세요!',
        cards: [],
        mode: 'general',
        collectionData: null,
      });
    }

    // 쿼리 임베딩 생성
    const queryEmbedding = await generateEmbedding(query);
    const mode = detectMode(query);

    // ── 컬렉션 모드 ──────────────────────────────────────────────
    if (mode === 'collection') {
      const bestCol = await findBestCollection(db, userId, query, queryEmbedding);
      if (bestCol) {
        // 해당 컬렉션의 콘텐츠 가져오기
        const { data: colContents } = await db
          .from('contents')
          .select('id, url, content_type, title, thumbnail_url, author, metadata, hashtags, topics, moods, collection_id, saved_at')
          .eq('collection_id', bestCol.id)
          .eq('user_id', userId)
          .order('saved_at', { ascending: false })
          .limit(10);

        const cards: ContentCard[] = (colContents || []).map((c: ContentRow) => toCard(c, 1));

        return NextResponse.json({
          message: `${bestCol.emoji} ${bestCol.name} 컬렉션에 ${bestCol.content_count || cards.length}개가 있어요!`,
          cards: cards.slice(0, 5),
          mode: 'collection',
          collectionData: {
            id: bestCol.id,
            name: bestCol.name,
            emoji: bestCol.emoji,
            content_count: bestCol.content_count || cards.length,
          },
        });
      }
    }

    // ── 기억 회수 / 일반 모드 ─────────────────────────────────────
    let cards: ContentCard[] = [];

    // 1순위: RPC 함수 시도
    const { data: rpcResults, error: rpcError } = await db.rpc('match_user_contents', {
      query_embedding: JSON.stringify(queryEmbedding),
      user_id_param: userId,
      match_count: 5,
    });

    if (!rpcError && rpcResults?.length) {
      cards = rpcResults.slice(0, 3).map(
        (r: ContentRow & { similarity: number }, i: number) => ({
          ...toCard(r, r.similarity),
          label: getCardLabel(i, r.similarity, r.saved_at),
        })
      );
    } else {
      // 2순위: 수동 벡터 검색 폴백
      if (rpcError) console.error('RPC error (using fallback):', rpcError.message);
      const fallbackCards = await manualSearch(db, userId, queryEmbedding, 5);
      cards = fallbackCards.slice(0, 3).map((c, i) => ({
        ...c,
        label: getCardLabel(i, c.similarity ?? 0, c.saved_at),
      }));
    }

    const message = await generateChatResponse(query, cards);

    return NextResponse.json({
      message,
      cards,
      mode,
      collectionData: null,
    });
  } catch (err) {
    console.error('chat error:', err);
    return NextResponse.json({ error: '서버 오류' }, { status: 500 });
  }
}
