"""
prompts/summary_refine — 1-1차 재가공

입력: 1차에서 나온 processed dict (또는 DB에서 복원한 동일 구조).
출력: 같은 스키마의 JSON 1개 — summary / summary_en / ko_title 품질 위주로 수정.

주의: `processed` 전체를 `.format()`에 넣지 않는다(중괄호 파싱 오류 방지).
      `build_refine_user_message()`로 유저 메시지를 조립한다.
"""

from __future__ import annotations

import json
from typing import Any

from .categories import REFINE_CATEGORY_RULES
from .fewshot import FEWSHOT_REFINE_BLOCK
from .rules_core import RULES_REFINE_CORE
from .rules_refine_panel import RULES_REFINE_PANEL
from .schema import OUTPUT_SCHEMA_REFINE_BLOCK

# gemma3 최적화 포인트:
# 1) JSON-only를 맨 앞에
# 2) Few-shot은 규칙·스키마 뒤(예시는 마지막 쪽)
# 3) 게이트는 짧은 체크리스트로 마무리
# 4) trend_insight 상세는 rules_core에만 두고 중복 블록은 쓰지 않음

REFINE_GATE_SHORT = """
[출력 직전 최종 체크 — 하나라도 위반하면 고쳐라]
□ JSON 객체 1개만 출력했는가? (바깥 텍스트·마크다운·코드펜스 없음)
□ summary label: 한글 명사구 2~8자 권장, 쉼표 없음, 콜론 머리말 없음, 영어 라벨 없음
□ summary_en label: 영어 명사구, "Auto" 없음, 메타 단어·콜론 머리말 없음
□ summary 카드 수 4~6개, summary_en 카드 수 = summary (7장 이상 입력은 병합해 4~6)
□ **summary[i].content에 한글(가-힣)이 최소 1글자 이상 포함되는가?** (해외기사라도 summary는 한국어 요약이다. 영어 문단 그대로 두지 마라.)
□ ko_title: 비어 있지 않음, 한국어, 30자 이내 권장
□ trend_insight: 기본 "" · 입력 유지 배포만 비어 있지 않은 입력 문자열 유지 · null 금지 ([핵심 계약] 6번과 동일)
□ tts_text: 한국어 구어체, 220자 이하, null 금지
□ 입력에 있던 키를 빠뜨리지 않았는가?
"""

# 배치/랩: Pydantic 검증 실패 시 두 번째 LLM 호출에만 덧붙이는 재시도 지침.
# (프롬프트만으로 100% 강제하기 어려운 형식 오류를 "한 번 더" 바로잡게 함)
REFINE_VALIDATION_RETRY_USER_SUFFIX = """

[스키마 재시도] 직전 출력이 검증에 실패했습니다.
- summary / summary_en 은 각각 **4~6개** 객체 배열이어야 하며 **개수가 서로 같아야** 합니다.
- summary_en 을 비우지 마라.
- 해외기사라도 **summary는 한국어 요약**이다. summary[i].content에 **한글이 반드시 포함**되어야 한다(영어 원문 그대로 금지).
- keywords 는 **정확히 5개**.
- artist_tags 는 **고유명사만**, 배열을 문자열로 직렬화한 값(예: "["A","B"]") 금지.
- trend_insight / ko_title / tts_text 등 문자열 필드에 null 금지 (없으면 "").
반드시 JSON 객체 1개만 출력하라(바깥 텍스트 금지).
"""

SUMMARY_REFINE_SYSTEM_PROMPT = "\n\n".join(
    [
        "【최우선 규칙】반드시 JSON 객체 1개만 출력하라. JSON 바깥에 텍스트·설명·마크다운·코드펜스를 절대 쓰지 마라.",
        RULES_REFINE_CORE.strip(),
        REFINE_CATEGORY_RULES.strip(),
        RULES_REFINE_PANEL.strip(),
        OUTPUT_SCHEMA_REFINE_BLOCK.strip(),
        FEWSHOT_REFINE_BLOCK.strip(),
        REFINE_GATE_SHORT.strip(),
        "최종 확인: 입력에 있던 키를 빼먹지 말 것. 로컬 모델(gemma3 등)은 max_tokens·컨텍스트를 여유 있게.",
    ]
)

_REFINE_USER_HEADER = """[참고 제목]
{title}

[팀 메모(없으면 빈 문자열)]
{notes}

아래 [현재 processed JSON]을 읽고, 동일한 키 구조를 유지하면서 품질만 개선한 JSON 1개를 출력하라.
수정 우선순위: ① summary label 교정 ② summary_en Auto 교체 ③ ko_title 한국어화 ④ tts_text 구어체화

[현재 processed JSON]
"""


def build_refine_user_message(
    *,
    title: str,
    notes: str,
    processed: dict[str, Any],
) -> str:
    """
    1-1차 LLM 유저 메시지.
    `processed`는 json.dumps로 붙여 `.format`과 분리한다.
    """
    header = _REFINE_USER_HEADER.format(
        title=title or "",
        notes=notes or "",
    )
    body = json.dumps(processed, ensure_ascii=False, indent=2)
    return header + body


def get_summary_refine_prompts() -> tuple[str, str]:
    """반환: (시스템 프롬프트 전체, 유저 헤더 템플릿). 권장: 유저 메시지는 `build_refine_user_message()` 사용."""
    return SUMMARY_REFINE_SYSTEM_PROMPT, _REFINE_USER_HEADER
