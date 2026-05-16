'use client';

import Image from 'next/image';
import type { ContentCard as ContentCardType } from '@/types';

interface Props {
  card: ContentCardType;
  userId: string;
  index: number;
}

export function ContentCard({ card, userId, index }: Props) {
  const channelName =
    card.content_type === 'youtube'
      ? (card.metadata?.channel_name as string | undefined) ?? card.author
      : card.author;

  const handleClick = async () => {
    fetch('/api/views', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contentId: card.id, userId }),
    }).catch(() => {});
    window.open(card.url, '_blank', 'noopener');
  };

  const timeAgo = formatTimeAgo(card.saved_at);
  const isYoutube = card.content_type === 'youtube';

  return (
    <div
      className="card-enter bg-white rounded-2xl overflow-hidden shadow-sm border border-gray-100 cursor-pointer active:scale-[0.98] transition-transform"
      style={{ animationDelay: `${index * 80}ms` }}
      onClick={handleClick}
    >
      {card.label && (
        <div className="px-3 pt-2.5 pb-0">
          <span className="text-[11px] font-medium text-indigo-500 bg-indigo-50 px-2 py-0.5 rounded-full">
            {card.label}
          </span>
        </div>
      )}

      <div className="flex gap-3 p-3">
        {/* 썸네일 */}
        <div className="relative flex-shrink-0 w-20 h-16 rounded-xl overflow-hidden bg-gray-100">
          {card.thumbnail_url ? (
            <Image
              src={card.thumbnail_url}
              alt={card.title}
              fill
              className="object-cover"
              unoptimized
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-2xl">
              {isYoutube ? '▶' : '📄'}
            </div>
          )}
          {isYoutube && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="bg-black/50 rounded-full w-6 h-6 flex items-center justify-center">
                <span className="text-white text-[10px] ml-0.5">▶</span>
              </div>
            </div>
          )}
        </div>

        {/* 정보 */}
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-semibold text-gray-900 leading-tight line-clamp-2">
            {card.title}
          </p>
          {channelName && (
            <p className="text-[11px] text-gray-400 mt-0.5 truncate">{channelName}</p>
          )}
          <div className="flex flex-wrap gap-1 mt-1.5">
            {card.hashtags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="text-[10px] text-indigo-500 bg-indigo-50 px-1.5 py-0.5 rounded-full"
              >
                {tag}
              </span>
            ))}
            <span className="text-[10px] text-gray-400 ml-auto">{timeAgo}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatTimeAgo(dateStr: string): string {
  const diffDays = Math.floor(
    (Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24)
  );
  if (diffDays < 1) return '오늘';
  if (diffDays < 7) return `${diffDays}일 전`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}주 전`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}개월 전`;
  return `${Math.floor(diffDays / 365)}년 전`;
}
