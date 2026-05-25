'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import type { Collection, Content } from '@/types';

interface Props {
  open: boolean;
  onClose: () => void;
  collections: Collection[];
  recentContents: Content[];
  userId: string;
  onCollectionSelect: (col: Collection) => void;
  onNewChat: () => void;
}

export function Sidebar({
  open,
  onClose,
  collections,
  recentContents,
  userId,
  onCollectionSelect,
  onNewChat,
}: Props) {
  const sidebarRef = useRef<HTMLDivElement>(null);
  const [reembedState, setReembedState] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [reembedResult, setReembedResult] = useState<string>('');

  const handleReembed = async () => {
    if (reembedState === 'running') return;
    setReembedState('running');
    setReembedResult('');
    try {
      const res = await fetch('/api/reembed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId }),
      });
      const data = await res.json();
      if (res.ok) {
        const visionCount = (data.results as { hasVision: boolean }[]).filter((r) => r.hasVision).length;
        setReembedResult(`✅ ${data.processed}개 완료 (Vision: ${visionCount}개)`);
        setReembedState('done');
      } else {
        setReembedResult(`❌ ${data.error || '실패'}`);
        setReembedState('error');
      }
    } catch {
      setReembedResult('❌ 네트워크 오류');
      setReembedState('error');
    }
  };

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (open && sidebarRef.current && !sidebarRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open, onClose]);

  return (
    <>
      <div
        className={`fixed inset-0 bg-black/30 z-30 transition-opacity duration-200 ${
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
      />

      <div
        ref={sidebarRef}
        className={`fixed top-0 left-0 h-full w-72 bg-white z-40 shadow-2xl flex flex-col transition-transform duration-250 ease-out ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-5 pt-12 pb-4 border-b border-gray-100">
          <span className="font-bold text-gray-900 text-lg">취향 정리집</span>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-500 text-xl leading-none"
          >
            ×
          </button>
        </div>

        <button
          onClick={() => { onNewChat(); onClose(); }}
          className="mx-4 mt-4 flex items-center gap-2 px-4 py-3 bg-indigo-50 text-indigo-600 font-semibold rounded-xl text-sm active:scale-98 transition-transform"
        >
          <span className="text-lg">+</span>
          새 채팅
        </button>

        <div className="flex-1 overflow-y-auto py-4 px-4 space-y-5">
          {collections.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                내 취향 모음집
              </h3>
              <div className="space-y-1">
                {collections.map((col) => (
                  <CollectionItem
                    key={col.id}
                    collection={col}
                    onSelect={() => { onCollectionSelect(col); onClose(); }}
                  />
                ))}
              </div>
            </section>
          )}

          {recentContents.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                최근 저장
              </h3>
              <div className="space-y-1">
                {recentContents.slice(0, 10).map((content) => (
                  <ContentItem key={content.id} content={content} userId={userId} />
                ))}
              </div>
            </section>
          )}

          {collections.length === 0 && recentContents.length === 0 && (
            <div className="text-center py-8 text-gray-400">
              <p className="text-sm">아직 저장된 콘텐츠가 없어요</p>
              <p className="text-xs mt-1">링크를 저장해보세요!</p>
            </div>
          )}

          {/* 썸네일 검색 개선 (기존 콘텐츠 재분석) */}
          {recentContents.length > 0 && (
            <section className="border-t border-gray-100 pt-4">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                검색 품질 개선
              </h3>
              <button
                onClick={handleReembed}
                disabled={reembedState === 'running' || reembedState === 'done'}
                className="w-full flex items-center gap-2 px-3 py-2.5 bg-indigo-50 text-indigo-600 rounded-xl text-sm font-medium disabled:opacity-50 active:scale-98 transition-transform text-left"
              >
                <span>{reembedState === 'running' ? '⏳' : reembedState === 'done' ? '✅' : '🔍'}</span>
                <div>
                  <p>{reembedState === 'running' ? '썸네일 분석 중...' : reembedState === 'done' ? '분석 완료!' : '기존 콘텐츠 썸네일 재분석'}</p>
                  {reembedState === 'idle' && (
                    <p className="text-[10px] text-indigo-400 mt-0.5">"안경 쓴 사람" 같은 시각적 검색 가능해져요</p>
                  )}
                  {reembedResult && (
                    <p className="text-[11px] mt-0.5 text-indigo-700">{reembedResult}</p>
                  )}
                </div>
              </button>
            </section>
          )}
        </div>
      </div>
    </>
  );
}

function CollectionItem({ collection, onSelect }: { collection: Collection; onSelect: () => void }) {
  return (
    <button
      onClick={onSelect}
      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-gray-50 active:bg-gray-100 transition-colors text-left"
    >
      <span className="text-xl flex-shrink-0">{collection.emoji}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 truncate">{collection.name}</p>
        <p className="text-xs text-gray-400">{collection.content_count}개</p>
      </div>
    </button>
  );
}

function ContentItem({ content, userId }: { content: Content; userId: string }) {
  const channelName =
    content.content_type === 'youtube'
      ? (content.metadata?.channel_name as string | undefined) ?? content.author
      : content.author;

  const handleClick = () => {
    fetch('/api/views', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contentId: content.id, userId }),
    }).catch(() => {});
    window.open(content.url, '_blank', 'noopener');
  };

  return (
    <button
      onClick={handleClick}
      className="w-full flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-gray-50 active:bg-gray-100 transition-colors text-left"
    >
      {content.thumbnail_url ? (
        <div className="relative w-8 h-8 rounded-lg overflow-hidden flex-shrink-0 bg-gray-100">
          <Image src={content.thumbnail_url} alt="" fill className="object-cover" unoptimized />
        </div>
      ) : (
        <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0 text-sm">
          {content.content_type === 'youtube' ? '▶' : '📄'}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-700 truncate">
          {content.title || 'Untitled'}
        </p>
        {channelName && (
          <p className="text-[10px] text-gray-400 truncate">{channelName}</p>
        )}
        <div className="flex flex-wrap gap-1 mt-0.5">
          {content.hashtags?.slice(0, 2).map((tag) => (
            <span key={tag} className="text-[10px] text-indigo-400">{tag}</span>
          ))}
        </div>
      </div>
    </button>
  );
}
