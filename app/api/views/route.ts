import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

export const runtime = 'nodejs';

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

export async function POST(req: NextRequest) {
  const { contentId, userId } = await req.json();
  if (!contentId || !userId) return NextResponse.json({ error: '파라미터 누락' }, { status: 400 });

  const db = admin();
  await db.from('content_views').insert({ content_id: contentId, user_id: userId });
  await db
    .from('contents')
    .update({ last_viewed_at: new Date().toISOString() })
    .eq('id', contentId)
    .eq('user_id', userId);

  return NextResponse.json({ success: true });
}
