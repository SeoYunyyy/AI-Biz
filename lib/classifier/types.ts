// types.ts

export interface ClassifyInput {
  title: string;
  description?: string;
  topics?: string[];
  moods?: string[];
  hashtags?: string[]; // (크롤러가 긁어온 원본 태그)
  embedding?: number[];
}

export interface ClassifyResult {
  category: string;             // '대분류 > 중분류 > 소분류' 형태의 텍스트
  generatedHashtags: string[];  // AI가 새로 뽑아낸 해시태그 배열
  confidence: number;           // 0~1
  model: string;                // 'llm-gpt4o-mini' | 'catboost-v1' ...
  rationale?: string;
}

export interface Classifier {
  readonly name: string;
  classify(input: ClassifyInput): Promise<ClassifyResult>;
}