import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { crawlContent } from '@/lib/crawler';
import { analyzeContent, generateEmbedding } from '@/lib/openai';
import { runClustering } from '@/lib/clustering';

export const runtime = 'nodejs';
export const maxDuration = 60;

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

export async function POST(req: NextRequest) {
  try {
    const { url, userId } = await req.json();
    if (!url || !userId) {
      return NextResponse.json({ error: 'url과 userId가 필요합니다.' }, { status: 400 });
    }

    const db = admin();

    // 중복 URL 체크 (UNIQUE constraint: user_id + url)
    const { data: existing } = await db
      .from('contents')
      .select('id, title, hashtags, analysis_status')
      .eq('user_id', userId)
      .eq('url', url)
      .single();

    if (existing) {
      return NextResponse.json({ duplicate: true, content: existing });
    }

    // 1. 즉시 저장 (분석 전 — 사용자를 기다리게 하지 않음)
    const { data: saved, error: saveError } = await db
      .from('contents')
      .insert({
        user_id: userId,
        url,
        content_type: 'other',
        analysis_status: 'processing',
        saved_at: new Date().toISOString(),
      })
      .select('id')
      .single();

    if (saveError || !saved) {
      return NextResponse.json({ error: '저장 실패' }, { status: 500 });
    }

    const contentId = saved.id;

    try {
      // 2. 크롤링
      const crawled = await crawlContent(url);

      // 3. AI 분석
      const analysisText =
        crawled.raw_text || crawled.description || crawled.title || '';
      const analysis = await analyzeContent(analysisText, crawled.title, crawled.content_type);

      // 4. 임베딩 생성
      const embeddingInput = [
        crawled.title,
        analysis.topics.join(' '),
        analysis.moods.join(' '),
        analysis.compressed_text,
      ]
        .filter(Boolean)
        .join(' ');
      const embedding = await generateEmbedding(embeddingInput);

      // 5. contents 업데이트
      await db.from('contents').update({
        content_type: crawled.content_type,
        title: crawled.title,
        description: crawled.description,
        thumbnail_url: crawled.thumbnail_url,
        author: crawled.author,
        metadata: crawled.metadata,
        topics: analysis.topics,
        moods: analysis.moods,
        intent: analysis.intent,
        energy: analysis.energy,
        hashtags: analysis.hashtags,
        analysis_status: 'completed',
        analyzed_at: new Date().toISOString(),
      }).eq('id', contentId);

      // 6. embeddings 테이블에 별도 저장
      await db.from('embeddings').insert({
        content_id: contentId,
        embedding: JSON.stringify(embedding),
      });

      // 7. 완료된 콘텐츠 수 확인 → 30개 이상이면 클러스터링
      const { count } = await db
        .from('contents')
        .select('*', { count: 'exact', head: true })
        .eq('user_id', userId)
        .eq('analysis_status', 'completed');

      if ((count ?? 0) >= 30) {
        runClustering(userId).catch(console.error);
      }

      return NextResponse.json({
        id: contentId,
        title: crawled.title,
        thumbnail_url: crawled.thumbnail_url,
        content_type: crawled.content_type,
        hashtags: analysis.hashtags,
        metadata: crawled.metadata,
        analysis_status: 'completed',
      });
    } catch (analysisError) {
      console.error('analysis error:', analysisError);
      await db
        .from('contents')
        .update({ analysis_status: 'failed' })
        .eq('id', contentId);
      return NextResponse.json({ error: '분석 실패', contentId }, { status: 500 });
    }
  } catch (err) {
    console.error('ingest error:', err);
    return NextResponse.json({ error: '서버 오류' }, { status: 500 });
  }
}
