// app/api/find-content/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import OpenAI from 'openai';

export const runtime = 'nodejs';
export const maxDuration = 30;

// ── 공용 인스턴스 ─────────────────────────────────────────────
const ai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY! });

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );

// ── 타입 ──────────────────────────────────────────────────────
interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ContentResult {
  id: string;
  title: string;
  thumbnail_url: string | null;
  hashtags: string[];
  category: string;
  summary: string | null;
  similarity: number;
}

// ── Step 1: LLM 라우팅 — 모호함 감지 ─────────────────────────
async function detectAmbiguity(
  query: string,
  history: ChatMessage[],
): Promise<{ isAmbiguous: boolean; clarificationQuestion?: string }> {
  const historyText =
    history.length
      ? history.map(m => `${m.role === 'user' ? '사용자' : '어시스턴트'}: ${m.content}`).join('\n')
      : '(이전 대화 없음)';

  const res = await ai.chat.completions.create({
    model: 'gpt-4o-mini',
    response_format: { type: 'json_object' },
    temperature: 0.2,
    max_tokens: 200,
    messages: [
      {
        role: 'system',
        content: `당신은 지식 아카이빙 플랫폼의 검색 라우터입니다.
사용자의 검색어가 DB에서 명확한 콘텐츠를 찾기에 충분히 구체적인지 판단하세요.

[모호한 예시] "카페", "요즘 듣는 거", "뭔가 재미있는 거", "좋은 영상"
[구체적인 예시] "일본 교토 카페 브이로그", "로파이 힙합 공부 플레이리스트", "리액트 상태관리 강의"

이전 대화 맥락도 고려하여 판단하세요.
모호하다면 '플랫폼(유튜브/블로그 등)', '콘텐츠 내용(주제)', '분위기(편안함/자극적 등)' 중
하나를 좁힐 수 있는 짧고 자연스러운 질문을 생성하세요.

JSON 응답 형식:
{
  "isAmbiguous": true 또는 false,
  "clarificationQuestion": "모호할 때만 작성. 없으면 빈 문자열"
}`,
      },
      {
        role: 'user',
        content: `이전 대화:\n${historyText}\n\n현재 검색어: "${query}"`,
      },
    ],
  });

  const raw = JSON.parse(res.choices[0].message.content || '{}');
  return {
    isAmbiguous: raw.isAmbiguous === true,
    clarificationQuestion:
      typeof raw.clarificationQuestion === 'string' && raw.clarificationQuestion
        ? raw.clarificationQuestion
        : undefined,
  };
}

// ── Step 2: 임베딩 생성 + pgvector 유사도 검색 ───────────────
async function vectorSearch(
  query: string,
  userId: string,
  db: ReturnType<typeof admin>,
  count = 5,
): Promise<ContentResult[]> {
  const embRes = await ai.embeddings.create({
    model: 'text-embedding-3-small',
    input: query,
  });

  const { data, error } = await db.rpc('match_contents', {
    query_embedding: embRes.data[0].embedding,
    match_threshold: 0.3,
    match_count: count,
    p_user_id: userId,
  });

  if (error) throw new Error(`벡터 검색 실패: ${error.message}`);
  return (data as ContentResult[]) ?? [];
}

// ── Step 3: 검색 결과 안내 멘트 생성 ─────────────────────────
async function generateGuideMessage(
  query: string,
  results: ContentResult[],
): Promise<string> {
  if (!results.length) {
    return `"${query}"에 관련된 저장된 콘텐츠가 없어요. 다른 키워드로 검색하거나, 링크를 새로 저장해보세요!`;
  }

  const resultSummary = results
    .map((r, i) => `${i + 1}. [${r.category}] ${r.title}`)
    .join('\n');

  const res = await ai.chat.completions.create({
    model: 'gpt-4o-mini',
    temperature: 0.5,
    max_tokens: 120,
    messages: [
      {
        role: 'system',
        content: '당신은 친근한 지식 아카이빙 어시스턴트입니다. 검색 결과를 자연스럽고 간결하게 안내하는 한두 문장을 한국어로 작성하세요.',
      },
      {
        role: 'user',
        content: `검색어: "${query}"\n검색 결과:\n${resultSummary}\n\n이 결과를 안내하는 짧고 친근한 멘트를 써주세요. 추가 조건(플랫폼, 분위기 등)을 말해주면 더 정확히 찾을 수 있다는 뉘앙스도 자연스럽게 포함해주세요.`,
      },
    ],
  });

  return (
    res.choices[0].message.content?.trim() ??
    `${results.length}개의 콘텐츠 후보를 찾았어요! 더 구체적인 조건이 있으면 말씀해 주세요.`
  );
}

// ── 메인 핸들러 ───────────────────────────────────────────────
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { query, history = [], userId } = body as {
      query: string;
      history: ChatMessage[];
      userId: string;
    };

    if (!query?.trim()) {
      return NextResponse.json({ error: 'query가 비어 있습니다.' }, { status: 400 });
    }
    if (!userId) {
      return NextResponse.json({ error: 'userId가 필요합니다.' }, { status: 400 });
    }

    const db = admin();

    // 1단계: 모호함 감지
    const { isAmbiguous, clarificationQuestion } = await detectAmbiguity(query, history);

    if (isAmbiguous && clarificationQuestion) {
      return NextResponse.json({
        status: 'need_clarification',
        message: clarificationQuestion,
        results: [],
      });
    }

    // 2단계: 벡터 검색 (TOP 5)
    const results = await vectorSearch(query, userId, db, 5);

    // 3단계: 안내 멘트 생성
    const message = await generateGuideMessage(query, results);

    return NextResponse.json({
      status: results.length > 0 ? 'success' : 'no_results',
      message,
      results: results.map(r => ({
        id: r.id,
        title: r.title,
        thumbnail_url: r.thumbnail_url,
        hashtags: r.hashtags,
        category: r.category,
        similarity: Math.round(r.similarity * 1000) / 1000, // 소수점 3자리
      })),
    });
  } catch (err: any) {
    console.error('[find-content] error:', err);
    return NextResponse.json(
      { error: '검색 중 오류가 발생했습니다.', detail: err.message },
      { status: 500 },
    );
  }
}
