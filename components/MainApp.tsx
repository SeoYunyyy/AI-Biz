'use client';

import { useState, useEffect, useCallback } from 'react';
import { createClient } from '@/lib/supabase/client';
import { ChatArea } from './ChatArea';
import { ChatInput } from './ChatInput';
import { CollectionStrip } from './CollectionStrip';
import { Sidebar } from './Sidebar';
import { Toast } from './Toast';
import type { ChatMessage, Collection, Content, ContentCard } from '@/types';

let msgIdCounter = 0;
const newId = () => `msg-${++msgIdCounter}-${Date.now()}`;

// ── localStorage 채팅 저장/불러오기 ─────────────────────────────
const CHAT_KEY = (uid: string) => `chat_history_${uid}`;
const MAX_STORED = 50; // 최대 저장 메시지 수

function saveMessages(uid: string, msgs: ChatMessage[]) {
  try {
    const serializable = msgs
      .filter((m) => !m.loading)
      .slice(-MAX_STORED)
      .map((m) => ({ ...m, timestamp: m.timestamp.toISOString() }));
    localStorage.setItem(CHAT_KEY(uid), JSON.stringify(serializable));
  } catch {}
}

function loadMessages(uid: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(CHAT_KEY(uid));
    if (!raw) return [];
    return JSON.parse(raw).map((m: ChatMessage & { timestamp: string }) => ({
      ...m,
      timestamp: new Date(m.timestamp),
    }));
  } catch {
    return [];
  }
}

export function MainApp() {
  const [userId, setUserId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [recentContents, setRecentContents] = useState<Content[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isClustering, setIsClustering] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' | 'info' } | null>(null);

  // ── 익명 로그인 + 채팅 복원 ─────────────────────────────────
  useEffect(() => {
    const init = async () => {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      const uid = session?.user?.id ?? (await supabase.auth.signInAnonymously().then(({ data, error }) => {
        if (error) console.error('auth error:', error);
        return data?.user?.id;
      }));
      if (!uid) return;
      setUserId(uid);
      // 저장된 채팅 기록 복원
      const saved = loadMessages(uid);
      if (saved.length > 0) setMessages(saved);
    };
    init();
  }, []);

  // ── 메시지 변경 시 localStorage에 저장 ──────────────────────
  useEffect(() => {
    if (!userId || messages.length === 0) return;
    saveMessages(userId, messages);
  }, [userId, messages]);

  // ── 카테고리 → 이모지 매핑 ──────────────────────────────────
  function categoryEmoji(cat: string): string {
    const c = cat.toLowerCase();
    if (c.includes('여행') || c.includes('travel')) return '✈️';
    if (c.includes('음식') || c.includes('요리') || c.includes('recipe') || c.includes('food')) return '🍳';
    if (c.includes('운동') || c.includes('헬스') || c.includes('workout')) return '💪';
    if (c.includes('공부') || c.includes('학습') || c.includes('study')) return '📚';
    if (c.includes('기술') || c.includes('tech') || c.includes('개발')) return '💻';
    if (c.includes('뉴스') || c.includes('news')) return '📰';
    if (c.includes('패션') || c.includes('fashion')) return '👗';
    if (c.includes('카페') || c.includes('cafe')) return '☕';
    if (c.includes('음악') || c.includes('music')) return '🎵';
    if (c.includes('영화') || c.includes('movie') || c.includes('드라마')) return '🎬';
    if (c.includes('게임') || c.includes('game')) return '🎮';
    return '📁';
  }

  // ── 데이터 로드 ──────────────────────────────────────────────
  const loadData = useCallback(async (uid: string) => {
    const [colRes, contRes] = await Promise.all([
      fetch(`/api/collections?userId=${uid}`),
      fetch(`/api/contents?userId=${uid}&limit=20`),
    ]);
    if (colRes.ok) {
      const { collections: cols } = await colRes.json();
      // API 응답 { category, total, preview } → Collection 타입으로 변환
      const mapped = (cols || []).map((c: { category: string; total: number; preview: Record<string, unknown>[] }) => ({
        id: c.category,
        name: c.category,
        emoji: categoryEmoji(c.category),
        content_count: c.total,
        is_user_renamed: false,
        last_accessed_at: null,
        created_at: '',
        updated_at: '',
        user_id: uid,
        contents: (c.preview || []).map((p) => ({
          id: p.id,
          url: p.url,
          title: p.title || '제목 없음',
          thumbnail_url: p.thumbnail_url ?? null,
          content_type: typeof p.url === 'string' && /youtube\.com|youtu\.be/.test(p.url as string) ? 'youtube' : 'blog',
          author: null,
          metadata: null,
          hashtags: Array.isArray(p.hashtags) ? p.hashtags : [],
          topics: [],
          moods: [],
          collection_id: null,
          saved_at: p.saved_at as string,
        })),
      }));
      setCollections(mapped);
    }
    if (contRes.ok) {
      const { contents, total } = await contRes.json();
      setRecentContents(contents || []);
      setTotalCount(total || 0);
    }
  }, []);

  useEffect(() => {
    if (userId) loadData(userId);
  }, [userId, loadData]);

  // ── 클러스터링 수동 트리거 ────────────────────────────────────
  const handleCluster = async () => {
    if (!userId || isClustering) return;
    setIsClustering(true);
    setToast({ msg: '✨ 컬렉션을 만들고 있어요...', type: 'info' });
    try {
      const res = await fetch('/api/cluster', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId }),
      });
      const data = await res.json();
      if (res.ok) {
        setToast({ msg: '컬렉션이 만들어졌어요! 🎉', type: 'success' });
        await loadData(userId);
      } else {
        setToast({ msg: data.error || '클러스터링 실패', type: 'error' });
      }
    } catch {
      setToast({ msg: '클러스터링 실패', type: 'error' });
    } finally {
      setIsClustering(false);
    }
  };

  // ── URL 저장 ─────────────────────────────────────────────────
  const handleAddUrl = async (url: string) => {
    if (!userId) return;
    setToast({ msg: '✓ 저장됨', type: 'success' });
    try {
      const res = await fetch('/api/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, userId }),
      });
      const data = await res.json();

      if (data.duplicate) {
        setToast({ msg: '이미 저장된 링크예요', type: 'info' });
        return;
      }
      if (!res.ok) {
        setToast({ msg: '저장 실패. 다시 시도해주세요.', type: 'error' });
        return;
      }

      const hashtags = (data.hashtags || []).slice(0, 3).join(' ');
      setToast({
        msg: `"${(data.title || 'URL').slice(0, 18)}"${
          hashtags ? ` · ${hashtags}` : ''
        } 저장됐어요`,
        type: 'success',
      });
      await loadData(userId);
    } catch {
      setToast({ msg: '저장 실패. 다시 시도해주세요.', type: 'error' });
    }
  };

  // ── 채팅 전송 ────────────────────────────────────────────────
  const handleSend = async (text: string) => {
    if (!userId || isChatLoading) return;

    setMessages((prev) => [
      ...prev,
      { id: newId(), role: 'user', content: text, timestamp: new Date() },
      { id: newId(), role: 'assistant', content: '', timestamp: new Date(), loading: true },
    ]);
    setIsChatLoading(true);

    try {
      // 직전 대화 최대 6턴(유저+어시스턴트)을 히스토리로 전달
      const recentHistory = messages
        .filter((m) => !m.loading && m.content)
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: text, userId, history: recentHistory }),
      });
      const data = await res.json();

      const assistantMsg: ChatMessage = {
        id: newId(),
        role: 'assistant',
        content: data.message || '죄송해요, 다시 시도해주세요.',
        cards: data.cards || [],
        collectionData: data.collectionData ?? undefined,
        timestamp: new Date(),
        showConfirm: (data.cards?.length || 0) > 0 && data.mode !== 'collection',
      };

      setMessages((prev) => [...prev.filter((m) => !m.loading), assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev.filter((m) => !m.loading),
        {
          id: newId(),
          role: 'assistant',
          content: '오류가 발생했어요. 다시 시도해주세요.',
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  // ── 확인 응답 ─────────────────────────────────────────────────
  const handleConfirm = (found: boolean) => {
    setMessages((prev) =>
      prev
        .map((m) => (m.showConfirm ? { ...m, showConfirm: false } : m))
        .concat({
          id: newId(),
          role: 'assistant',
          content: found
            ? '찾으셨군요! 😊 다른 것도 찾아드릴까요?'
            : '더 구체적으로 설명해주시면 다시 찾아볼게요!',
          timestamp: new Date(),
        })
    );
  };

  // ── 컬렉션 선택 (사이드바 / Strip) ───────────────────────────
  const handleCollectionSelect = (col: Collection) => {
    const cards: ContentCard[] = (col.contents || []).map((c) => ({
      id: c.id,
      url: c.url,
      content_type: c.content_type,
      title: c.title || '제목 없음',
      thumbnail_url: c.thumbnail_url,
      author: c.author,
      metadata: c.metadata,
      hashtags: c.hashtags || [],
      topics: c.topics || [],
      moods: c.moods || [],
      collection_id: c.collection_id,
      saved_at: c.saved_at,
    }));

    setMessages((prev) => [
      ...prev,
      {
        id: newId(),
        role: 'assistant',
        content: `${col.emoji} ${col.name} 컬렉션이에요! (${col.content_count}개)`,
        cards: cards.slice(0, 5),
        timestamp: new Date(),
      },
    ]);
  };

  if (!userId) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="text-3xl mb-3 animate-pulse">✨</div>
          <p className="text-sm text-gray-400">로딩 중...</p>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* 헤더 */}
      <header className="flex items-center justify-between px-4 pt-safe-or-4 pb-3 border-b border-gray-100 bg-white/90 backdrop-blur-sm flex-shrink-0">
        <button
          onClick={() => setSidebarOpen(true)}
          className="w-9 h-9 flex items-center justify-center rounded-xl hover:bg-gray-100 active:bg-gray-200 transition-colors"
          aria-label="메뉴"
        >
          <div className="space-y-1.5">
            <span className="block w-5 h-0.5 bg-gray-700 rounded-full" />
            <span className="block w-4 h-0.5 bg-gray-700 rounded-full" />
            <span className="block w-5 h-0.5 bg-gray-700 rounded-full" />
          </div>
        </button>

        <div className="flex items-center gap-1.5">
          <span className="text-base">✨</span>
          <span className="font-bold text-gray-900 text-[15px]">취향 정리집</span>
        </div>

        <div className="w-9" />
      </header>

      {/* 채팅 영역 */}
      <ChatArea
        messages={messages}
        userId={userId}
        onConfirm={handleConfirm}
        selectedCollection={null}
        onCollectionSelect={handleCollectionSelect}
      />

      {/* 컬렉션 Strip (아코디언) */}
      <CollectionStrip
        collections={collections}
        totalCount={totalCount}
        userId={userId}
        onCluster={handleCluster}
        isClustering={isClustering}
      />

      {/* 채팅 입력 */}
      <ChatInput
        onSend={handleSend}
        onAddUrl={handleAddUrl}
        isLoading={isChatLoading}
      />

      {/* 사이드바 */}
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        collections={collections}
        recentContents={recentContents}
        userId={userId}
        onCollectionSelect={handleCollectionSelect}
        onNewChat={() => {
          setMessages([]);
          if (userId) localStorage.removeItem(CHAT_KEY(userId));
        }}
      />

      {/* Toast */}
      <Toast
        message={toast?.msg || null}
        type={toast?.type}
        onDismiss={() => setToast(null)}
      />
    </>
  );
}
