// app/api/youtube-learn/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import OpenAI from 'openai';
import { YoutubeTranscript } from 'youtube-transcript';

export const runtime = 'nodejs';
export const maxDuration = 60;

// ── 공용 인스턴스 ─────────────────────────────────────────────
const ai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY! });

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );

// ── 유틸: YouTube 영상 ID 추출 ────────────────────────────────
function extractVideoId(url: string): string | null {
  const patterns = [
    /(?:youtube\.com\/watch\?v=)([^&\n?#]+)/,
    /(?:youtu\.be\/)([^&\n?#]+)/,
    /(?:youtube\.com\/embed\/)([^&\n?#]+)/,
    /(?:youtube\.com\/shorts\/)([^&\n?#]+)/,
  ];
  for (const p of patterns) {
    const m = url.match(p);
    if (m?.[1]) return m[1];
  }
  return null;
}

// ── 유틸: 썸네일 URL (고화질 → 일반화질 폴백 순서) ───────────
function getThumbnailUrl(videoId: string): string {
  // maxresdefault가 없을 경우 프론트에서 hqdefault로 폴백 처리 권장
  return `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`;
}

// ── Step 1: Vision API — 썸네일 이미지 분석 ──────────────────
async function analyzeThumbnail(thumbnailUrl: string): Promise<string> {
  const res = await ai.chat.completions.create({
    model: 'gpt-4o',
    max_tokens: 250,
    messages: [
      {
        role: 'user',
        content: [
          {
            type: 'image_url',
            image_url: { url: thumbnailUrl, detail: 'low' }, // 비용 절감
          },
          {
            type: 'text',
            text: '이 유튜브 썸네일을 분석해 주세요. ① 화면에 적힌 큰 텍스트 ② 핵심 사물이나 인물 ③ 전반적인 분위기를 간결하게 서술해 주세요.',
          },
        ],
      },
    ],
  });
  return res.choices[0].message.content?.trim() ?? '';
}

// ── Step 2: 자막 추출 (한국어 → 영어 → 자동생성 순 폴백) ─────
async function fetchTranscript(videoId: string): Promise<string> {
  const langCandidates = ['ko', 'en', 'en-US', 'en-GB'];

  for (const lang of langCandidates) {
    try {
      const segments = await YoutubeTranscript.fetchTranscript(videoId, { lang });
      if (segments.length) return segments.map((s: { text: string }) => s.text).join(' ');
    } catch {
      // 해당 언어 자막 없음 → 다음 시도
    }
  }

  // 마지막 폴백: 언어 코드 없이 시도 (YouTube 자동생성 자막)
  try {
    const segments = await YoutubeTranscript.fetchTranscript(videoId);
    return segments.map((s: { text: string }) => s.text).join(' ');
  } catch {
    return ''; // 자막 완전 없음
  }
}

// ── Step 3: GPT-4o-mini 종합 분석 ────────────────────────────
async function analyzeContent(params: {
  title: string;
  thumbnailAnalysis: string;
  transcript: string;
  hasTranscript: boolean;
}): Promise<{ summary: string; hashtags: string[]; category: string }> {
  const { title, thumbnailAnalysis, transcript, hasTranscript } = params;

  const transcriptSection = hasTranscript
    ? `자막 텍스트 (앞 3000자):\n${transcript.slice(0, 3000)}`
    : `자막: 없음 — 썸네일과 제목만으로 분석해 주세요.`;

  const res = await ai.chat.completions.create({
    model: 'gpt-4o-mini',
    response_format: { type: 'json_object' },
    temperature: 0.2,
    max_tokens: 400,
    messages: [
      {
        role: 'system',
        content: `당신은 유튜브 영상을 깊이 있게 분석하는 지식 아카이빙 어시스턴트입니다.
주어진 정보를 종합해 반드시 JSON 형식으로만 응답하세요.
카테고리는 반드시 '대분류 > 중분류 > 소분류' 형태여야 합니다.
예시: "운동 > 홈트 > 복근", "여행 > 일본 > 카페", "개발 > 프론트엔드 > React"`,
      },
      {
        role: 'user',
        content: `제목: ${title}
썸네일 분석 결과: ${thumbnailAnalysis || '(분석 실패)'}
${transcriptSection}

JSON 응답 포맷:
{
  "summary": "핵심 내용 3줄 요약. 각 줄은 ' / '로 구분해 한 문자열로 작성",
  "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5"],
  "category": "대분류 > 중분류 > 소분류"
}`,
      },
    ],
  });

  const raw = JSON.parse(res.choices[0].message.content || '{}');
  return {
    summary: typeof raw.summary === 'string' ? raw.summary : '',
    hashtags: Array.isArray(raw.hashtags) ? raw.hashtags : [],
    category:
      typeof raw.category === 'string' ? raw.category : '기타 > 미분류 > 미분류',
  };
}

// ── 메인 핸들러 ───────────────────────────────────────────────
export async function POST(req: NextRequest) {
  try {
    const { url, userId } = await req.json();

    if (!url || !userId) {
      return NextResponse.json(
        { error: 'url과 userId가 필요합니다.' },
        { status: 400 },
      );
    }

    const videoId = extractVideoId(url);
    if (!videoId) {
      return NextResponse.json(
        { error: '유효한 YouTube URL이 아닙니다.' },
        { status: 400 },
      );
    }

    const db = admin();

    // 중복 체크 (기존 route.ts 패턴 동일)
    const { data: existing } = await db
      .from('contents')
      .select('id, title, category, analysis_status')
      .eq('user_id', userId)
      .eq('url', url)
      .single();
    if (existing) return NextResponse.json({ duplicate: true, content: existing });

    // 선저장
    const { data: saved, error: saveError } = await db
      .from('contents')
      .insert({ user_id: userId, url, analysis_status: 'processing' })
      .select('id')
      .single();

    if (saveError || !saved) {
      console.error('[youtube-learn] 초기 저장 실패:', saveError);
      return NextResponse.json(
        { error: '초기 저장 실패', detail: saveError?.message },
        { status: 500 },
      );
    }
    const contentId = saved.id;

    try {
      const thumbnailUrl = getThumbnailUrl(videoId);

      // 썸네일 분석 + 자막 추출 병렬 실행 (독립 작업이므로 Promise.allSettled)
      const [thumbnailResult, transcriptResult] = await Promise.allSettled([
        analyzeThumbnail(thumbnailUrl),
        fetchTranscript(videoId),
      ]);

      const thumbnailAnalysis =
        thumbnailResult.status === 'fulfilled' ? thumbnailResult.value : '';
      const transcript =
        transcriptResult.status === 'fulfilled' ? transcriptResult.value : '';
      const hasTranscript = transcript.length > 50;

      if (thumbnailResult.status === 'rejected') {
        console.warn('[youtube-learn] 썸네일 분석 실패:', thumbnailResult.reason);
      }
      if (!hasTranscript) {
        console.warn('[youtube-learn] 자막 없음 또는 너무 짧음 — 폴백 모드');
      }

      // 제목: og:title 크롤링이 이상적이나, 여기서는 videoId 기반 임시값 사용
      // (실제 프로젝트에서는 crawlContent(url)의 title을 재사용 권장)
      const title = `YouTube: ${videoId}`;

      // 종합 분석
      const { summary, hashtags, category } = await analyzeContent({
        title,
        thumbnailAnalysis,
        transcript,
        hasTranscript,
      });

      // 임베딩 생성 (기존 generateEmbedding 패턴 동일)
      const embeddingInput = [title, summary, hashtags.join(' '), category]
        .filter(Boolean)
        .join(' ');

      const embRes = await ai.embeddings.create({
        model: 'text-embedding-3-small',
        input: embeddingInput,
      });
      const embedding = embRes.data[0].embedding;

      // embeddings 테이블 저장 (기존 route.ts 패턴 동일)
      await db.from('embeddings').insert({
        content_id: contentId,
        vec: JSON.stringify(embedding),
      });

      // contents 최종 업데이트 (기존 route.ts 패턴 동일)
      await db
        .from('contents')
        .update({
          title,
          summary,
          thumbnail_url: thumbnailUrl,
          category,
          hashtags,
          analysis_status: 'completed',
        })
        .eq('id', contentId);

      return NextResponse.json({
        id: contentId,
        title,
        category,
        summary,
        hashtags,
        has_transcript: hasTranscript,
        analysis_status: 'completed',
      });
    } catch (e: any) {
      console.error('[youtube-learn] 분석 오류:', e);
      await db
        .from('contents')
        .update({ analysis_status: 'failed' })
        .eq('id', contentId);
      return NextResponse.json(
        { error: 'YouTube 분석/저장 실패', detail: e.message },
        { status: 500 },
      );
    }
  } catch (err: any) {
    console.error('[youtube-learn] 치명적 오류:', err);
    return NextResponse.json(
      { error: '서버 오류', detail: err.message },
      { status: 500 },
    );
  }
}
