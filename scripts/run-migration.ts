/**
 * Supabase platform 컬럼 백필 스크립트
 * 실행: npx tsx scripts/run-migration.ts
 */
import { config } from 'dotenv';
import { resolve } from 'path';
config({ path: resolve(process.cwd(), '.env.local') });

import { createClient } from '@supabase/supabase-js';

const db = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!,
);

// URL 패턴 → platform 매핑 (platform.ts 와 동일한 순서)
const PLATFORM_RULES: { pattern: string; platform: string }[] = [
  { pattern: '%youtube.com%',        platform: 'youtube'  },
  { pattern: '%youtu.be%',           platform: 'youtube'  },
  { pattern: '%n.news.naver.com%',   platform: 'news'     },
  { pattern: '%news.naver.com%',     platform: 'news'     },
  { pattern: '%mnews.naver.com%',    platform: 'news'     },
  { pattern: '%chosun.com%',         platform: 'news'     },
  { pattern: '%donga.com%',          platform: 'news'     },
  { pattern: '%joongang.co.kr%',     platform: 'news'     },
  { pattern: '%hani.co.kr%',         platform: 'news'     },
  { pattern: '%yna.co.kr%',          platform: 'news'     },
  { pattern: '%hankyung.com%',       platform: 'news'     },
  { pattern: '%mk.co.kr%',           platform: 'news'     },
  { pattern: '%zdnet.co.kr%',        platform: 'news'     },
  { pattern: '%etnews.com%',         platform: 'news'     },
  { pattern: '%smartstore.naver.com%', platform: 'shopping' },
  { pattern: '%shopping.naver.com%', platform: 'shopping' },
  { pattern: '%brand.naver.com%',    platform: 'shopping' },
  { pattern: '%blog.naver.com%',     platform: 'blog'     },
  { pattern: '%tistory.com%',        platform: 'blog'     },
  { pattern: '%velog.io%',           platform: 'blog'     },
  { pattern: '%brunch.co.kr%',       platform: 'blog'     },
  { pattern: '%medium.com%',         platform: 'blog'     },
  { pattern: '%substack.com%',       platform: 'blog'     },
  { pattern: '%github.com%',         platform: 'github'   },
  { pattern: '%instagram.com%',      platform: 'instagram'},
  { pattern: '%twitter.com%',        platform: 'twitter'  },
  { pattern: '%x.com%',             platform: 'twitter'  },
];

async function run() {
  console.log('🔧 platform 컬럼 백필 시작...\n');

  // NULL인 것만 가져오기
  const { data: nullRows, error: fetchErr } = await db
    .from('contents')
    .select('id, url')
    .is('platform', null);

  if (fetchErr) {
    console.error('❌ 데이터 조회 실패:', fetchErr.message);
    process.exit(1);
  }

  if (!nullRows || nullRows.length === 0) {
    console.log('✅ platform이 NULL인 행이 없습니다. 이미 최신 상태입니다.');
    return;
  }

  console.log(`  📊 NULL 행 ${nullRows.length}개 발견\n`);

  let updated = 0;
  let skipped = 0;

  for (const row of nullRows) {
    const url = (row.url as string).toLowerCase();

    // 첫 번째로 매칭되는 규칙 사용
    const matched = PLATFORM_RULES.find(({ pattern }) => {
      const re = pattern.replace(/%/g, '');
      return url.includes(re);
    });

    const platform = matched?.platform ?? 'web';

    const { error: updateErr } = await db
      .from('contents')
      .update({ platform })
      .eq('id', row.id);

    if (updateErr) {
      console.warn(`  ⚠️ id=${row.id} 업데이트 실패:`, updateErr.message);
      skipped++;
    } else {
      updated++;
    }
  }

  console.log(`  ✅ 업데이트 완료: ${updated}개 / 실패: ${skipped}개`);

  // thumbnail_description 컬럼 확인 (없으면 안내)
  console.log('\n─────────────────────────────────────────');
  console.log('💡 thumbnail_description 컬럼은 Supabase SQL Editor에서');
  console.log('   아래 SQL을 직접 실행해 주세요:');
  console.log('\n   ALTER TABLE contents ADD COLUMN IF NOT EXISTS thumbnail_description TEXT;\n');
}

run().catch(console.error);
