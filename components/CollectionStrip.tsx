'use client';

import { useState } from 'react';
import Image from 'next/image';
import type { Collection, ContentCard } from '@/types';

interface Props {
  collections: Collection[];
  totalCount: number;
  userId: string;
  onCluster: () => void;
  isClustering: boolean;
}

export function CollectionStrip({
  collections,
  totalCount,
  userId,
  onCluster,
  isClustering,
}: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const top3 = collections.slice(0, 3);
  const needed = Math.max(0, 30 - totalCount);

  const toggle = (id: string) => setExpandedId((prev) => (prev === id ? null : id));

  // ── 진행률 바 (30개 미만) ────────────────────────────────────
  if (totalCount < 30 || collections.length === 0) {
    return (
      <div className="flex-shrink-0 px-4 py-2 border-t border-gray-100">
        {needed > 0 ? (
          <div className="bg-gray-50 rounded-xl px-4 py-2.5 flex items-center gap-3">
            <div className="flex-1 bg-gray-200 rounded-full h-1.5">
              <div
                className="bg-indigo-400 h-1.5 rounded-full transition-all"
                style={{ width: `${Math.min((totalCount / 30) * 100, 100)}%` }}
              />
            </div>
            <span className="text-[11px] text-gray-500 whitespace-nowrap">
              {needed}개 더 저장하면 AI가 정리해드려요
            </span>
          </div>
        ) : (
          <button
            onClick={onCluster}
            disabled={isClustering}
            className="w-full bg-indigo-50 text-indigo-600 text-sm font-medium py-2.5 rounded-xl disabled:opacity-60 active:scale-98 transition-transform"
          >
            {isClustering ? '✨ 컬렉션 만드는 중...' : '✨ AI 컬렉션 자동 정리하기'}
          </button>
        )}
      </div>
    );
  }

  const expandedCollection = top3.find((c) => c.id === expandedId);

  return (
    <div className="flex-shrink-0 border-t border-gray-100">
      {/* ── 확장된 컬렉션 패널 ─────────────────────────────────── */}
      {expandedCollection && (
        <CollectionPanel
          collection={expandedCollection}
          userId={userId}
          onClose={() => setExpandedId(null)}
        />
      )}

      {/* ── 컬렉션 pill 행 ──────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-4 py-2.5 overflow-x-auto scrollbar-none">
        {top3.map((col) => {
          const isActive = expandedId === col.id;
          return (
            <button
              key={col.id}
              onClick={() => toggle(col.id)}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 whitespace-nowrap transition-all active:scale-95 border ${
                isActive
                  ? 'bg-indigo-500 border-indigo-500 text-white shadow-md'
                  : 'bg-white border-gray-200 text-gray-700 hover:border-indigo-200'
              }`}
            >
              <span className="text-base">{col.emoji}</span>
              <span className="text-[12px] font-medium">{col.name}</span>
              {col.content_count > 0 && (
                <span
                  className={`text-[10px] ml-0.5 ${
                    isActive ? 'text-indigo-100' : 'text-gray-400'
                  }`}
                >
                  {col.content_count}
                </span>
              )}
            </button>
          );
        })}

        {/* 더보기 버튼 */}
        {collections.length > 3 && (
          <button
            onClick={onCluster}
            className="flex items-center gap-1 bg-gray-50 border border-gray-200 text-gray-500 rounded-full px-3 py-1.5 whitespace-nowrap text-[12px]"
          >
            +{collections.length - 3}
          </button>
        )}
      </div>
    </div>
  );
}

// ── 확장 패널 ────────────────────────────────────────────────────
function CollectionPanel({
  collection,
  userId,
  onClose,
}: {
  collection: Collection;
  userId: string;
  onClose: () => void;
}) {
  const contents = (collection.contents || []) as ContentCard[];

  return (
    <div className="border-b border-gray-100 bg-white animate-slideUp">
      {/* 패널 헤더 */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <div className="flex items-center gap-2">
          <span className="text-xl">{collection.emoji}</span>
          <span className="text-sm font-semibold text-gray-900">{collection.name}</span>
          <span className="text-xs text-gray-400">{collection.content_count}개</span>
        </div>
        <button
          onClick={onClose}
          className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-400 text-lg leading-none"
        >
          ×
        </button>
      </div>

      {/* 콘텐츠 가로 스크롤 */}
      {contents.length > 0 ? (
        <div className="flex gap-3 overflow-x-auto scrollbar-none px-4 pb-3">
          {contents.map((card) => (
            <MiniCard key={card.id} card={card} userId={userId} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-400 px-4 pb-3">콘텐츠가 없어요</p>
      )}
    </div>
  );
}

// ── 미니 카드 ────────────────────────────────────────────────────
function MiniCard({ card, userId }: { card: ContentCard; userId: string }) {
  const channelName =
    card.content_type === 'youtube'
      ? (card.metadata?.channel_name as string | undefined) ?? card.author
      : card.author;

  const handleClick = () => {
    fetch('/api/views', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contentId: card.id, userId }),
    }).catch(() => {});
    window.open(card.url, '_blank', 'noopener');
  };

  return (
    <div
      onClick={handleClick}
      className="flex-shrink-0 w-36 cursor-pointer active:scale-95 transition-transform"
    >
      {/* 썸네일 */}
      <div className="relative w-full h-24 rounded-xl overflow-hidden bg-gray-100">
        {card.thumbnail_url ? (
          <Image src={card.thumbnail_url} alt={card.title} fill className="object-cover" unoptimized />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-2xl">
            {card.content_type === 'youtube' ? '▶' : '📄'}
          </div>
        )}
        {card.content_type === 'youtube' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="bg-black/40 rounded-full w-7 h-7 flex items-center justify-center">
              <span className="text-white text-xs ml-0.5">▶</span>
            </div>
          </div>
        )}
      </div>

      {/* 타이틀 + 채널명 */}
      <p className="text-[11px] font-medium text-gray-800 mt-1.5 line-clamp-2 leading-tight">
        {card.title}
      </p>
      {channelName && (
        <p className="text-[10px] text-gray-400 mt-0.5 truncate">{channelName}</p>
      )}
      {/* 해시태그 */}
      <div className="flex gap-1 mt-1 flex-wrap">
        {card.hashtags.slice(0, 2).map((tag) => (
          <span key={tag} className="text-[9px] text-indigo-400 bg-indigo-50 px-1 rounded-full">
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}
