# SNS Archive — AI 기반 콘텐츠 아카이빙 백엔드

> 보내놓기만 하세요. 찾는 건 우리가, 기억하는 건 AI가.

## 빠른 시작

```bash
# 1) 가상환경
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) 패키지 설치
pip install -r requirements.txt

# 3) 환경변수
cp .env.example .env
# .env 파일에 OpenAI / Supabase 키 입력

# 4) DB 마이그레이션 (Supabase SQL Editor에서 실행)
# migrations/001_init.sql 내용을 복사하여 실행

# 5) 서버 실행
uvicorn app.main:app --reload --port 8000

# 6) 동작 확인
curl http://localhost:8000/health
```

## 디렉토리 구조

```
app/
├── main.py              FastAPI 진입점
├── config.py            환경변수
├── deps.py              인증 의존성
├── routers/             API 엔드포인트
├── services/            비즈니스 로직
│   ├── metadata/        URL별 메타데이터 추출기
│   ├── ai_classifier.py 분류·태그·요약 (OpenAI)
│   ├── embedder.py      임베딩
│   └── search_engine.py 하이브리드 검색
├── agents/              LangGraph Agent
├── db/                  SQLAlchemy 모델
├── schemas/             Pydantic 요청·응답
└── prompts/             프롬프트 템플릿
```

## API 엔드포인트

| Method | Path | 역할 |
|---|---|---|
| GET | /health | 헬스 체크 |
| POST | /api/save | URL 저장 + 자동 분류 |
| GET | /api/library | 저장 콘텐츠 목록 |
| POST | /api/search | 의미 기반 검색 |
| POST | /api/chat | RAG 챗봇 |
| PATCH | /api/contents/{id} | 카테고리·태그 수정 |
| GET | /api/report/monthly | 월간 취향 리포트 |

## 팀

- A · B: 프론트 (Next.js, 나중에 합류)
- C: 백엔드 통합 / FastAPI / Supabase
- D: AI · RAG · 임베딩
- E: PM · QA · 데이터
