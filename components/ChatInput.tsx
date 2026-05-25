'use client';

import { useState, useRef, KeyboardEvent } from 'react';

interface Props {
  onSend: (text: string) => void;
  onAddUrl: (url: string) => void;
  isLoading: boolean;
}

export function ChatInput({ onSend, onAddUrl, isLoading }: Props) {
  const [text, setText] = useState('');
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [url, setUrl] = useState('');
  const [urlLoading, setUrlLoading] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setText('');
    inputRef.current?.focus();
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleUrlSubmit = async () => {
    const trimmed = url.trim();
    if (!trimmed || urlLoading) return;

    // 간단한 URL 유효성 검사
    try {
      new URL(trimmed);
    } catch {
      alert('올바른 URL을 입력해주세요.');
      return;
    }

    setUrlLoading(true);
    await onAddUrl(trimmed);
    setUrl('');
    setShowUrlInput(false);
    setUrlLoading(false);
  };

  const handleUrlKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleUrlSubmit();
    if (e.key === 'Escape') setShowUrlInput(false);
  };

  return (
    <div className="px-4 pb-safe-or-4 pt-2">
      {/* 링크 저장 버튼 (항상 표시) */}
      {!showUrlInput && (
        <button
          onClick={() => setShowUrlInput(true)}
          className="w-full mb-2 flex items-center justify-center gap-2 py-2 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-600 text-sm font-medium active:bg-indigo-100 transition-colors"
        >
          <span>🔗</span>
          <span>링크 저장하기</span>
        </button>
      )}

      {/* URL 입력 모드 */}
      {showUrlInput && (
        <div className="mb-2 bg-white rounded-2xl border border-indigo-200 shadow-md overflow-hidden">
          <div className="flex items-center px-4 py-2 border-b border-gray-100">
            <span className="text-xs font-medium text-indigo-600">🔗 링크 저장</span>
            <button
              className="ml-auto text-gray-400 text-lg leading-none"
              onClick={() => setShowUrlInput(false)}
            >
              ×
            </button>
          </div>
          <div className="flex items-center px-3 py-2 gap-2">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={handleUrlKey}
              placeholder="유튜브 또는 블로그 URL 붙여넣기"
              className="flex-1 text-sm outline-none text-gray-800 placeholder-gray-400"
              autoFocus
            />
            <button
              onClick={handleUrlSubmit}
              disabled={urlLoading || !url.trim()}
              className="bg-indigo-500 text-white text-sm font-medium px-3 py-1.5 rounded-xl disabled:opacity-50 active:scale-95 transition-transform"
            >
              {urlLoading ? '저장 중...' : '저장'}
            </button>
          </div>
        </div>
      )}

      {/* 채팅 입력 */}
      <div className={`flex items-end gap-2 bg-white rounded-2xl border shadow-sm px-3 py-2 transition-colors ${isLoading ? 'border-indigo-200' : 'border-gray-200'}`}>
        {/* 텍스트 입력 — 로딩 중에도 타이핑 가능 */}
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            e.target.style.height = 'auto';
            e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
          }}
          onKeyDown={handleKey}
          placeholder={isLoading ? '답변 생성 중...' : '무엇을 찾아드릴까요?'}
          rows={1}
          className="flex-1 resize-none outline-none text-sm text-gray-800 placeholder-gray-400 bg-transparent leading-relaxed max-h-28"
          style={{ height: '24px' }}
        />

        {/* 전송 버튼 — 로딩 중이거나 텍스트 없으면 비활성 */}
        <button
          onClick={handleSend}
          disabled={!text.trim() || isLoading}
          className="flex-shrink-0 w-8 h-8 bg-indigo-500 rounded-full flex items-center justify-center mb-0.5 disabled:opacity-30 active:scale-90 transition-transform"
        >
          {isLoading ? (
            <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
