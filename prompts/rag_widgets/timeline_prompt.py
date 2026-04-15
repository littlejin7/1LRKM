"""(Placeholder) RAG 컨텍스트 → 타임라인 카드 생성 프롬프트."""

from __future__ import annotations

TIMELINE_SYSTEM_PROMPT = """(TODO)
RAG/Chroma로 검색된 과거 기사 컨텍스트를 기반으로,
6개월 타임라인 카드 데이터를 생성하는 프롬프트를 여기에 정의한다.

원칙:
- JSON-only 출력
- 컨텍스트에 없는 날짜/사건은 생성 금지
"""

