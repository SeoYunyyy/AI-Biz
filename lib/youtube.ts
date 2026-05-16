import type { CrawledContent } from '@/types';

export function extractYouTubeId(url: string): string | null {
  const patterns = [
    /youtube\.com\/watch\?v=([^&]+)/,
    /youtu\.be\/([^?]+)/,
    /youtube\.com\/embed\/([^?]+)/,
    /youtube\.com\/shorts\/([^?]+)/,
  ];
  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) return match[1];
  }
  return null;
}

export function isYouTubeUrl(url: string): boolean {
  return /youtube\.com|youtu\.be/.test(url);
}

export async function fetchYouTubeMetadata(url: string): Promise<CrawledContent> {
  const videoId = extractYouTubeId(url);
  if (!videoId) throw new Error('유효하지 않은 YouTube URL입니다.');

  const apiKey = process.env.YOUTUBE_API_KEY;
  if (!apiKey) throw new Error('YouTube API 키가 없습니다.');

  const apiUrl = `https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails&id=${videoId}&key=${apiKey}`;
  const res = await fetch(apiUrl);
  if (!res.ok) throw new Error(`YouTube API 오류: ${res.status}`);

  const data = await res.json();
  if (!data.items || data.items.length === 0) {
    throw new Error('영상을 찾을 수 없습니다.');
  }

  const snippet = data.items[0].snippet;
  const contentDetails = data.items[0].contentDetails;

  const title: string = snippet.title || '';
  const description: string = snippet.description || '';
  const channelName: string = snippet.channelTitle || '';
  const thumbnail: string =
    snippet.thumbnails?.maxres?.url ||
    snippet.thumbnails?.high?.url ||
    snippet.thumbnails?.medium?.url ||
    `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;

  const rawText = [title, description].filter(Boolean).join('\n\n');

  return {
    title,
    description: description.slice(0, 500),
    thumbnail_url: thumbnail,
    author: channelName,
    metadata: {
      channel_name: channelName,
      video_id: videoId,
      duration: contentDetails?.duration || null,
    },
    raw_text: rawText,
    content_type: 'youtube',
  };
}
