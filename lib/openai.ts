import OpenAI from 'openai';
import type { AnalysisResult, ContentCard } from '@/types';
import { platformLabel } from '@/lib/platform';

let _client: OpenAI | null = null;
function getClient(): OpenAI {
  if (!_client) {
    _client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY! });
  }
  return _client;
}

export async function analyzeContent(
  text: string,
  title: string,
  type: string
): Promise<AnalysisResult> {
  const ai = getClient();
  const truncatedText = text.slice(0, 4000);

  const response = await ai.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: '콘텐츠 분석 전문가입니다. JSON만 반환하세요.' },
      {
        role: 'user',
        content: `다음 ${type} 콘텐츠를 분석하세요.

제목: ${title}
내용: ${truncatedText}

JSON 형식으로만 응답:
{
  "topics": ["topic1", "topic2"],
  "moods": ["mood1", "mood2"],
  "intent": ["intent1"],
  "energy": "low" | "medium" | "high",
  "format": "${type}",
  "hashtags": ["#한글태그1", "#한글태그2", "#한글태그3"]
}

- topics/moods/intent: 영어 소문자, 1~3개
- hashtags: 한국어 #태그 형식, 3~5개`,
      },
    ],
    response_format: { type: 'json_object' },
    temperature: 0.3,
    max_tokens: 300,
  });

  const raw = JSON.parse(response.choices[0].message.content || '{}');

  let compressed_text = text;
  if (text.length > 2000) {
    const sumRes = await ai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [
        { role: 'system', content: '주어진 텍스트를 핵심만 500자 이내 한국어로 요약하세요.' },
        { role: 'user', content: text.slice(0, 8000) },
      ],
      temperature: 0.3,
      max_tokens: 400,
    });
    compressed_text = sumRes.choices[0].message.content || text.slice(0, 500);
  }

  return {
    topics: Array.isArray(raw.topics) ? raw.topics.slice(0, 3) : [],
    moods: Array.isArray(raw.moods) ? raw.moods.slice(0, 3) : [],
    intent: Array.isArray(raw.intent) ? raw.intent.slice(0, 2) : [],
    energy: ['low', 'medium', 'high'].includes(raw.energy) ? raw.energy : 'medium',
    format: raw.format || type,
    hashtags: Array.isArray(raw.hashtags) ? raw.hashtags.slice(0, 5) : [],
    compressed_text,
  };
}

export async function generateCollectionName(
  topics: string[],
  moods: string[],
  sampleTitles: string[]
): Promise<{ name: string; emoji: string }> {
  const ai = getClient();
  const response = await ai.chat.completions.create({
    model: 'gpt-4o',
    messages: [
      { role: 'system', content: '감성적인 콘텐츠 컬렉션 이름을 만드는 전문가입니다. JSON만 반환하세요.' },
      {
        role: 'user',
        content: `다음 특성의 콘텐츠 컬렉션 이름과 이모지를 만드세요.
주제: ${topics.join(', ')}
분위기: ${moods.join(', ')}
콘텐츠 예시: ${sampleTitles.slice(0, 3).join(', ')}

JSON:
{
  "name": "감성적인 한국어 이름 (2~5단어)",
  "emoji": "어울리는 이모지 1개"
}`,
      },
    ],
    response_format: { type: 'json_object' },
    temperature: 0.8,
    max_tokens: 80,
  });

  const result = JSON.parse(response.choices[0].message.content || '{}');
  return {
    name: result.name || '새 컬렉션',
    emoji: result.emoji || '📁',
  };
}

// 모호한 쿼리 감지
function isVagueQuery(query: string): boolean {
  const trimmed = query.trim();
  if (trimmed.length < 6) return true;
  const vaguePatterns = /^(뭐|그거|아무|뭔가|그냥|어떤|있었는데|있잖아|저번에|있어|뭐였|혹시|있나|없나|모르겠|기억|잊어)/.test(trimmed);
  const tooShort = trimmed.split(/\s+/).length <= 2 && trimmed.length < 10;
  return vaguePatterns || tooShort;
}

export async function generateChatResponse(
  query: string,
  matchedCards: ContentCard[],
  options?: {
    platformFilter?: string | null;
    hasTypeMatch?: boolean;
    history?: { role: string; content: string }[];
    searchIntent?: string;
  }
): Promise<string> {
  if (matchedCards.length === 0) {
    return '아직 저장된 콘텐츠가 없어요. 아래 + 버튼으로 유튜브나 블로그 링크를 저장해보세요!';
  }

  const ai = getClient();
  const filter = options?.platformFilter ?? null;
  const hasTypeMatch = options?.hasTypeMatch ?? true;
  const history = options?.history ?? [];

  // ── 유사도 판단 ────────────────────────────────────────────────
  const maxSim = Math.max(...matchedCards.map((c) => c.similarity ?? 0));
  const avgSim = matchedCards.reduce((s, c) => s + (c.similarity ?? 0), 0) / matchedCards.length;
  // 유사도가 매우 낮으면 카드를 보여줘도 "못 찾았을 수 있음"을 알림
  const notFound = maxSim < 0.30;
  const lowConf  = !notFound && (avgSim < 0.42 || isVagueQuery(query));

  // ── 카드 목록 (AI에게 넘길 때 유사도 % 제거 — 혼란 방지) ─────
  const cardList = matchedCards
    .map((c, i) => {
      const tags = c.hashtags?.slice(0, 3).join(' ') || '';
      const type = c.content_type === 'youtube' ? '[유튜브]' :
                   c.content_type === 'other'   ? '[쇼핑]'  : '[글]';
      return `${i + 1}. ${type} "${c.title || '제목 없음'}" — ${tags} (${formatTimeAgo(c.saved_at)})`;
    })
    .join('\n');

  // ── 플랫폼 불일치 안내 ─────────────────────────────────────────
  const typeLabel = filter ? platformLabel(filter) : null;
  const typeMismatch = typeLabel && !hasTypeMatch
    ? `사용자가 "${typeLabel}"를 원하지만 저장된 ${typeLabel} 중 맞는 것이 없었습니다.`
    : '';

  // ── 이전 대화 메시지 (최대 4개, 팔로업일 때만 전달됨) ─────────
  const historyMessages = history.slice(-4).map((m) => ({
    role: m.role as 'user' | 'assistant',
    content: m.content,
  }));

  const systemPrompt = `당신은 사용자의 개인 콘텐츠 보관함 도우미입니다. 짧고 자연스럽게 답하세요.

상황별 답변 방식:
- notFound=true  → "저장하신 내용 중 딱 맞는 게 없어요. 혹시 제목이나 주제를 더 기억하세요?" (카드 설명 최소화)
- lowConf=true   → 카드를 소개하되 마지막에 "맞나요? 더 구체적으로 말씀해 주시면 더 잘 찾을 수 있어요." 한 문장 추가
- 정상            → 찾은 콘텐츠 1~2줄로 소개
${typeMismatch ? `\n주의: ${typeMismatch}` : ''}

규칙: 2~3문장 이내. 유사도·기술적 설명 언급 금지. 카드 번호(1. 2. 3.)는 그대로 언급 가능.`;

  const userPrompt = `[사용자 질문] ${query}
[상황] notFound=${notFound}, lowConf=${lowConf}
[검색 결과]
${cardList}`;

  const response = await ai.chat.completions.create({
    model: 'gpt-4o',
    messages: [
      { role: 'system', content: systemPrompt },
      ...historyMessages,
      { role: 'user', content: userPrompt },
    ],
    temperature: 0.5,
    max_tokens: 120,
  });

  return response.choices[0].message.content?.trim() || '이런 콘텐츠를 찾았어요!';
}

// ── 대화 맥락에서 검색 의도 추출 ──────────────────────────────
// 여러 턴의 대화를 보고 "지금 실제로 찾는 것"을 한 문단으로 요약
export async function extractSearchIntent(
  currentQuery: string,
  history: { role: string; content: string }[]
): Promise<string> {
  // 히스토리 없으면 현재 쿼리 그대로
  if (!history.length) return currentQuery;

  const ai = getClient();
  try {
    // 최근 2턴(유저+AI 각 1회)만 사용 — 오래된 주제 오염 방지
    const recentTwo = history.slice(-4);
    const conversation = recentTwo
      .map((m) => `${m.role === 'user' ? '사용자' : 'AI'}: ${m.content}`)
      .join('\n');

    const response = await ai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [
        {
          role: 'system',
          content: `직전 대화 1~2턴과 현재 질문을 보고,
사용자가 지금 찾으려는 콘텐츠를 구체적인 한 문장으로 정리하세요.
- 현재 질문이 새 주제라면 현재 질문만 반영하세요.
- 이전 대화의 추가 단서(타입·주제·시각적 특징)가 있으면 합쳐서 작성하세요.
- 검색에 바로 쓸 수 있는 한국어 문장 1개만 출력하세요.`,
        },
        {
          role: 'user',
          content: `[직전 대화]\n${conversation}\n\n[현재 질문] ${currentQuery}`,
        },
      ],
      temperature: 0.2,
      max_tokens: 100,
    });
    return response.choices[0].message.content?.trim() || currentQuery;
  } catch {
    return currentQuery;
  }
}

// ── 쿼리 확장 (Query Expansion) ────────────────────────────────
// 짧거나 시각적·모호한 쿼리를 임베딩 친화적인 풍부한 문단으로 확장
export async function expandQuery(query: string): Promise<string> {
  const ai = getClient();
  try {
    const response = await ai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [
        {
          role: 'system',
          content: `사용자의 콘텐츠 검색 쿼리를 임베딩 검색에 최적화된 풍부한 문단으로 확장하세요.
규칙:
- 원래 의도를 유지하면서 동의어·관련 개념·시각적 특징·맥락을 추가하세요.
- 썸네일/외모/시각적 특징 언급이 있으면 → 해당 직업·스타일·분야 키워드로 확장하세요.
  예) "안경 쓴 사람" → "안경, 전문가, 강사, 크리에이터, 교수, presenter, glasses"
- 한국어와 영어 키워드를 함께 포함하세요.
- 결과는 100단어 이내의 단일 단락으로만 출력하세요. (설명 없이 바로)`,
        },
        {
          role: 'user',
          content: `검색 쿼리: "${query}"`,
        },
      ],
      temperature: 0.3,
      max_tokens: 180,
    });
    return response.choices[0].message.content?.trim() || query;
  } catch {
    return query; // 실패 시 원본 쿼리 그대로 사용
  }
}

// ── 썸네일 Vision 분석 ──────────────────────────────────────────
// GPT-4o로 썸네일 이미지를 분석해 텍스트 설명 반환
export async function analyzeThumbnailVision(
  thumbnailUrl: string,
  title: string
): Promise<string> {
  const ai = getClient();
  try {
    const response = await ai.chat.completions.create({
      model: 'gpt-4o',
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'image_url',
              image_url: { url: thumbnailUrl, detail: 'low' },
            },
            {
              type: 'text',
              text: `이미지는 "${title}"의 썸네일입니다. 다음을 간결하게 설명하세요 (150자 이내):
1. 사람이 있다면: 안경 착용 여부, 헤어스타일, 성별, 옷차림, 표정
2. 배경·장소 (스튜디오, 야외, 실내 등)
3. 텍스트·자막·그래픽 요소
4. 전반적 분위기·색감`,
            },
          ],
        },
      ],
      max_tokens: 200,
    });
    return response.choices[0].message.content?.trim() || '';
  } catch {
    return ''; // Vision 분석 실패 시 빈 문자열
  }
}

export async function generateEmbedding(text: string): Promise<number[]> {
  const ai = getClient();
  const response = await ai.embeddings.create({
    model: 'text-embedding-3-small',
    input: text.slice(0, 8000),
  });
  return response.data[0].embedding;
}

export function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 1) return '오늘';
  if (diffDays < 7) return `${diffDays}일 전`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}주 전`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}개월 전`;
  return `${Math.floor(diffDays / 365)}년 전`;
}
