# 메타데이터 추출 파이프라인

링크 URL을 받아서 제목, 날짜, 요약, 썸네일 등을 추출하고 AI로 분류하는 파이프라인입니다.

## 파일 설명

| 파일 | 역할 |
|---|---|
| `dispatcher.py` | URL 보고 어떤 추출기 쓸지 결정 (진입점) |
| `web.py` | 일반 웹사이트/뉴스 메타데이터 추출 |
| `youtube.py` | 유튜브 영상 메타데이터 추출 (YouTube Data API) |
| `news.py` | 네이버 뉴스 전용 추출 (본문 크롤링) |
| `naver_blog.py` | 네이버 블로그 메타데이터 추출 |
| `map.py` | 카카오맵/네이버지도 장소 정보 추출 |
| `shopping.py` | 쇼핑몰 상품명/가격 추출 |
| `ai_classifier.py` | 추출된 메타데이터를 OpenAI로 요약/태그/분류 |

## 출력 형식

```python
{
  "title": "제목",
  "date": "2024-03-01",
  "summary": "내용 요약",
  "category": "뉴스/블로그/영상/쇼핑/장소",
  "tags": ["태그1", "태그2"],
  "thumbnail": "이미지 URL",
  "platform": "youtube/naver_blog/naver_news/web/shopping",
  "original_url": "원본 URL"
}
```

## 필요한 환경변수

```
YOUTUBE_API_KEY=유튜브 Data API 키
OPENAI_API_KEY=OpenAI API 키
```

## 1차 결과

잘됨
•	youtube.py - 제목, 날짜, 태그, 썸네일 다 완벽
•	news.py - 네이버 뉴스 제목, 날짜, 본문 다 됨
•	dispatcher.py - URL 분류 잘 됨
애매
•	web.py - 제목/썸네일은 되는데 날짜/본문은 사이트마다 달라서 빈값 나올 수 있음
•	naver_blog.py - 제목/썸네일은 되는데 날짜/본문이 잘 안 나옴. 공개된 블로그만 가능
안됨
•	map.py - JavaScript 렌더링이라 장소명 못 가져옴, API 신청 필요
•	ai_classifier.py - OpenAI 결제 후 테스트 필요
•	shopping.py – 현재 og태그 긁는 식으로만 짜둠 web이랑 걍 비슷, 네이버/쿠팡 봇 차단 심함. API 다 가져와야할 듯
