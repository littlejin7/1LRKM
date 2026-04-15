"""(Placeholder) PDF 종합보고서 생성 프롬프트."""

from __future__ import annotations

REPORT_SYSTEM_PROMPT = """(TODO)
기간(주간/월간) 동안 수집된 processed_news/past_news를 요약해
종합보고서 문장을 생성하는 프롬프트를 여기에 정의한다.

원칙:
- 입력 컨텍스트(집계표/대표기사/키워드/아티스트 등)만 근거로 작성
- 과장/환각 금지
- 최종 출력 포맷(HTML 템플릿/Jinja)과 맞물리게 섹션별 문단을 생성
"""

