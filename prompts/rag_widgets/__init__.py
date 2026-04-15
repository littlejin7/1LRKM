"""
prompts/rag_widgets_v1 — (미래) 오른쪽 위젯용 프롬프트 묶음.

현재는 파일트리 확보 목적(placeholder).
RAG/Chroma/LangGraph 구축 후, past_news 기반 위젯 또는 LLM 카드 생성에 사용.
"""

from __future__ import annotations

__all__ = [
    "TIMELINE_SYSTEM_PROMPT",
    "SIMILAR_CASES_SYSTEM_PROMPT",
]

from .timeline_prompt import TIMELINE_SYSTEM_PROMPT  # noqa: E402
from .similar_cases_prompt import SIMILAR_CASES_SYSTEM_PROMPT  # noqa: E402

