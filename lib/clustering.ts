import { createClient } from '@supabase/supabase-js';
import { generateCollectionName, generateEmbedding } from './openai';

const MIN_CLUSTER_SIZE = 3;
const SIMILARITY_THRESHOLD = 0.40;

function cosine(a: number[], b: number[]): number {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb);
  return denom === 0 ? 0 : dot / denom;
}

function parseVector(v: unknown): number[] {
  if (Array.isArray(v)) return v as number[];
  if (typeof v === 'string') {
    return v.replace(/[\[\]]/g, '').split(',').map(Number);
  }
  return [];
}

interface EmbeddingRow {
  content_id: string;
  embedding: number[];
  title: string | null;
  topics: string[];
  moods: string[];
}

function dbscan(rows: EmbeddingRow[]): Map<string, number> {
  const n = rows.length;
  const labels = new Map<string, number>(rows.map((r) => [r.content_id, -1]));
  const visited = new Set<string>();
  let clusterIdx = 0;

  const getNeighbors = (idx: number): number[] =>
    rows
      .map((_, j) => j)
      .filter(
        (j) =>
          j !== idx &&
          cosine(rows[idx].embedding, rows[j].embedding) >= SIMILARITY_THRESHOLD
      );

  for (let i = 0; i < n; i++) {
    const row = rows[i];
    if (visited.has(row.content_id)) continue;
    visited.add(row.content_id);

    const nbrs = getNeighbors(i);
    if (nbrs.length < MIN_CLUSTER_SIZE - 1) continue;

    labels.set(row.content_id, clusterIdx);
    const queue = [...nbrs];

    while (queue.length > 0) {
      const j = queue.pop()!;
      const jRow = rows[j];
      if (!visited.has(jRow.content_id)) {
        visited.add(jRow.content_id);
        const jNbrs = getNeighbors(j);
        if (jNbrs.length >= MIN_CLUSTER_SIZE - 1) queue.push(...jNbrs);
      }
      if (labels.get(jRow.content_id) === -1) {
        labels.set(jRow.content_id, clusterIdx);
      }
    }

    clusterIdx++;
  }

  return labels;
}

export async function runClustering(userId: string): Promise<void> {
  const db = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  // Step 1: 이 유저의 분석 완료 콘텐츠 ID + 메타 조회
  const { data: userContents, error: contentsError } = await db
    .from('contents')
    .select('id, title, topics, moods')
    .eq('user_id', userId)
    .eq('analysis_status', 'completed');

  if (contentsError || !userContents || userContents.length < MIN_CLUSTER_SIZE) return;

  const contentIds = userContents.map((c: { id: string }) => c.id);

  // Step 2: 해당 ID들의 임베딩 조회
  const { data: embedRows, error: embedError } = await db
    .from('embeddings')
    .select('content_id, embedding')
    .in('content_id', contentIds);

  if (embedError || !embedRows?.length) return;

  // 메타 맵 구성
  interface ContentMeta { title: string | null; topics: string[]; moods: string[] }
  const metaMap = new Map<string, ContentMeta>(
    (userContents as (ContentMeta & { id: string })[]).map((c) => [
      c.id,
      { title: c.title, topics: c.topics || [], moods: c.moods || [] },
    ])
  );

  const parsed: EmbeddingRow[] = (embedRows as { content_id: string; embedding: unknown }[])
    .map((r) => {
      const meta = metaMap.get(r.content_id);
      if (!meta) return null;
      const embedding = parseVector(r.embedding);
      if (embedding.length === 0) return null;
      return {
        content_id: r.content_id,
        embedding,
        title: meta.title,
        topics: meta.topics,
        moods: meta.moods,
      };
    })
    .filter((r): r is EmbeddingRow => r !== null);

  if (parsed.length < MIN_CLUSTER_SIZE) return;

  const labels = dbscan(parsed);

  // 클러스터별 그룹핑
  const clusters = new Map<number, EmbeddingRow[]>();
  for (const row of parsed) {
    const label = labels.get(row.content_id) ?? -1;
    if (label === -1) continue;
    if (!clusters.has(label)) clusters.set(label, []);
    clusters.get(label)!.push(row);
  }

  // 기존 자동 생성 컬렉션 삭제 — CASCADE 위험 방지: update 확인 후 delete
  const { data: oldCols } = await db
    .from('collections')
    .select('id')
    .eq('user_id', userId)
    .eq('is_user_renamed', false);

  if (oldCols && oldCols.length > 0) {
    const oldIds = oldCols.map((c: { id: string }) => c.id);

    // 1) 콘텐츠 연결 해제 — 반드시 error 확인
    const { error: unlinkError } = await db
      .from('contents')
      .update({ collection_id: null })
      .in('collection_id', oldIds)
      .eq('user_id', userId);

    if (unlinkError) {
      console.error('collection unlink failed, aborting delete to prevent data loss:', unlinkError);
      return;
    }

    // 2) 연결 해제 확인 후 컬렉션 삭제
    await db.from('collections').delete().eq('user_id', userId).in('id', oldIds);
  }

  // 새 컬렉션 생성
  for (const [, members] of clusters) {
    if (members.length < MIN_CLUSTER_SIZE) continue;

    const allTopics = members.flatMap((m) => m.topics);
    const allMoods = members.flatMap((m) => m.moods);
    const topTopics = mostFrequent(allTopics, 3);
    const topMoods = mostFrequent(allMoods, 3);
    const sampleTitles = members
      .slice(0, 3)
      .map((m) => m.title || '')
      .filter(Boolean);

    const { name, emoji } = await generateCollectionName(topTopics, topMoods, sampleTitles);

    // 클러스터 중심(centroid) 임베딩 계산
    const centroidText =
      [...topTopics, ...topMoods].join(' ') || sampleTitles[0] || 'collection';
    const centroidEmbedding = await generateEmbedding(centroidText);

    // 컬렉션 생성
    const { data: col } = await db
      .from('collections')
      .insert({
        user_id: userId,
        name,
        emoji,
        is_user_renamed: false,
        content_count: members.length,
        cluster_centroid: JSON.stringify(centroidEmbedding),
      })
      .select('id')
      .single();

    if (!col) continue;

    // contents.collection_id 업데이트 (1:N)
    await db
      .from('contents')
      .update({ collection_id: col.id })
      .in(
        'id',
        members.map((m) => m.content_id)
      );
  }
}

function mostFrequent(arr: string[], topN: number): string[] {
  const freq = new Map<string, number>();
  for (const item of arr) freq.set(item, (freq.get(item) || 0) + 1);
  return [...freq.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map(([k]) => k);
}
