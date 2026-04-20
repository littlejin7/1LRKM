"""허용 sub_category 목록 — 1-1차에서 분류를 손댈 때만 참조.

1-pass `prompts/summary/categories.py`와 동일 소스(`CATEGORY_LIST_BLOCK`)를 써 목록이 어긋나지 않게 한다.
"""

from __future__ import annotations

from ..summary.categories import CATEGORY_LIST_BLOCK

REFINE_SUBCATEGORY_LIST_BLOCK = CATEGORY_LIST_BLOCK

REFINE_CATEGORY_RULES = f"""
[분류 필드 — 1-1차]
- **입력이 이미 타당하면 category / sub_category 는 그대로 둔다.** (토큰 낭비·검증 리스크 감소)
- 고칠 때만: **category** 는 `컨텐츠 & 작품` / `인물 & 아티스트` / `비즈니스 & 행사` **세 문자열 중 하나 전체**(줄임 `작품` 금지).
- **sub_category** 는 아래 **허용 목록과 문자열이 정확히 일치**해야 한다(슬래시 위치·띄어쓰기 변경 금지).

허용 sub_category:
{REFINE_SUBCATEGORY_LIST_BLOCK}
"""
