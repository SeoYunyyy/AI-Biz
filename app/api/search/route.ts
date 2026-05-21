import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { generateEmbedding } from '@/lib/openai';

export const runtime = 'nodejs';

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

export async function POST(req: NextRequest) {
  try {
    const { userId, query } = await req.json();

    if (!userId || !query) {
      return NextResponse.json({ error: 'userId와 query가 필요합니다.' }, { status: 400 });
    }

    const db = admin();

    // 1) 사용자가 입력한 검색어를 벡터(숫자)로 변환
    const queryEmbedding = await generateEmbedding(query);

    // 2) DB에 만들어둔 검색 함수(RPC) 호출 (새 파라미터 이름 적용)
    const { data: results, error } = await db.rpc('search_user_contents', {
      query_embedding: JSON.stringify(queryEmbedding),
      p_user_id: userId,
      p_category: null, 
      match_count: 5    
    });

    if (error) {
      console.error('Search RPC error:', error);
      return NextResponse.json({ error: '검색 실패', detail: error.message }, { status: 500 });
    }

    return NextResponse.json({ cards: results });
  } catch (error: any) {
    console.error('Search error:', error);
    return NextResponse.json({ error: '서버 치명적 오류', detail: error.message }, { status: 500 });
  }
}