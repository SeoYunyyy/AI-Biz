/**
 * URL → 플랫폼 식별자 변환
 * platform 컬럼에 저장되는 값의 유일한 출처
 */
export function detectPlatform(url: string): string {
  const u = url.toLowerCase();

  // 동영상
  if (/youtube\.com|youtu\.be/.test(u)) return 'youtube';
  if (/vimeo\.com/.test(u)) return 'vimeo';
  if (/twitch\.tv/.test(u)) return 'twitch';

  // 뉴스·언론
  if (
    /news\.naver\.com|n\.news\.naver\.com|mnews\.naver\.com/.test(u) ||
    /chosun\.com|donga\.com|joongang\.co\.kr|hani\.co\.kr|khan\.co\.kr/.test(u) ||
    /yna\.co\.kr|yonhapnews|newsis\.com|newspim\.com/.test(u) ||
    /mbc\.co\.kr|kbs\.co\.kr|sbs\.co\.kr|jtbc\.co\.kr|ytn\.co\.kr/.test(u) ||
    /hankyung\.com|mk\.co\.kr|sedaily\.com|etnews\.com|zdnet\.co\.kr/.test(u) ||
    /bbc\.com\/news|bbc\.co\.uk\/news|cnn\.com|nytimes\.com|reuters\.com/.test(u) ||
    /techcrunch\.com|theverge\.com|wired\.com/.test(u)
  ) return 'news';

  // SNS
  if (/instagram\.com/.test(u)) return 'instagram';
  if (/twitter\.com|x\.com/.test(u)) return 'twitter';
  if (/facebook\.com|fb\.com/.test(u)) return 'facebook';
  if (/linkedin\.com/.test(u)) return 'linkedin';
  if (/tiktok\.com/.test(u)) return 'tiktok';
  if (/reddit\.com/.test(u)) return 'reddit';

  // 개발·기술
  if (/github\.com/.test(u)) return 'github';
  if (/stackoverflow\.com/.test(u)) return 'stackoverflow';

  // 쇼핑
  if (
    /smartstore\.naver\.com|brand\.naver\.com/.test(u) ||
    /shopping\.naver\.com|search\.shopping\.naver\.com/.test(u)
  ) return 'shopping';

  // 블로그·아티클
  if (
    /blog\.naver\.com/.test(u) ||
    /tistory\.com/.test(u) ||
    /velog\.io/.test(u) ||
    /brunch\.co\.kr/.test(u) ||
    /medium\.com/.test(u) ||
    /substack\.com/.test(u) ||
    /notion\.site/.test(u) ||
    /wordpress\.com/.test(u) ||
    /blogspot\.com/.test(u)
  ) return 'blog';

  return 'web'; // 기타 웹페이지
}

/**
 * 검색 쿼리에서 유저가 원하는 플랫폼 감지
 * 반환값은 detectPlatform 의 반환값과 동일한 네임스페이스
 */
export function detectQueryPlatform(text: string): string | null {
  const t = text.toLowerCase();
  if (/유튜브|youtube|영상|동영상|비디오|video|채널|유튜버|shorts/.test(t)) return 'youtube';
  if (/뉴스|news|기사|언론|신문|보도|언론사/.test(t)) return 'news';
  if (/쇼핑|shopping|스마트스토어|smartstore|상품|제품|구매|가격|최저가|리뷰|후기/.test(t)) return 'shopping';
  if (/인스타|instagram|인스타그램/.test(t)) return 'instagram';
  if (/트위터|twitter|엑스|x\.com/.test(t)) return 'twitter';
  if (/블로그|blog|포스트|글|아티클|article|tistory|velog|brunch|medium/.test(t)) return 'blog';
  if (/깃허브|github/.test(t)) return 'github';
  return null; // 플랫폼 무관
}

/** platform 값 → 사람이 읽을 수 있는 한국어 레이블 */
export function platformLabel(platform: string | null): string {
  const map: Record<string, string> = {
    youtube: '유튜브 영상',
    news: '뉴스 기사',
    shopping: '쇼핑 상품',
    instagram: '인스타그램',
    twitter: '트위터',
    blog: '블로그 글',
    github: 'GitHub',
    vimeo: '비메오',
    web: '웹페이지',
  };
  return platform ? (map[platform] ?? platform) : '콘텐츠';
}
