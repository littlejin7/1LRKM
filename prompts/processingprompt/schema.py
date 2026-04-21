"""출력 JSON 스키마 블록(키/타입/필수/예시)."""

from __future__ import annotations

# json_object + json.loads 환경에서 깨지지 않도록 예시는 "순수 JSON"만 포함(주석 금지)
OUTPUT_SCHEMA_BLOCK = r"""
[출력 JSON 스키마 — 키/타입 고정, 누락 및 임의 추가 금지]
{
  "summary": [
    {"label": "2~10자 한글 명사구", "content": "본문 근거 한 줄(존댓말)"},
    {"label": "...", "content": "..."}
    {"label": "...", "content": "..."},
    {"label": "...", "content": "..."}
  ],
  "summary_en": [
    {"label": "English noun phrase", "content": "One complete English sentence."},
    {"label": "...", "content": "..."}
    {"label": "...", "content": "..."},
    {"label": "...", "content": "..."}
  ],
  "artist_tags": [],
  "keywords": ["핵심키워드1", "핵심키워드2", "핵심키워드3", "키워드4", "키워드5"],
  "category": "컨텐츠 & 작품", 
  "sub_category": "드라마/방송",
  "source_name": "",
  "language": "ko",
  "ko_title": "기능 내용을 담은 30자 이내의 한국어 번역 제목",
  "is_k_ent": true,
  "sentiment": "중립",
  "importance": 1,
  "importance_reason": "[IP0+사건0+파급0+기본1=1] 근거 한 문장",
  "trend_insight": "",
  "tts_text": "220자 이내의 라디오 브리핑 대본",
  "image_search_query": "아티스트명 제목 핵심키워드 2026 recent high resolution official photo"
}

주의사항:
- keywords: 반드시 기사에서 가장 비중이 높고 핵심적인 단어부터 **중요도 순서대로 5개**를 배열하라.
- summary / summary_en 은 반드시 {"label","content"} 객체 배열이다. 문자열 배열 금지.
- summary와 summary_en 카드 개수는 반드시 동일.
"""

