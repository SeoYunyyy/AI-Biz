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
  const limit = parseInt(req.nextUrl.searchParams.get('limit') || '20');
  const offset = parseInt(req.nextUrl.searchParams.get('offset') || '0');

  if (!userId) return NextResponse.json({ error: 'userId 필요' }, { status: 400 });

  const db = admin();

  const { data, error, count } = await db
    .from('contents')
    .select(
      'id, url, content_type, title, thumbnail_url, author, metadata, hashtags, topics, moods, collection_id, analysis_status, saved_at',
      { count: 'exact' }
    )
    .eq('user_id', userId)
    .order('saved_at', { ascending: false })
    .range(offset, offset + limit - 1);

  if (error) return NextResponse.json({ error: '콘텐츠 로드 실패' }, { status: 500 });

  return NextResponse.json({ contents: data || [], total: count || 0 });
}
