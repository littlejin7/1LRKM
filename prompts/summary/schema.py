"""출력 JSON 스키마 블록(키/타입/필수/예시)."""

from __future__ import annotations

# json_object + json.loads 환경에서 깨지지 않도록 예시는 "순수 JSON"만 포함(주석 금지)
OUTPUT_SCHEMA_BLOCK = r"""
[출력 JSON 스키마 — 키/타입 고정, 누락 금지]
{
  "summary": ["..."],
  "summary_en": ["..."],
  "artist_tags": ["..."],
  "keywords": ["...", "...", "...", "...", "..."],
  "briefing": [
    {"label": "...", "content": "..."},
    {"label": "...", "content": "..."},
    {"label": "...", "content": "..."}
  ],
  "sub_category": "...",
  "sentiment": "중립",
  "sentiment_score": null,
  "importance": 1,
  "importance_reason": "[IP0+사건0+파급0+기본1=1] 근거 한 문장",
  "tts_text": "..."
}
"""

