import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

export const runtime = 'nodejs';

const admin = () =>
  createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const userId = searchParams.get('userId');

    if (!userId) {
      return NextResponse.json({ error: 'userId가 필요합니다.' }, { status: 400 });
    }

    const db = admin();

    // 1) created_at 대신 saved_at 으로 이름 변경!
    const { data: contents, error } = await db
      .from('contents')
      .select('id, title, summary, thumbnail_url, category, url, saved_at')
      .eq('user_id', userId)
      .order('saved_at', { ascending: false });

    if (error) {
      console.error('Fetch error:', error);
      return NextResponse.json({ error: '조회 실패', detail: error.message }, { status: 500 });
    }

    // 2) 카테고리별로 예쁘게 분류해서 묶어주기
    const collections: Record<string, any> = {};
    
    contents?.forEach((item) => {
      // 💡 핵심: "여행 > 일본 > 나고야" 에서 '>' 를 기준으로 쪼갠 뒤 제일 앞의 "여행"만 가져옵니다.
      const fullCategory = item.category || '기타';
      const mainCategory = fullCategory.split('>')[0].trim(); 

      if (!collections[mainCategory]) {
        collections[mainCategory] = { category: mainCategory, total: 0, preview: [] };
      }
      collections[mainCategory].total += 1;
      
      // 미리보기는 최신 5개까지만
      if (collections[mainCategory].preview.length < 5) {
        collections[mainCategory].preview.push(item);
      }
    });

    return NextResponse.json(Object.values(collections));
  } catch (error: any) {
    console.error('Collections error:', error);
    return NextResponse.json({ error: '서버 치명적 오류', detail: error.message }, { status: 500 });
  }
}