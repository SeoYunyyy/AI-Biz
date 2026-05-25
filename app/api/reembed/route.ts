/**
 * POST /api/reembed
 * 기존 콘텐츠의 썸네일 Vision 분석 후 임베딩 재생성 (일회성 Backfill)
 * Body: { userId: string, limit?: number }
 */
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { analyzeThumbnailVision, generateEmbedding } from '@/lib/openai';

export const runtime = 'nodejs';
export const maxDuration = 300; // 최대 5분

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

export async function POST(req: NextRequest) {
  try {
    const { userId, limit = 50 } = await req.json();
    if (!userId) {
      return NextResponse.json({ error: 'userId가 필요합니다.' }, { status: 400 });
    }

    const db = admin();

    // 1) 이 유저의 완료된 콘텐츠 목록 가져오기
    const { data: contents, error } = await db
      .from('contents')
      .select('id, title, thumbnail_url, summary, category, hashtags')
      .eq('user_id', userId)
      .eq('analysis_status', 'completed')
      .limit(limit);

    if (error || !contents?.length) {
      return NextResponse.json({ error: '콘텐츠 없음', detail: error?.message }, { status: 400 });
    }

    let processed = 0;
    let failed = 0;
    const results: { id: string; title: string; hasVision: boolean }[] = [];

    for (const content of contents) {
      try {
        // 2) 썸네일 Vision 분석
        let thumbnailDescription = '';
        if (content.thumbnail_url) {
          thumbnailDescription = await analyzeThumbnailVision(
            content.thumbnail_url,
            content.title || ''
          );
        }

        // 3) 임베딩 재생성 (기존 텍스트 + 썸네일 설명 포함)
        const embeddingInput = [
          content.title,
          (content.hashtags ?? []).join(' '),
          content.summary,
          thumbnailDescription,
        ]
          .filter(Boolean)
          .join(' ');

        const embedding = await generateEmbedding(embeddingInput);

        // 4) embeddings 테이블 업서트 (기존 행 있으면 덮어쓰기)
        const { error: embedError } = await db
          .from('embeddings')
          .upsert(
            { content_id: content.id, vec: JSON.stringify(embedding) },
            { onConflict: 'content_id' }
          );

        // 5) thumbnail_description 저장
        await db
          .from('contents')
          .update({ thumbnail_description: thumbnailDescription || null })
          .eq('id', content.id);

        if (embedError) {
          console.error(`embed upsert error for ${content.id}:`, embedError);
          failed++;
        } else {
          processed++;
        }

        results.push({
          id: content.id,
          title: content.title || '제목 없음',
          hasVision: !!thumbnailDescription,
        });

        // API 속도 제한 방지: 각 콘텐츠 처리 후 짧은 대기
        await new Promise((r) => setTimeout(r, 200));
      } catch (e) {
        console.error(`reembed failed for ${content.id}:`, e);
        failed++;
      }
    }

    return NextResponse.json({
      processed,
      failed,
      total: contents.length,
      results,
    });
  } catch (err) {
    console.error('reembed error:', err);
    return NextResponse.json({ error: '서버 오류' }, { status: 500 });
  }
}
