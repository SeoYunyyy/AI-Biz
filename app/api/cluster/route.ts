import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { runClustering } from '@/lib/clustering';

export const runtime = 'nodejs';
export const maxDuration = 120;

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

export async function POST(req: NextRequest) {
  try {
    const { userId } = await req.json();
    if (!userId) return NextResponse.json({ error: 'userId 필요' }, { status: 400 });

    const db = admin();

    // 분석 완료된 콘텐츠 수 확인
    const { count } = await db
      .from('contents')
      .select('*', { count: 'exact', head: true })
      .eq('user_id', userId)
      .eq('analysis_status', 'completed');

    if ((count ?? 0) < 3) {
      return NextResponse.json({
        error: `컬렉션 생성에는 최소 3개의 분석 완료 콘텐츠가 필요합니다. (현재: ${count ?? 0}개)`,
      }, { status: 400 });
    }

    await runClustering(userId);
    return NextResponse.json({ success: true, message: '컬렉션이 생성됐어요!' });
  } catch (err) {
    console.error('cluster error:', err);
    return NextResponse.json({ error: '클러스터링 실패: ' + String(err) }, { status: 500 });
  }
}
