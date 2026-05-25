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
      'id, url, title, summary, thumbnail_url, category, hashtags, analysis_status, saved_at',
      { count: 'exact' }
    )
    .eq('user_id', userId)
    .order('saved_at', { ascending: false })
    .range(offset, offset + limit - 1);

  if (error) return NextResponse.json({ error: '콘텐츠 로드 실패' }, { status: 500 });

  // DB 컬럼을 ContentCard 형식으로 매핑 (content_type은 URL에서 추론)
  const contents = (data || []).map((c: Record<string, unknown>) => ({
    ...c,
    content_type: typeof c.url === 'string' && /youtube\.com|youtu\.be/.test(c.url) ? 'youtube' : 'blog',
    author: null,
    metadata: null,
    topics: [],
    moods: [],
    collection_id: null,
  }));

  return NextResponse.json({ contents, total: count || 0 });
}
