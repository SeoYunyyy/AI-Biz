/**
 * 크롤러 테스트 스크립트
 * 실행: npx tsx scripts/test-crawler.ts [URL]
 *
 * URL을 인자로 주면 그 URL만 테스트:
 *   npx tsx scripts/test-crawler.ts https://blog.naver.com/xxx/123
 *
 * 인자 없으면 기본 테스트 케이스 실행
 */

// .env.local 로드
import { config } from 'dotenv';
import { resolve } from 'path';
config({ path: resolve(process.cwd(), '.env.local') });

import { crawlContent } from '../lib/crawler';

const DEFAULT_URLS = [
  // YouTube
  'https://youtu.be/tYM4oISacwY',
  // 일반 블로그 (Readability)
  'https://velog.io/@velopert/react-hooks',
  // 뉴스
  'https://n.news.naver.com/article/092/0002359456',
];

async function run() {
  const urls = process.argv[2] ? [process.argv[2]] : DEFAULT_URLS;

  for (const url of urls) {
    console.log('\n' + '='.repeat(60));
    console.log('URL:', url);
    console.log('='.repeat(60));
    try {
      const result = await crawlContent(url);
      console.log('✅ title       :', result.title);
      console.log('   type        :', result.content_type);
      console.log('   author      :', result.author ?? '없음');
      console.log('   thumbnail   :', result.thumbnail_url ? '있음' : '없음');
      console.log('   description :', (result.description ?? '').slice(0, 80));
      console.log('   raw_text    :', (result.raw_text ?? '').slice(0, 100) + '...');
      console.log('   metadata    :', JSON.stringify(result.metadata));
    } catch (e) {
      console.log('❌ 실패:', (e as Error).message);
    }
  }
}

run();
