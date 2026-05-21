// ── DB 테이블 타입 ──────────────────────────────────────────────

export interface Profile {
  id: string;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface Content {
  id: string;
  user_id: string;
  url: string;
  content_type: 'youtube' | 'blog' | 'other';
  title: string | null;
  description: string | null;
  thumbnail_url: string | null;
  author: string | null;
  metadata: Record<string, unknown> | null; // { channel_name, duration, ... }
  topics: string[];
  moods: string[];
  intent: string[];
  energy: string | null;
  hashtags: string[];
  collection_id: string | null;
  analysis_status: 'pending' | 'processing' | 'completed' | 'failed';
  saved_at: string;
  analyzed_at: string | null;
}

export interface Collection {
  id: string;
  user_id: string;
  name: string;
  emoji: string;
  content_count: number;
  is_user_renamed: boolean;
  last_accessed_at: string | null;
  created_at: string;
  updated_at: string;
  // 조인 시 추가
  contents?: ContentCard[];
}

export interface Embedding {
  id: string;
  content_id: string;
  embedding: number[];
  created_at: string;
}

export interface ContentView {
  id: string;
  user_id: string;
  content_id: string;
  viewed_at: string;
}

// ── UI 전용 타입 ────────────────────────────────────────────────

export interface ContentCard {
  id: string;
  url: string;
  content_type: 'youtube' | 'blog' | 'other';
  title: string;
  thumbnail_url: string | null;
  author: string | null;
  metadata: Record<string, unknown> | null;
  hashtags: string[];
  topics: string[];
  moods: string[];
  collection_id: string | null;
  saved_at: string;
  last_viewed_at?: string | null;
  similarity?: number;
  label?: string;
}

export interface CollectionSummary {
  id: string;
  name: string;
  emoji: string;
  content_count: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  cards?: ContentCard[];
  collectionData?: CollectionSummary;
  timestamp: Date;
  loading?: boolean;
  showConfirm?: boolean;
}

export type ChatMode = 'memory' | 'collection' | 'general';

export interface AnalysisResult {
  topics: string[];
  moods: string[];
  intent: string[];
  energy: string;
  format: string;
  hashtags: string[];
  compressed_text: string;
}

export interface CrawledContent {
  title: string;
  description: string;
  thumbnail_url: string | null;
  author: string | null;
  metadata: Record<string, unknown>; // channel_name 등 타입별 추가 정보
  raw_text: string;
  content_type: 'youtube' | 'blog' | 'other';
}
