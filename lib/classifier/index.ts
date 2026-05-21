import { Classifier, ClassifyInput, ClassifyResult } from './types';
import { LLMClassifier } from './llm';

export * from './types';
export { LLMClassifier } from './llm';

// 전략 스위처. 새 분류기 추가 시 case 한 줄만.
//   CLASSIFIER=llm  (기본)
//   CLASSIFIER=ml   (CatBoost/LightGBM 외부 추론 서버 — 추후)
export function getClassifier(): Classifier {
  switch (process.env.CLASSIFIER || 'llm') {
    case 'llm':
    default:
      return new LLMClassifier();
    // case 'ml': return new MLApiClassifier(process.env.ML_API_URL!);
  }
}

// 호출부 단순화 헬퍼.
export async function classifyContent(input: ClassifyInput): Promise<ClassifyResult> {
  return getClassifier().classify(input);
}
