import type { CrawledContent } from '@/types';
import { isYouTubeUrl, fetchYouTubeMetadata } from './youtube';

export async function crawlContent(url: string): Promise<CrawledContent> {
  if (isYouTubeUrl(url)) {
    return fetchYouTubeMetadata(url);
  }
  return crawlBlog(url);
}

async function crawlBlog(url: string): Promise<CrawledContent> {
  const res = await fetch(url, {
    headers: {
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      Accept: 'text/html,application/xhtml+xml',
      'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
    },
    signal: AbortSignal.timeout(10000),
  });

  if (!res.ok) throw new Error(`페이지 로드 실패: ${res.status}`);
  const html = await res.text();

  const title = extractTitle(html);
  const description = extractDescription(html);
  const thumbnail_url = extractThumbnail(html, url);
  const author = extractAuthor(html);
  const siteName = extractSiteName(html);
  const raw_text = extractText(html);

  return {
    title,
    description,
    thumbnail_url,
    author,
    metadata: {
      site_name: siteName,
      source_url: url,
    },
    raw_text,
    content_type: 'blog',
  };
}

function extractTitle(html: string): string {
  const ogTitle = html.match(/<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']/i);
  if (ogTitle) return decode(ogTitle[1]);
  const titleTag = html.match(/<title[^>]*>([^<]+)<\/title>/i);
  if (titleTag) return decode(titleTag[1].trim());
  const h1 = html.match(/<h1[^>]*>([^<]+)<\/h1>/i);
  if (h1) return decode(h1[1].trim());
  return 'Untitled';
}

function extractDescription(html: string): string {
  const ogDesc = html.match(/<meta[^>]+property=["']og:description["'][^>]+content=["']([^"']{1,500})["']/i);
  if (ogDesc) return decode(ogDesc[1]);
  const metaDesc = html.match(/<meta[^>]+name=["']description["'][^>]+content=["']([^"']{1,500})["']/i);
  if (metaDesc) return decode(metaDesc[1]);
  return '';
}

function extractThumbnail(html: string, baseUrl: string): string | null {
  const ogImg = html.match(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/i);
  if (ogImg) {
    const src = ogImg[1];
    if (src.startsWith('http')) return src;
    try { return new URL(src, baseUrl).href; } catch { return null; }
  }
  return null;
}

function extractAuthor(html: string): string | null {
  const ogAuthor = html.match(/<meta[^>]+property=["']article:author["'][^>]+content=["']([^"']+)["']/i);
  if (ogAuthor) return decode(ogAuthor[1]);
  const metaAuthor = html.match(/<meta[^>]+name=["']author["'][^>]+content=["']([^"']+)["']/i);
  if (metaAuthor) return decode(metaAuthor[1]);
  return null;
}

function extractSiteName(html: string): string | null {
  const ogSite = html.match(/<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']+)["']/i);
  return ogSite ? decode(ogSite[1]) : null;
}

function extractText(html: string): string {
  let text = html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, ' ')
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, ' ')
    .replace(/<nav\b[^<]*(?:(?!<\/nav>)<[^<]*)*<\/nav>/gi, ' ')
    .replace(/<header\b[^<]*(?:(?!<\/header>)<[^<]*)*<\/header>/gi, ' ')
    .replace(/<footer\b[^<]*(?:(?!<\/footer>)<[^<]*)*<\/footer>/gi, ' ');

  const paragraphs: string[] = [];
  const pMatches = text.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi);
  for (const m of pMatches) {
    const clean = m[1].replace(/<[^>]+>/g, '').trim();
    if (clean.length > 20) paragraphs.push(decode(clean));
  }

  if (paragraphs.length > 0) return paragraphs.join('\n').slice(0, 8000);
  return decode(text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()).slice(0, 8000);
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
