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
    return '아직 저장된 콘텐츠가 없어요. 아래 링크 저장하기 버튼으로 유튜브나 블로그 링크를 저장해보세요!';
  }

  const ai = getClient();
  const vague = isVagueQuery(query);
  const filter = options?.platformFilter ?? null;
  const hasTypeMatch = options?.hasTypeMatch ?? true;
  const history = options?.history ?? [];
  const searchIntent = options?.searchIntent;

  const typeLabel = filter ? platformLabel(filter) : null;

  const cardList = matchedCards
    .map((c, i) => {
      const sim = c.similarity != null ? ` (유사도 ${Math.round(c.similarity * 100)}%)` : '';
      const tags = c.hashtags?.slice(0, 3).join(' ') || '';
      const type = c.content_type === 'youtube' ? '📹유튜브' : '📄';
      return `[${i + 1}] ${type} "${c.title || '제목 없음'}"${sim} — ${tags} (${formatTimeAgo(c.saved_at)})`;
    })
    .join('\n');

  const avgSimilarity = matchedCards.reduce((s, c) => s + (c.similarity ?? 0), 0) / matchedCards.length;
  const lowConfidence = avgSimilarity < 0.45 || vague;

  const typeContext = typeLabel && !hasTypeMatch
    ? `\n주의: 사용자가 ${typeLabel}을 찾고 있지만 저장된 ${typeLabel} 중 적합한 것을 못 찾았습니다. 이 점을 언급하고 다른 특징을 물어보세요.`
    : typeLabel
    ? `\n참고: 사용자가 ${typeLabel}을 찾고 있으며 검색 결과도 해당 플랫폼입니다.`
    : '';

  const intentContext = searchIntent
    ? `\n[대화를 종합한 실제 검색 의도]: "${searchIntent}"`
    : '';

  // 이전 대화 메시지를 GPT messages 배열에 포함 (최대 6개)
  const historyMessages = history.slice(-6).map((m) => ({
    role: m.role as 'user' | 'assistant',
    content: m.content,
  }));

  const response = await ai.chat.completions.create({
    model: 'gpt-4o',
    messages: [
      {
        role: 'system',
        content: `당신은 사용자의 개인 콘텐츠 라이브러리 도우미입니다. 친근하고 따뜻한 말투로 대화하세요.

규칙:
1. 이전 대화 맥락을 기억하고 자연스럽게 이어가세요. "아까 말씀하신 ~"처럼 연결하세요.
2. 질문이 모호하거나 유사도가 낮으면(lowConfidence=true), 카드를 보여주되 **유도 질문 1개**를 마지막에 추가하세요.
   유도 질문 예시: "제목에 포함된 단어 기억나시나요?", "언제쯤 저장하셨어요?", "어떤 주제였나요?"
3. 유도 질문에 사용자가 구체적으로 답하면, 그 정보까지 합쳐서 검색했음을 알려주세요.
4. 콘텐츠 타입(유튜브/블로그)이 맞지 않으면 솔직하게 말하고 더 좁혀달라고 하세요.
5. 2~3문장 이내로 답하세요.${typeContext}${intentContext}`,
      },
      ...historyMessages,
      {
        role: 'user',
        content: `사용자 질문: "${query}"
lowConfidence: ${lowConfidence}
typeMatched: ${hasTypeMatch}

검색된 콘텐츠:
${cardList}

위 규칙에 따라 답변하세요.`,
      },
    ],
    temperature: 0.7,
    max_tokens: 150,
  });

  return response.choices[0].message.content || '이런 콘텐츠를 찾고 계신 것 같아요!';
}

// ── 대화 맥락에서 검색 의도 추출 ──────────────────────────────
// 여러 턴의 대화를 보고 "지금 실제로 찾는 것"을 한 문단으로 요약
export async function extractSearchIntent(
  currentQuery: string,
  history: { role: string; content: string }[]
): Promise<string> {
  if (!history.length) return currentQuery;

  const ai = getClient();
  try {
    const conversation = history
      .map((m) => `${m.role === 'user' ? '사용자' : 'AI'}: ${m.content}`)
      .join('\n');

    const response = await ai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [
        {
          role: 'system',
          content: `아래 대화 내용을 분석해서, 사용자가 지금 찾고 싶어 하는 콘텐츠를
하나의 구체적인 검색 문장으로 정리하세요.
- 이전 대화의 단서들을 모두 합쳐서 작성하세요.
- 콘텐츠 타입(유튜브/블로그), 주제, 시각적 특징, 시기 등 언급된 정보를 모두 포함하세요.
- 결과는 검색에 바로 쓸 수 있는 한국어 문장 1개만 출력하세요.`,
        },
        {
          role: 'user',
          content: `[대화 기록]\n${conversation}\n\n[현재 질문]\n사용자: ${currentQuery}\n\n위 내용을 바탕으로 사용자가 찾는 콘텐츠를 한 문장으로 정리하세요.`,
        },
      ],
      temperature: 0.2,
      max_tokens: 150,
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
