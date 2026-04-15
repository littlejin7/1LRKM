"""
엔터 뉴스 대분류 / 중분류 체계 (대시보드·LLM 가공 공통)

제안 보강 중분류:
  - 컨텐츠 & 작품: 영화/OTT (극·OTT 단독 보도)
  - 인물 & 아티스트: 연애/결혼, 입대/군복무 (연예 뉴스 빈도 높음)
"""

from __future__ import annotations

# 대분류 → 중분류
CATEGORY_HIERARCHY: dict[str, list[str]] = {
    "컨텐츠 & 작품": [
        "음악/차트",
        "앨범/신곡",
        "콘서트/투어",
        "드라마/방송",
        "예능/방송",
        "공연/전시",
        "영화/OTT",
    ],
    "인물 & 아티스트": [
        "팬덤/SNS",
        "스캔들/논란",
        "인사/동정",
        "미담/기부",
        "연애/결혼",
        "입대/군복무",
    ],
    "비즈니스 & 행사": [
        "산업/기획사",
        "해외반응",
        "마케팅/브랜드",
        "행사/이벤트",
        "기타",
    ],
}

# 카드/배지 색 (중분류 기준)
CATEGORY_SUB_COLORS: dict[str, str] = {
    "음악/차트": "#1D9E75",
    "앨범/신곡": "#BA7517",
    "콘서트/투어": "#0F6E56",
    "드라마/방송": "#D4537E",
    "예능/방송": "#993556",
    "공연/전시": "#0E7490",
    "영화/OTT": "#C2410C",
    "팬덤/SNS": "#5F5E5A",
    "스캔들/논란": "#D85A30",
    "인사/동정": "#6366F1",
    "미담/기부": "#059669",
    "연애/결혼": "#EC4899",
    "입대/군복무": "#64748B",
    "산업/기획사": "#7F77DD",
    "해외반응": "#378ADD",
    "마케팅/브랜드": "#CA8A04",
    "행사/이벤트": "#9333EA",
    "기타": "#888780",
}

# 구버전 category(단일) → (대분류, 중분류)
LEGACY_CATEGORY_TO_PAIR: dict[str, tuple[str, str]] = {
    "아이돌": ("인물 & 아티스트", "팬덤/SNS"),
    "드라마": ("컨텐츠 & 작품", "드라마/방송"),
    "영화": ("컨텐츠 & 작품", "영화/OTT"),
    "글로벌": ("비즈니스 & 행사", "해외반응"),
    "entertainment": ("비즈니스 & 행사", "기타"),
    "기타": ("비즈니스 & 행사", "기타"),
}


def all_majors() -> list[str]:
    return list(CATEGORY_HIERARCHY.keys())


def all_subs() -> list[str]:
    return sorted({s for subs in CATEGORY_HIERARCHY.values() for s in subs})


def subs_for_majors(majors: list[str]) -> list[str]:
    if not majors:
        return all_subs()
    out: list[str] = []
    for m in majors:
        out.extend(CATEGORY_HIERARCHY.get(m, []))
    return sorted(set(out))


def validate_pair(major: str | None, sub: str | None) -> tuple[str, str]:
    m = (major or "").strip()
    s = (sub or "").strip()
    if s in LEGACY_CATEGORY_TO_PAIR:
        return LEGACY_CATEGORY_TO_PAIR[s]
    if m in CATEGORY_HIERARCHY and s in CATEGORY_HIERARCHY[m]:
        return m, s
    if s:
        for mj, subs in CATEGORY_HIERARCHY.items():
            if s in subs:
                return mj, s
    return ("비즈니스 & 행사", "기타")


def resolve_row_categories(row: dict) -> tuple[str, str]:
    """DB 행(dict)에서 대분류·중분류 추출 (신규 컬럼 + 구 category 호환)."""
    major = (row.get("category_major") or "").strip() or None
    sub = (row.get("category_sub") or "").strip() or None
    legacy = (row.get("category") or "").strip() or None

    if major and sub:
        return validate_pair(major, sub)
    if sub and not major:
        return validate_pair(None, sub)
    if legacy:
        if legacy in LEGACY_CATEGORY_TO_PAIR:
            return LEGACY_CATEGORY_TO_PAIR[legacy]
        return validate_pair(None, legacy)
    return ("비즈니스 & 행사", "기타")


def accent_color_for_row(row: dict) -> str:
    _, sub = resolve_row_categories(row)
    return CATEGORY_SUB_COLORS.get(sub, CATEGORY_SUB_COLORS["기타"])


def llm_prompt_category_block() -> str:
    """processor SYSTEM_PROMPT에 붙일 분류 설명."""
    lines = ["분류(필수): category_major, category_sub 는 아래 조합에서만 고른다."]
    for maj, subs in CATEGORY_HIERARCHY.items():
        lines.append(f"- {maj}: {', '.join(subs)}")
    lines.append(
        "구분이 애매하면 비즈니스 & 행사 / 기타. "
        "category 필드는 쓰지 말고 category_major, category_sub 만 채운다."
    )
    return "\n".join(lines)
