import type { CrawledContent } from '@/types';
import { isYouTubeUrl, fetchYouTubeMetadata } from './youtube';
import { JSDOM } from 'jsdom';
import { Readability } from '@mozilla/readability';

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const TIMEOUT = 12_000;

// ── URL 분류 ─────────────────────────────────────────────────────

function isNaverShopping(url: string): boolean {
  return (
    /smartstore\.naver\.com|brand\.naver\.com/.test(url) ||
    /shopping\.naver\.com|search\.shopping\.naver\.com/.test(url)
  );
}

function isNaverBlog(url: string): boolean {
  return /blog\.naver\.com/.test(url);
}

// ── 메인 엔트리 ──────────────────────────────────────────────────

export async function crawlContent(url: string): Promise<CrawledContent> {
  if (isYouTubeUrl(url)) return fetchYouTubeMetadata(url);
  if (isNaverShopping(url)) return crawlNaverShopping(url);
  if (isNaverBlog(url)) return crawlNaverBlog(url);
  return crawlGeneral(url);
}

// ── 1. 네이버 쇼핑 ──────────────────────────────────────────────

async function crawlNaverShopping(url: string): Promise<CrawledContent> {
  const clientId = process.env.NAVER_CLIENT_ID;
  const clientSecret = process.env.NAVER_CLIENT_SECRET;

  // ① URL에서 스토어명·상품ID 파싱 (JS 렌더링 우회용 검색 쿼리 생성)
  const storeMatch = url.match(/smartstore\.naver\.com\/([^\/\?#]+)/i)
    || url.match(/brand\.naver\.com\/([^\/\?#]+)/i);
  const productIdMatch = url.match(/\/products\/(\d+)/i);
  const storeName = storeMatch?.[1] ?? null;
  const productId = productIdMatch?.[1] ?? null;

  // ② Naver Shopping 검색 API (API 키 있을 때)
  if (clientId && clientSecret) {
    // 검색 쿼리: productId > storeName > URL fallback
    const rawQuery = productId ?? storeName ?? url.split('/').filter(Boolean).pop() ?? '';
    const query = encodeURIComponent(rawQuery.slice(0, 80));

    try {
      const apiRes = await fetch(
        `https://openapi.naver.com/v1/search/shop.json?query=${query}&display=3&sort=sim`,
        {
          headers: {
            'X-Naver-Client-Id': clientId,
            'X-Naver-Client-Secret': clientSecret,
          },
          signal: AbortSignal.timeout(8_000),
        }
      );

      if (apiRes.ok) {
        const apiData = await apiRes.json();
        // URL이 포함된 결과 우선, 없으면 첫 번째 결과
        const items: Record<string, string>[] = apiData.items ?? [];
        const item = items.find((i) => i.link && url.includes(productId ?? '')) ?? items[0];

        if (item) {
          const title = decode(item.title?.replace(/<[^>]+>/g, '') || '');
          const price = item.lprice ? `${Number(item.lprice).toLocaleString()}원` : null;
          const category = [item.category1, item.category2, item.category3].filter(Boolean).join(' > ');
          const description = [
            category,
            price ? `최저가 ${price}` : '',
            item.mallName ? `판매처: ${item.mallName}` : '',
          ].filter(Boolean).join(' | ');

          return {
            title: title || `${storeName ?? '네이버'} 쇼핑 상품`,
            description,
            thumbnail_url: item.image || null,
            author: item.mallName || storeName || null,
            metadata: {
              site_name: '네이버 쇼핑',
              source_url: url,
              price: item.lprice,
              category1: item.category1,
              category2: item.category2,
              category3: item.category3,
              mall_name: item.mallName,
              product_id: item.productId ?? productId,
            },
            raw_text: [title, description, category].filter(Boolean).join('\n'),
            content_type: 'other',
          };
        }
      }
    } catch (e) {
      console.warn('[Crawler] 네이버 쇼핑 API 실패:', e);
    }
  }

  // ③ API 키 없거나 API 실패 → URL 정보만으로 최소 결과 반환
  console.warn('[Crawler] NAVER API 키 없음 또는 실패 → URL 기반 최소 정보 반환');
  const fallbackTitle = storeName
    ? `${storeName} 스토어 상품`
    : '네이버 쇼핑 상품';

  return {
    title: fallbackTitle,
    description: productId ? `상품 ID: ${productId}` : '',
    thumbnail_url: null,
    author: storeName ?? null,
    metadata: {
      site_name: '네이버 쇼핑',
      source_url: url,
      store_name: storeName,
      product_id: productId,
    },
    raw_text: [fallbackTitle, storeName, productId].filter(Boolean).join(' '),
    content_type: 'other',
  };
}

// ── 2. 네이버 블로그 ─────────────────────────────────────────────
// Naver Blog는 JS SPA → 서버사이드 직접 크롤 불가
// 전략: ① Naver Blog Search API (API 키 있을 때, 제목+설명 획득)
//        ② PostView HTML에서 OG 메타 추출
//        ③ 최소 정보 반환

async function crawlNaverBlog(url: string): Promise<CrawledContent> {
  const { blogId, logNo } = extractNaverBlogIds(url);
  const clientId = process.env.NAVER_CLIENT_ID;
  const clientSecret = process.env.NAVER_CLIENT_SECRET;

  // ① Naver Blog Search API로 포스트 정보 획득 (API 키 있을 때)
  if (clientId && clientSecret && blogId && logNo) {
    try {
      // blogId를 쿼리로 검색해 logNo가 일치하는 포스트 찾기
      const query = encodeURIComponent(blogId);
      const apiRes = await fetch(
        `https://openapi.naver.com/v1/search/blog.json?query=${query}&display=20&sort=date`,
        {
          headers: {
            'X-Naver-Client-Id': clientId,
            'X-Naver-Client-Secret': clientSecret,
          },
          signal: AbortSignal.timeout(8_000),
        }
      );

      if (apiRes.ok) {
        const apiData = await apiRes.json();
        interface BlogItem { title: string; description: string; bloggername: string; link: string; thumbnail?: string; }
        const items: BlogItem[] = apiData.items ?? [];
        // logNo가 link URL에 포함된 항목 우선
        const matched = items.find((i) => i.link?.includes(logNo)) ?? items[0];

        if (matched) {
          const title = decode(matched.title?.replace(/<[^>]+>/g, '') || '');
          const description = decode(matched.description?.replace(/<[^>]+>/g, '') || '');
          return {
            title: title || `${matched.bloggername ?? blogId} 블로그`,
            description,
            thumbnail_url: matched.thumbnail ?? null,
            author: matched.bloggername || blogId,
            metadata: {
              site_name: '네이버 블로그',
              source_url: url,
              blog_id: blogId,
              log_no: logNo,
            },
            raw_text: [title, description].filter(Boolean).join('\n'),
            content_type: 'blog',
          };
        }
      }
    } catch (e) {
      console.warn('[Crawler] 네이버 블로그 Search API 실패:', e);
    }
  }

  // ② PostView HTML에서 OG 메타 추출 (블로그 홈 레벨이지만 썸네일·저자는 얻을 수 있음)
  if (blogId && logNo) {
    const postViewUrl = `https://blog.naver.com/PostView.naver?blogId=${blogId}&logNo=${logNo}`;
    try {
      const html = await fetchHtmlPermissive(postViewUrl);
      if (html.length > 10_000) {
        const ogTitle    = extractOgTag(html, 'title');
        const thumbnail_url = toAbsolute(extractOgTag(html, 'image'), postViewUrl);
        const description = extractOgTag(html, 'description') || extractMetaName(html, 'description');
        // og:title이 블로그 홈 제목이면 버림
        const isPostTitle = ogTitle && !ogTitle.includes('네이버 블로그') && !ogTitle.toUpperCase().includes('NAVER');
        if (isPostTitle || thumbnail_url) {
          return {
            title: isPostTitle ? ogTitle! : `${blogId} 블로그 포스트`,
            description,
            thumbnail_url,
            author: blogId,
            metadata: { site_name: '네이버 블로그', source_url: url, blog_id: blogId, log_no: logNo },
            raw_text: [ogTitle, description].filter(Boolean).join('\n'),
            content_type: 'blog',
          };
        }
      }
    } catch { /* 무시 */ }
  }

  // ③ 최후 폴백: URL 정보만으로 최소 반환
  console.warn('[Crawler] Naver Blog 크롤 실패 → 최소 정보 반환 (NAVER_CLIENT_ID 설정 권장)');
  return {
    title: blogId ? `${blogId} 네이버 블로그` : '네이버 블로그',
    description: logNo ? `포스트 번호: ${logNo}` : '',
    thumbnail_url: null,
    author: blogId ?? null,
    metadata: { site_name: '네이버 블로그', source_url: url, blog_id: blogId, log_no: logNo },
    raw_text: '',
    content_type: 'blog',
  };
}

/** URL에서 blogId / logNo 추출 */
function extractNaverBlogIds(url: string): {
  blogId: string | null;
  logNo: string | null;
} {
  // 패턴 1: blog.naver.com/{blogId}/{logNo}
  const pathMatch = url.match(/blog\.naver\.com\/([^\/\?#]+)\/([0-9]+)/);
  if (pathMatch) return { blogId: pathMatch[1], logNo: pathMatch[2] };

  // 패턴 2: ?blogId=xxx&logNo=yyy (순서 무관)
  const blogIdMatch = url.match(/[?&]blogId=([^&]+)/);
  const logNoMatch = url.match(/[?&]logNo=([0-9]+)/);
  if (blogIdMatch || logNoMatch) {
    return {
      blogId: blogIdMatch?.[1] ?? null,
      logNo: logNoMatch?.[1] ?? null,
    };
  }

  return { blogId: null, logNo: null };
}

// ── 3. 일반 웹사이트 (Readability) ──────────────────────────────

async function crawlGeneral(url: string): Promise<CrawledContent> {
  const html = await fetchHtml(url);
  const { title: readTitle, raw_text } = readabilityExtract(html, url);

  const ogTitle = extractOgTag(html, 'title');
  const thumbnail_url = toAbsolute(extractOgTag(html, 'image'), url);
  const author =
    extractOgTag(html, 'article:author') || extractMetaName(html, 'author') || null;
  const description =
    extractOgTag(html, 'description') ||
    extractMetaName(html, 'description') ||
    raw_text.slice(0, 200);
  const siteName = extractOgTag(html, 'site_name');

  return {
    title: readTitle || ogTitle || extractTitleTag(html) || 'Untitled',
    description,
    thumbnail_url,
    author,
    metadata: {
      site_name: siteName || null,
      source_url: url,
    },
    raw_text,
    content_type: 'blog',
  };
}

// ── Readability로 순수 본문 추출 ─────────────────────────────────

function readabilityExtract(
  html: string,
  url: string
): { title: string; raw_text: string } {
  try {
    const dom = new JSDOM(html, { url });
    const reader = new Readability(dom.window.document);
    const article = reader.parse();

    if (article) {
      return {
        title: article.title?.trim() ?? '',
        raw_text:
          article.textContent?.replace(/\s+/g, ' ').trim().slice(0, 8_000) ?? '',
      };
    }
  } catch (e) {
    console.warn('[Crawler] Readability 실패, 폴백 사용:', e);
  }

  // Readability 실패 시 regex 폴백
  return {
    title: extractTitleTag(html),
    raw_text: extractTextFallback(html),
  };
}

// ── 공통 유틸 ────────────────────────────────────────────────────

const FETCH_HEADERS = {
  'User-Agent': UA,
  Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
  'Cache-Control': 'no-cache',
};

/** 2xx 만 허용 */
async function fetchHtml(url: string): Promise<string> {
  const res = await fetch(url, { headers: FETCH_HEADERS, signal: AbortSignal.timeout(TIMEOUT) });
  if (!res.ok) throw new Error(`페이지 로드 실패: ${res.status} — ${url}`);
  return res.text();
}

/** 4xx 도 허용 (Naver Blog PostView 처럼 404지만 HTML을 반환하는 경우) */
async function fetchHtmlPermissive(url: string): Promise<string> {
  const res = await fetch(url, { headers: FETCH_HEADERS, signal: AbortSignal.timeout(TIMEOUT) });
  // 5xx는 예외, 4xx는 내용을 그냥 반환
  if (res.status >= 500) throw new Error(`서버 오류: ${res.status} — ${url}`);
  return res.text();
}

/** og: 또는 article: 메타 태그 content 추출 */
function extractOgTag(html: string, property: string): string {
  const re = new RegExp(
    `<meta[^>]+property=["'](?:og:|article:)${property}["'][^>]+content=["']([^"']{1,1000})["']`,
    'i'
  );
  const re2 = new RegExp(
    `<meta[^>]+content=["']([^"']{1,1000})["'][^>]+property=["'](?:og:|article:)${property}["']`,
    'i'
  );
  const m = html.match(re) || html.match(re2);
  return m ? decode(m[1]) : '';
}

/** name= 메타 태그 content 추출 */
function extractMetaName(html: string, name: string): string {
  const re = new RegExp(
    `<meta[^>]+name=["']${name}["'][^>]+content=["']([^"']{1,500})["']`,
    'i'
  );
  const re2 = new RegExp(
    `<meta[^>]+content=["']([^"']{1,500})["'][^>]+name=["']${name}["']`,
    'i'
  );
  const m = html.match(re) || html.match(re2);
  return m ? decode(m[1]) : '';
}

function extractTitleTag(html: string): string {
  const m = html.match(/<title[^>]*>([^<]+)<\/title>/i);
  return m ? decode(m[1].trim()) : '';
}

/** 상대 URL → 절대 URL 변환 (실패 시 null) */
function toAbsolute(src: string, base: string): string | null {
  if (!src) return null;
  if (src.startsWith('http')) return src;
  try {
    return new URL(src, base).href;
  } catch {
    return null;
  }
}

/** Readability 실패 시 regex로 본문 추출 (폴백) */
function extractTextFallback(html: string): string {
  const cleaned = html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, ' ')
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, ' ')
    .replace(/<(nav|header|footer|aside)\b[\s\S]*?<\/\1>/gi, ' ');

  const paragraphs: string[] = [];
  for (const m of cleaned.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi)) {
    const clean = m[1].replace(/<[^>]+>/g, '').trim();
    if (clean.length > 20) paragraphs.push(decode(clean));
  }

  if (paragraphs.length > 0) return paragraphs.join('\n').slice(0, 8_000);
  return decode(cleaned.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()).slice(
    0,
    8_000
  );
}

function decode(str: string): string {
  return str
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .trim();
}
