# Keepit API 문서

> **Base URL** `http://localhost:8000`  
> **인증** 모든 엔드포인트는 `Authorization: Bearer <JWT>` 헤더 필요

---

## 목차

1. [콘텐츠](#1-콘텐츠)
2. [검색](#2-검색)
3. [채팅](#3-채팅)
4. [마감기한](#4-마감기한)
5. [컬렉션(폴더)](#5-컬렉션폴더)
6. [이번 업데이트 변경 내역](#6-이번-업데이트-변경-내역)

---

## 1. 콘텐츠

### `POST /ingest` — URL 저장

링크를 저장하고 AI 분석(분류·요약·임베딩)을 실행합니다.

**Request Body**
```json
{
  "url": "https://www.youtube.com/watch?v=example",
  "user_id": "uuid",
  "instruction": "파이썬 폴더에 넣어줘",
  "collection_id": null
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `url` | string | ✅ | 저장할 링크 |
| `user_id` | string | ✅ | 사용자 ID |
| `instruction` | string | | 폴더 지정 등 사용자 지시사항 |
| `collection_id` | string | | 직접 폴더 ID 지정 (없으면 AI가 자동 배정) |

**Response**
```json
{
  "id": "content-uuid",
  "title": "파이썬 입문 강의",
  "thumbnail": "https://...",
  "platform": "youtube",
  "category": "IT/기술",
  "sub_category": "파이썬",
  "one_line_summary": "파이썬 기초부터 배우는 입문 강의",
  "tags": ["파이썬", "프로그래밍", "입문"],
  "has_deadline": false,
  "deadline_date": null,
  "deadline_note": null,
  "deadline_items": [],
  "collection_id": "folder-uuid",
  "analysis_status": "completed",
  "similar_contents": [
    {
      "id": "uuid",
      "title": "관련 콘텐츠",
      "url": "https://...",
      "similarity": 0.82,
      "one_line_summary": "..."
    }
  ]
}
```

> 이미 저장된 URL일 경우 `{ "duplicate": true, "content": { ... } }` 반환

---

### `GET /contents` — 콘텐츠 목록 조회 🆕

필터와 페이지네이션을 적용해 저장된 콘텐츠 목록을 조회합니다.

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `user_id` | string | 필수 | 사용자 ID |
| `category` | string | | 대분류 필터 (예: `IT/기술`, `여행`) |
| `platform` | string | | 플랫폼 필터 (예: `youtube`, `blog`) |
| `collection_id` | string | | 특정 폴더 필터 |
| `date_from` | string | | 저장일 시작 (YYYY-MM-DD) |
| `date_to` | string | | 저장일 종료 (YYYY-MM-DD) |
| `limit` | int | `20` | 페이지 크기 |
| `offset` | int | `0` | 건너뛸 항목 수 |

**Example**
```
GET /contents?user_id=uuid&category=IT/기술&limit=20&offset=0
GET /contents?user_id=uuid&date_from=2026-01-01&date_to=2026-05-28
```

**Response**
```json
{
  "contents": [
    {
      "id": "uuid",
      "title": "파이썬 입문 강의",
      "url": "https://...",
      "thumbnail_url": "https://...",
      "content_type": "youtube",
      "category": "IT/기술",
      "sub_category": "파이썬",
      "one_line_summary": "...",
      "hashtags": ["#파이썬", "#프로그래밍"],
      "analysis_status": "completed",
      "saved_at": "2026-05-28T00:00:00+00:00",
      "has_deadline": false,
      "deadline_date": null,
      "collection_id": "folder-uuid"
    }
  ],
  "limit": 20,
  "offset": 0
}
```

---

### `GET /contents/{content_id}` — 콘텐츠 단건 조회

**Response**
```json
{
  "id": "uuid",
  "title": "...",
  "thumbnail_url": "...",
  "category": "IT/기술",
  "one_line_summary": "...",
  "has_deadline": false,
  "deadline_date": null,
  "deadline_note": null,
  "sub_category": "파이썬",
  "analysis_status": "completed"
}
```

> 본인 소유 콘텐츠가 아니면 `404` 반환

---

### `PATCH /contents/{content_id}` — 폴더 재배정 🆕

콘텐츠를 다른 폴더로 이동합니다.

**Request Body**
```json
{
  "user_id": "uuid",
  "collection_id": "new-folder-uuid"
}
```

**Response**
```json
{ "success": true }
```

---

### `DELETE /contents/{content_id}` — 콘텐츠 삭제 🆕

**Response**
```json
{ "success": true }
```

> JWT에서 user_id를 추출해 소유권을 검증합니다. 별도 body 불필요.

---

## 2. 검색

### `POST /search` — 벡터 유사도 검색

저장된 콘텐츠를 의미 기반으로 검색합니다.

**Request Body**
```json
{
  "query": "파이썬 강의",
  "user_id": "uuid",
  "limit": 5
}
```

**Response**
```json
{
  "results": [
    {
      "id": "uuid",
      "title": "파이썬 입문 강의",
      "url": "https://...",
      "thumbnail_url": "https://...",
      "hashtags": ["#파이썬"],
      "one_line_summary": "...",
      "similarity": 0.87
    }
  ],
  "found": true,
  "message": null,
  "follow_up_questions": []
}
```

> 결과가 없으면 `"found": false` + `"follow_up_questions"` 배열 반환

---

## 3. 채팅

### `POST /chat` — AI 채팅 검색

대화 맥락을 기억하며 콘텐츠를 찾아주는 채팅 인터페이스입니다.

**Request Body**
```json
{
  "query": "파이썬 강의 찾아줘",
  "user_id": "uuid",
  "history": [
    { "role": "user", "content": "파이썬 강의 찾아줘" },
    { "role": "assistant", "content": "이 중에 찾으시는 콘텐츠가 있나요?" }
  ],
  "search_attempt": 1,
  "shown_ids": ["id1", "id2", "id3"],
  "action": null
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `query` | string | 현재 메시지 |
| `user_id` | string | 사용자 ID |
| `history` | array | 이전 대화 내역 (클라이언트가 유지) |
| `search_attempt` | int | 현재 검색 시도 횟수 (클라이언트가 유지) |
| `shown_ids` | array | 이미 보여준 콘텐츠 ID 목록 (클라이언트가 유지) |
| `action` | string\|null | 버튼 클릭 시 `"found"` 또는 `"refine"` 직접 전달 |

**Response**
```json
{
  "answer": "찾으시는 콘텐츠 후보를 3개 찾았어요. ...\n\n이 중에 찾으시는 콘텐츠가 있나요?",
  "results": [
    {
      "rank": 1,
      "id": "uuid",
      "title": "파이썬 입문 강의",
      "thumbnail_url": "https://...",
      "hashtags": ["#파이썬"],
      "one_line_summary": "...",
      "url": "https://...",
      "platform": "youtube",
      "similarity": 0.87
    }
  ],
  "intent": "search",
  "search_attempt": 1,
  "shown_ids": ["id1", "id2", "id3"],
  "session_ended": false,
  "show_confirmation": true,
  "confirmation_options": [
    { "label": "있어요 ✅", "action": "found" },
    { "label": "없어요 ❌", "action": "refine" }
  ]
}
```

**채팅 흐름**

```
[1] 첫 질문 (search)
    → 후보 3개 제시 + 확인 버튼 표시
    → search_attempt: 1, shown_ids: [id1, id2, id3]

[2-A] "있어요" 버튼 클릭 (action: "found")
    → session_ended: true, 대화 종료

[2-B] "없어요" 버튼 클릭 (action: "refine")
    → 이전 결과 제외하고 재검색
    → search_attempt: 2, shown_ids: [id1~id6]

[3] 최대 3회 시도 후에도 못 찾으면
    → 포기 메시지 + session_ended: true
```

**인식되는 의도(intent)**

| intent | 설명 | 예시 |
|--------|------|------|
| `search` | 새 검색 | "파이썬 강의 찾아줘" |
| `refine` | 조건 추가·재검색 | "그중 유튜브 영상", "없어" |
| `found` | 정답 확인 | "맞아", "있어", "이거야" |
| `deadline` | 마감기한 조회 | "마감 언제야" |
| `folder` | 폴더 관리 | "스터디 폴더 만들어줘" |
| `cleanup` | 만료 콘텐츠 정리 | "오래된 거 지워줘" |

---

## 4. 마감기한

### `GET /deadlines/{user_id}` — 마감기한 콘텐츠 조회

마감기한이 있는 콘텐츠를 마감일 오름차순으로 반환합니다.

**Response**
```json
{
  "deadlines": [
    {
      "id": "uuid",
      "title": "국민대 장학금 신청",
      "url": "https://...",
      "deadline_date": "2026-06-30",
      "deadline_note": "신청 마감 6/30",
      "thumbnail_url": "https://..."
    }
  ]
}
```

---

## 5. 컬렉션(폴더)

### `GET /collections/{user_id}` — 폴더 목록 조회

**Response**
```json
{
  "collections": [
    {
      "id": "uuid",
      "name": "IT/기술",
      "emoji": null,
      "content_count": 5,
      "created_at": "2026-05-28T00:00:00+00:00"
    }
  ]
}
```

---

### `POST /collections` — 폴더 생성

**Request Body**
```json
{
  "user_id": "uuid",
  "name": "스터디"
}
```

**Response**
```json
{
  "collection_id": "uuid",
  "name": "스터디"
}
```

---

### `GET /collections/{collection_id}/contents` — 폴더별 콘텐츠 조회 🆕

특정 폴더에 속한 콘텐츠 목록을 페이지네이션으로 조회합니다.

**Query Parameters**

| 파라미터 | 타입 | 기본값 |
|----------|------|--------|
| `user_id` | string | 필수 |
| `limit` | int | `20` |
| `offset` | int | `0` |

**Response**
```json
{
  "contents": [ { "id": "...", "title": "..." } ],
  "collection_id": "uuid",
  "limit": 20,
  "offset": 0
}
```

---

### `PATCH /collections/{collection_id}` — 폴더 이름 변경 🆕

**Request Body**
```json
{
  "user_id": "uuid",
  "name": "새 폴더명"
}
```

**Response**
```json
{
  "success": true,
  "collection_id": "uuid",
  "name": "새 폴더명"
}
```

---

### `DELETE /collections/{collection_id}` — 폴더 삭제 🆕

폴더를 삭제합니다. 해당 폴더 소속 콘텐츠의 `collection_id`는 `null`로 해제되며, 콘텐츠 자체는 삭제되지 않습니다.

**Response**
```json
{ "success": true }
```

---

## 6. 이번 업데이트 변경 내역

### 🆕 신규 추가 기능

| 기능 | 엔드포인트 | 설명 |
|------|------------|------|
| 콘텐츠 목록 조회 | `GET /contents` | 6가지 필터 + 페이지네이션 |
| 콘텐츠 삭제 | `DELETE /contents/{id}` | JWT 기반 소유권 검증 |
| 폴더 재배정 | `PATCH /contents/{id}` | 콘텐츠를 다른 폴더로 이동 |
| 폴더별 콘텐츠 조회 | `GET /collections/{id}/contents` | 페이지네이션 지원 |
| 폴더 이름 변경 | `PATCH /collections/{id}` | `is_user_renamed` 플래그 저장 |
| 폴더 삭제 | `DELETE /collections/{id}` | 콘텐츠 null 해제 후 폴더 삭제 |

### 🔧 수정·개선된 기능

| 기능 | 변경 내용 |
|------|-----------|
| **마감기한 오탐 방지** | 방송일·게시일 등을 마감기한으로 잘못 인식하던 문제 수정. 1년 이상 과거 날짜 자동 제거, 파생 필드(`has_deadline`, `deadline_date`, `deadline_note`) 재계산 |
| **채팅 중복 결과 제거** | 이미 보여준 콘텐츠(`shown_ids`)를 다음 검색에서 자동 제외 |
| **채팅 대화 흐름 구조화** | 검색 → 확인 버튼 → 재검색 최대 3회 → 종료 흐름 구현. `search_attempt`, `shown_ids`, `session_ended` 상태를 클라이언트가 유지 |
| **버튼 기반 확인** | "있어요/없어요" 버튼 클릭 시 `action` 필드로 직접 전달 → LLM 의도 분류 오류 제거 |
| **한/영 다국어 검색** | "뮤직뱅크"로 검색해도 "Music Bank"로 저장된 콘텐츠 검색 가능 (고유명사 자동 병기) |
| **카테고리 기반 폴더 자동 배정** | 사용자가 폴더를 지정하지 않으면 AI 분류 카테고리로 자동 배정 |
| **콘텐츠 단건 조회 보안** | `GET /contents/{id}`에서 타인 소유 콘텐츠 조회 차단 (404 반환) |

### 폴더 자동 배정 우선순위

```
1순위: 사용자가 instruction에서 직접 언급한 폴더명
       예) "파이썬 폴더에 넣어줘" → "파이썬" 폴더
2순위: AI가 분류한 대분류 카테고리
       예) category = "IT/기술" → "IT/기술" 폴더
```

---

*최종 수정일: 2026-05-28*
