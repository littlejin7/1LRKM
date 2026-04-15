"""허용 sub_category 목록 렌더링 + 경계 규칙(간단 버전)."""

from __future__ import annotations

def _load_allowed_subcategories() -> list[str]:
    """
    이식 대상(yongnamho_fe)에서는 categories.py가 SoT.
    현재 레포에서는 categories.py가 없을 수 있어 fallback을 둔다.
    """
    try:
        from categories import ALLOWED_NEWS_CATEGORIES  # type: ignore

        xs = list(ALLOWED_NEWS_CATEGORIES)
        return [str(x).strip() for x in xs if str(x).strip()]
    except Exception:
        # fallback (현재 레포 호환): models.kpop_news_summary의 허용 카테고리 사용
        try:
            from models.kpop_news_summary import ALLOWED_NEWS_CATEGORIES  # type: ignore

            xs = list(ALLOWED_NEWS_CATEGORIES)
            return [str(x).strip() for x in xs if str(x).strip()]
        except Exception:
            return ["기타"]


_ALLOWED = _load_allowed_subcategories()

CATEGORY_LIST_BLOCK = "\n".join(f"- {c}" for c in _ALLOWED) if _ALLOWED else "- 기타"

