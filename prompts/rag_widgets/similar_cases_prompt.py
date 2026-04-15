"""(Placeholder) RAG 컨텍스트 → 유사사례 카드 생성 프롬프트."""

from __future__ import annotations

SIMILAR_CASES_SYSTEM_PROMPT = """(TODO)
RAG/Chroma로 검색된 유사 기사 컨텍스트를 기반으로,
과거 유사 사례 카드 데이터를 생성하는 프롬프트를 여기에 정의한다.

원칙:
- JSON-only 출력
- 컨텍스트에 없는 사실/수치/연도는 생성 금지
"""

