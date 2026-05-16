import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

export const runtime = 'nodejs';

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

export async function GET(req: NextRequest) {
  const userId = req.nextUrl.searchParams.get('userId');
  if (!userId) return NextResponse.json({ error: 'userId 필요' }, { status: 400 });

  const db = admin();

  // 컬렉션 목록 (1:N — contents는 별도 쿼리로 가져옴)
  const { data: collections, error } = await db
    .from('collections')
    .select('id, name, emoji, content_count, is_user_renamed, last_accessed_at, created_at, updated_at')
    .eq('user_id', userId)
    .order('updated_at', { ascending: false });

  if (error) return NextResponse.json({ error: '컬렉션 로드 실패' }, { status: 500 });

  // 각 컬렉션의 콘텐츠를 별도로 조회 (최대 10개 미리보기)
  const enriched = await Promise.all(
    (collections || []).map(async (col) => {
      const { data: contents } = await db
        .from('contents')
        .select(
          'id, url, content_type, title, thumbnail_url, author, metadata, hashtags, topics, moods, collection_id, saved_at'
        )
        .eq('collection_id', col.id)
        .eq('user_id', userId)
        .order('saved_at', { ascending: false })
        .limit(10);

      return { ...col, contents: contents || [] };
    })
  );

  return NextResponse.json({ collections: enriched });
}

export async function PATCH(req: NextRequest) {
  const { collectionId, name, userId } = await req.json();
  if (!collectionId || !name || !userId) {
    return NextResponse.json({ error: '파라미터 누락' }, { status: 400 });
  }

  const db = admin();
  const { error } = await db
    .from('collections')
    .update({ name, is_user_renamed: true, updated_at: new Date().toISOString() })
    .eq('id', collectionId)
    .eq('user_id', userId);

  if (error) return NextResponse.json({ error: '수정 실패' }, { status: 500 });
  return NextResponse.json({ success: true });
}
