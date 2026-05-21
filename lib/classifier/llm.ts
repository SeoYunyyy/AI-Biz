// llm.ts
import OpenAI from 'openai';
import { Classifier, ClassifyInput, ClassifyResult } from './types';

// LLM 기반 계층형 분류기 및 해시태그 생성기
export class LLMClassifier implements Classifier {
  readonly name = 'llm-gpt4o-mini';
  constructor(private ai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY! })) {}

  async classify(input: ClassifyInput): Promise<ClassifyResult> {
    const res = await this.ai.chat.completions.create({
      model: 'gpt-4o-mini',
      response_format: { type: 'json_object' },
      temperature: 0.2, // 창의적인 해시태그 생성을 위해 살짝 올림
      max_tokens: 250,
      messages: [
        { 
          role: 'system', 
          content: `당신은 전문적인 지식 아카이빙 어시스턴트입니다. 주어진 텍스트를 분석하여 3단계 계층형 카테고리와 핵심 해시태그 3~5개를 추출하세요. 반드시 JSON 형식으로만 응답해야 합니다.
카테고리는 반드시 '대분류 > 중분류 > 소분류' 형태의 텍스트여야 합니다.
예시 1: "운동 > 홈트 > 복근"
예시 2: "여행 > 일본 > 카페"
예시 3: "국제정치 > 동아시아 > 베트남외교"` 
        },
        { 
          role: 'user', 
          content: `다음 콘텐츠를 분석해 주세요.
제목: ${input.title}
설명: ${(input.description || '').slice(0, 400)}
토픽: ${(input.topics || []).join(', ')}

JSON 응답 포맷:
{
  "category": "대분류 > 중분류 > 소분류",
  "hashtags": ["#키워드1", "#키워드2", "#키워드3"],
  "confidence": 0~1사이의숫자,
  "rationale": "분류 근거 한 줄"
}` 
        },
      ],
    });

    const raw = JSON.parse(res.choices[0].message.content || '{}');

    return {
      // AI가 엉뚱한 대답을 할 경우를 대비한 기본값(안전망)
      category: typeof raw.category === 'string' ? raw.category : '기타 > 미분류 > 미분류',
      generatedHashtags: Array.isArray(raw.hashtags) ? raw.hashtags : [],
      confidence: typeof raw.confidence === 'number' ? raw.confidence : 0.6,
      rationale: raw.rationale,
      model: this.name,
    };
  }
}