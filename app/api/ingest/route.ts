import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { crawlContent } from '@/lib/crawler';
import { analyzeContent, generateEmbedding } from '@/lib/openai';
import { runClustering } from '@/lib/clustering';
import { classifyContent } from '@/lib/classifier';

export const runtime = 'nodejs';
export const maxDuration = 60;

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );

export async function POST(req: NextRequest) {
  try {
    const { url, userId } = await req.json();
    if (!url || !userId) {
      return NextResponse.json({ error: 'url과 userId가 필요합니다.' }, { status: 400 });
    }

    const db = admin();

    // 중복 체크 (DB에 남겨둔 컬럼만 조회)
    const { data: existing } = await db
      .from('contents')
      .select('id, title, category, analysis_status')
      .eq('user_id', userId).eq('url', url).single();
    if (existing) return NextResponse.json({ duplicate: true, content: existing });

    // 1) 선저장 (삭제된 컬럼 빼고 심플하게 삽입)
    const { data: saved, error: saveError } = await db
      .from('contents')
      .insert({
        user_id: userId, 
        url: url,
        analysis_status: 'processing'
      })
      .select('id').single();
      
    if (saveError || !saved) {
      console.error('Save error details:', saveError);
      return NextResponse.json({ error: '초기 저장 실패', detail: saveError?.message }, { status: 500 });
    }
    const contentId = saved.id;

    try {
      // 2) 크롤링
      const crawled = await crawlContent(url);

      // 3) AI 분석
      const analysisText = crawled.raw_text || crawled.description || crawled.title || '';
      const analysis = await analyzeContent(analysisText, crawled.title, crawled.content_type);

      // 4) 임베딩 생성
      const embeddingInput = [
        crawled.title, analysis.topics.join(' '),
        analysis.moods.join(' '), analysis.compressed_text,
      ].filter(Boolean).join(' ');
      const embedding = await generateEmbedding(embeddingInput);

      // 새로 만든 embeddings 테이블의 'vec' 컬럼에 저장
      await db.from('embeddings').insert({
        content_id: contentId,
        vec: JSON.stringify(embedding), 
      });

      // 5) 분류기 호출 (수정됨)
      const { category, generatedHashtags, confidence, model } = await classifyContent({
        title: crawled.title,
        description: crawled.description,
        topics: analysis.topics,
        moods: analysis.moods,
        embedding,
      });

      // 6) contents 최종 업데이트 (hashtags 기둥 추가!)
      await db.from('contents').update({
        title: crawled.title,
        summary: analysis.compressed_text || crawled.description,
        thumbnail_url: crawled.thumbnail_url,
        category: category,             // '대분류 > 중분류 > 소분류' 저장
        hashtags: generatedHashtags,    // 🔥 AI가 뽑아낸 태그들 저장!
        analysis_status: 'completed'
      }).eq('id', contentId);

      // (선택) 클러스터링 트리거
      const { count } = await db
        .from('contents').select('*', { count: 'exact', head: true })
        .eq('user_id', userId).eq('analysis_status', 'completed');
      if ((count ?? 0) >= 30) runClustering(userId).catch(console.error);

      return NextResponse.json({
        id: contentId,
        title: crawled.title,
        category,
        analysis_status: 'completed',
      });
      
    } catch (e: any) {
      console.error('Analysis error:', e);
      await db.from('contents').update({ analysis_status: 'failed' }).eq('id', contentId);
      return NextResponse.json({ error: 'AI 분석/저장 실패', detail: e.message }, { status: 500 });
    }
  } catch (err: any) {
    console.error('Ingest error:', err);
    return NextResponse.json({ error: '서버 치명적 오류', detail: err.message }, { status: 500 });
  }
}