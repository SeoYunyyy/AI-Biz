import OpenAI from 'openai';
import type { AnalysisResult, ContentCard } from '@/types';

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

export async function generateChatResponse(
  query: string,
  matchedCards: ContentCard[]
): Promise<string> {
  if (matchedCards.length === 0) {
    return '아직 저장된 콘텐츠가 없어요. 아래 + 버튼으로 유튜브나 블로그 링크를 저장해보세요!';
  }

  const ai = getClient();
  const cardList = matchedCards
    .map((c, i) => `[${i + 1}] "${c.title || '제목 없음'}" (${formatTimeAgo(c.saved_at)})`)
    .join('\n');

  const response = await ai.chat.completions.create({
    model: 'gpt-4o',
    messages: [
      {
        role: 'system',
        content: `사용자의 콘텐츠 라이브러리 도우미입니다. 찾던 콘텐츠를 자연스럽고 따뜻하게 안내하세요.
"이거 아닐까요?" 같은 편안한 말투로 1~2문장만 답하세요.`,
      },
      {
        role: 'user',
        content: `사용자 질문: "${query}"\n\n관련 콘텐츠:\n${cardList}\n\n짧고 자연스럽게 안내해주세요.`,
      },
    ],
    temperature: 0.7,
    max_tokens: 80,
  });

  return response.choices[0].message.content || '이런 콘텐츠를 찾고 계신 것 같아요!';
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
