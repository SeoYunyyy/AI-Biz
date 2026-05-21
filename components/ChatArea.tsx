'use client';

import { useEffect, useRef } from 'react';
import { ContentCard } from './ContentCard';
import type { ChatMessage, Collection, CollectionSummary } from '@/types';

interface Props {
  messages: ChatMessage[];
  userId: string;
  onConfirm: (found: boolean) => void;
  onCollectionSelect: (col: Collection) => void;
  selectedCollection: Collection | null;
}

export function ChatArea({ messages, userId, onConfirm, selectedCollection, onCollectionSelect }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
        <div className="text-5xl mb-4">✨</div>
        <h2 className="text-lg font-bold text-gray-800 mb-2">취향 정리집</h2>
        <p className="text-sm text-gray-500 leading-relaxed">
          유튜브, 블로그 링크를 저장하면
          <br />
          AI가 자동으로 분류하고 기억해드려요
        </p>
        <div className="mt-6 space-y-2 w-full max-w-xs">
          <div className="bg-indigo-50 rounded-xl px-4 py-2.5 text-left">
            <p className="text-xs text-indigo-600">💬 이렇게 찾아보세요</p>
            <p className="text-sm text-gray-700 mt-0.5">"몇 달 전에 본 재즈 플리 뭐였더라"</p>
          </div>
          <div className="bg-indigo-50 rounded-xl px-4 py-2.5 text-left">
            <p className="text-xs text-indigo-600">💬</p>
            <p className="text-sm text-gray-700 mt-0.5">"새벽에 들을 만한 음악 추천해줘"</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          msg={msg}
          userId={userId}
          onConfirm={onConfirm}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function CollectionHeader({ col }: { col: CollectionSummary }) {
  return (
    <div className="flex items-center gap-2 bg-indigo-50 border border-indigo-100 rounded-xl px-3 py-2.5">
      <span className="text-xl">{col.emoji}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900 truncate">{col.name}</p>
        <p className="text-[11px] text-indigo-500">{col.content_count}개의 콘텐츠</p>
      </div>
      <span className="text-xs text-indigo-400">📂</span>
    </div>
  );
}

function MessageBubble({
  msg,
  userId,
  onConfirm,
}: {
  msg: ChatMessage;
  userId: string;
  onConfirm: (found: boolean) => void;
}) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="bg-indigo-500 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 max-w-[80%] shadow-sm">
          <p className="text-sm leading-relaxed">{msg.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 max-w-[90%]">
      {/* AI 아바타 + 말풍선 */}
      <div className="flex items-start gap-2">
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-[12px]">✨</span>
        </div>
        <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-2.5 shadow-sm border border-gray-100">
          {msg.loading ? (
            <div className="flex gap-1 py-1">
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          ) : (
            <p className="text-sm text-gray-800 leading-relaxed">{msg.content}</p>
          )}
        </div>
      </div>

      {/* 컬렉션 헤더 (컬렉션 모드 응답) */}
      {!msg.loading && msg.collectionData && (
        <div className="ml-9">
          <CollectionHeader col={msg.collectionData} />
        </div>
      )}

      {/* 콘텐츠 카드들 */}
      {!msg.loading && msg.cards && msg.cards.length > 0 && (
        <div className="ml-9 space-y-2">
          {msg.cards.map((card, i) => (
            <ContentCard key={card.id} card={card} userId={userId} index={i} />
          ))}

          {msg.showConfirm && (
            <div className="flex gap-2 mt-1">
              <button
                onClick={() => onConfirm(true)}
                className="flex-1 bg-indigo-500 text-white text-sm font-medium rounded-xl py-2 active:scale-95 transition-transform"
              >
                예, 맞아요
              </button>
              <button
                onClick={() => onConfirm(false)}
                className="flex-1 bg-gray-100 text-gray-700 text-sm font-medium rounded-xl py-2 active:scale-95 transition-transform"
              >
                다른 거예요
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
