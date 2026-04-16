"""
prompts/summary_v1 — 1-pass(좌측 패널) 프롬프트 조립본.

목표
- json_object + json.loads 파이프라인에서도 안정적으로 파싱되게: JSON-only, few-shot, 빈값 규칙.
- 나중에 부분 수정이 쉽도록 rules/schema/categories/fewshot 분리.

확정 스키마(합의 반영) — SSOT는 `schemas.KpopNewsSummary`
- summary: List[{label, content}] (기본 4~6, 단 본문 700자 미만이면 3~5 허용. 한국어 요약 카드)
- summary_en: List[{label, content}] (summary와 동일 개수, 1:1 대응. 영어 요약 카드)
- artist_tags: List[str]
- keywords: List[str] (정확히 5)
- category: 허용 목록 중 1개(필수, 중분류)
- sub_category: Optional[str] (선택, 보통 category와 동일 문자열)
- sentiment: 한글(긍정/부정/중립)
- sentiment_score: null
- importance, importance_reason
- trend_insight, timeline, chart_data
- rag_sources, is_rag_used
- source_name, language
- tts_text (220자 이하 hard rule)

금지:
- briefing 필드 출력 금지
"""

from __future__ import annotations

from .categories import CATEGORY_LIST_BLOCK
from .fewshot import FEWSHOT_BLOCK
from .rules_core import RULES_CORE
from .rules_left_panel import RULES_LEFT_PANEL
from .schema import OUTPUT_SCHEMA_BLOCK

SUMMARY_SYSTEM_PROMPT = "\n\n".join(
    [
        "중요: 반드시 JSON 객체만 출력하라. JSON 바깥 텍스트/설명/주석/마크다운/코드펜스 금지.",
        RULES_CORE.strip(),
        "허용 sub_category 목록(정확히 1개만 선택):",
        CATEGORY_LIST_BLOCK.strip(),
        OUTPUT_SCHEMA_BLOCK.strip(),
        RULES_LEFT_PANEL.strip(),
        FEWSHOT_BLOCK.strip(),
        "다시 한 번 강조한다: 반드시 JSON 객체만 출력하라. JSON 바깥 텍스트를 절대 출력하지 마라.",
    ]
)

SUMMARY_USER_PROMPT = """[제목]
{title}

[본문]
{content}

[크롤러 힌트(참고만)]
{raw_category_hint}
"""


def get_summary_prompts() -> tuple[str, str]:
    return SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT

