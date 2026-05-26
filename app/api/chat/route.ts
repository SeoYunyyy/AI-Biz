import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { generateEmbedding, generateChatResponse, expandQuery, extractSearchIntent } from '@/lib/openai';
import { detectPlatform, detectQueryPlatform, platformLabel } from '@/lib/platform';
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

// ── 플랫폼 필터 헬퍼 ────────────────────────────────────────────
// platform 컬럼 값 또는 URL 파생값으로 플랫폼을 확인
function getPlatform(c: Record<string, unknown>): string {
  if (c.platform && typeof c.platform === 'string') return c.platform;
  // platform 컬럼이 NULL이면 URL에서 파생 (기존 데이터 호환)
  return detectPlatform((c.url as string) || '');
}

// ── 폴백: 수동 벡터 검색 ────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function manualSearch(
  db: any,
  userId: string,
  queryEmbedding: number[],
  limit = 5,
  platformFilter: string | null = null   // null = 플랫폼 무관
): Promise<ContentCard[]> {
  // 1. 이 유저의 모든 임베딩 가져오기
  const { data: embedRows, error: embedError } = await db
    .from('embeddings')
    .select('content_id, vec');

  if (embedError || !embedRows?.length) {
    // embeddings 없으면 최신순으로 폴백
    const { data: fallback } = await db
      .from('contents')
      .select('id, url, title, summary, thumbnail_url, category, hashtags, platform, analysis_status, saved_at')
      .eq('user_id', userId)
      .order('saved_at', { ascending: false })
      .limit(limit);
    return (fallback || []).map((c: Record<string, unknown>) => toCard({
      ...c,
      content_type: getPlatform(c) === 'youtube' ? 'youtube' : 'blog',
      author: null, metadata: null, topics: [], moods: [], collection_id: null,
    } as unknown as ContentRow, 1));
  }

  // 2. 코사인 유사도 계산 — 플랫폼 필터 시 후보를 더 넉넉하게 확보
  interface Scored { content_id: string; score: number; }
  const candidateLimit = platformFilter ? limit * 4 : limit;
  const scored: Scored[] = (embedRows as { content_id: string; vec: unknown }[])
    .map((row) => ({
      content_id: row.content_id,
      score: cosine(queryEmbedding, parseVector(row.vec)),
    }))
    .sort((a: Scored, b: Scored) => b.score - a.score)
    .slice(0, candidateLimit);

  if (!scored.length) return [];

  // 3. contents 조회 (platform 컬럼 포함)
  const topIds = scored.map((s: Scored) => s.content_id);
  const { data: contents } = await db
    .from('contents')
    .select('id, url, title, summary, thumbnail_url, category, hashtags, platform, analysis_status, saved_at')
    .eq('user_id', userId)
    .in('id', topIds);

  if (!contents?.length) return [];

  // 4. JS에서 platform 값으로 필터링 (NULL이면 URL에서 파생)
  const rows = contents as Record<string, unknown>[];
  let filtered = rows;
  if (platformFilter) {
    const matched = rows.filter((c) => getPlatform(c) === platformFilter);
    if (matched.length > 0) filtered = matched; // 없으면 전체 폴백
  }

  return filtered
    .map((c) => toCard({
      ...c,
      content_type: getPlatform(c) === 'youtube' ? 'youtube' : 'blog',
      author: null, metadata: null, topics: [], moods: [], collection_id: null,
    } as unknown as ContentRow, scored.find((s: Scored) => s.content_id === c.id)?.score ?? 0))
    .sort((a: ContentCard, b: ContentCard) => (b.similarity ?? 0) - (a.similarity ?? 0))
    .slice(0, limit);
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

function getCardLabel(index: number): string {
  return `${index + 1}위 후보`;
}

// ── 메인 핸들러 ──────────────────────────────────────────────────
export async function POST(req: NextRequest) {
  try {
    const { query, userId, history = [] } = await req.json();
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

    // ── 대화 맥락 통합 ───────────────────────────────────────────
    const hasHistory = Array.isArray(history) && history.length > 0;

    // 현재 쿼리가 이전 대화를 참조하는지 판단
    // 참조어가 없으면 → 새 주제로 간주해 이전 대화 무시
    const isFollowUp = hasHistory &&
      /그거|그것|그런|아까|저번|이전|방금|말한|찾던|그때|혹시 그|위에서|아까 말|그 영상|그 글|그 상품/.test(query);

    // 검색 의도 추출: 팔로업일 때만, 최근 2턴(4메시지)만 사용
    const recentHistory = hasHistory ? history.slice(-4) : [];
    const searchIntent = isFollowUp
      ? await extractSearchIntent(query, recentHistory)
      : query;

    // 플랫폼 필터: 현재 쿼리 + (팔로업이면 직전 유저 메시지까지)
    const userOnlyContext = isFollowUp
      ? recentHistory
          .filter((m: { role: string; content: string }) => m.role === 'user')
          .map((m: { role: string; content: string }) => m.content)
          .join(' ') + ' ' + query
      : query;
    const platformFilter = detectQueryPlatform(userOnlyContext);

    // 모드 감지: 현재 쿼리 중심 (이전 대화 오염 방지)
    const mode = detectMode(query);

    // 쿼리 확장 + 임베딩 생성 (검색 의도 기반)
    const needsExpansion =
      mode === 'memory' ||
      /썸네일|사진|이미지|안경|머리|얼굴|배경|색|옷|표지|커버|화면|영상에서|보여주던|있었는데|모르겠|기억/.test(userOnlyContext) ||
      searchIntent.trim().length < 20;
    const embeddingInput = needsExpansion ? await expandQuery(searchIntent) : searchIntent;
    const queryEmbedding = await generateEmbedding(embeddingInput);

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

    // 1순위: RPC 함수 시도 (플랫폼 필터 있으면 더 많이 받아서 JS 필터링)
    const rpcCount = platformFilter ? 10 : 5;
    const { data: rpcResults, error: rpcError } = await db.rpc('match_user_contents', {
      query_embedding: JSON.stringify(queryEmbedding),
      user_id_param: userId,
      match_count: rpcCount,
    });

    if (!rpcError && rpcResults?.length) {
      let pool: (ContentRow & { similarity: number })[] = rpcResults;

      // RPC 결과에 platform 필터 적용
      if (platformFilter) {
        const matched = pool.filter((r) => getPlatform(r as unknown as Record<string, unknown>) === platformFilter);
        if (matched.length > 0) pool = matched;
      }

      cards = pool.slice(0, 3).map((r, i) => ({
        ...toCard(r, r.similarity),
        label: getCardLabel(i),
      }));
    } else {
      // 2순위: 수동 벡터 검색 폴백
      if (rpcError) console.error('RPC error (using fallback):', rpcError.message);
      const fallbackCards = await manualSearch(db, userId, queryEmbedding, 5, platformFilter);
      cards = fallbackCards.slice(0, 3).map((c, i) => ({
        ...c,
        label: getCardLabel(i),
      }));
    }

    // platform 일치 여부 확인 (AI 답변용)
    const hasTypeMatch = !platformFilter ||
      cards.some((c) => getPlatform(c as unknown as Record<string, unknown>) === platformFilter);

    const message = await generateChatResponse(query, cards, {
      platformFilter,
      hasTypeMatch,
      // 팔로업일 때만 대화 맥락 전달 — 새 주제면 이전 대화 오염 방지
      history: isFollowUp ? recentHistory : [],
      searchIntent: isFollowUp ? searchIntent : undefined,
    });

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
