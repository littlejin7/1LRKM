import os
import re

# 설정값
# ═══════════════════════════════════════════════════

def _env_int(name: str, default: int) -> int:
    v = (os.getenv(name) or "").strip()
    try:
        return int(v) if v else default
    except Exception:
        return default


RAW_CONTENT_MAX_CHARS = _env_int("RAW_CONTENT_MAX_CHARS", 8000)
TAVILY_MAX_RESULTS = 100  # ★ 수집 극대화: 100건 (Tavily 최대치)
MAX_PER_DOMAIN = max(1, _env_int("CRAWL_MAX_PER_DOMAIN", 10))
TAVILY_RETRY = 2
LOOKBACK_DAYS = 7  # ★ 최근 1주일 범위
RSS_MAX_TOTAL = 9999  # ★ RSS 무제한 (피드가 제공하는 최대치)

# ★ 최소 본문 길이: 일반 200자, RSS 50자
MIN_CONTENT_LEN = 200
RSS_MIN_CONTENT_LEN = 50



# ═══════════════════════════════════════════════════
# 본문 정제

# ═══════════════════════════════════════════════════

_NOISE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"Advertisement",
        r"Sponsored",
        r"©.*",
        r"All rights reserved.*",
        r"Reporter\s*:\s*.*",
        r"Contact\s*:\s*.*",
        r"Email\s*:\s*.*",
        r"RELATED ARTICLES.*",
        r"Read more.*",
        r"Sign up for.*newsletter.*",
        r"Subscribe\s*(to|for)?\s*.*",
        r"Follow us on.*",
        r"Share this article.*",
        r"Tags\s*:.*",
        r"Photo\s*credit\s*:.*",
        r"Source\s*:.*",
    ]
]


def clean_content(text: str, min_len: int = MIN_CONTENT_LEN) -> str:
    """광고·불필요 텍스트 제거 후 정제. ★ 최소 길이 미달 시 빈 문자열 반환."""
    if not text:
        return text
    for pat in _NOISE_PATTERNS:
        text = pat.sub("", text)

    lines = [line.strip() for line in text.split("\n") if len(line.strip()) >= 20]
    cleaned = re.sub(r"\n{2,}", "\n", "\n".join(lines)).strip()

    if len(cleaned) < min_len:
        return ""

    return cleaned



# ═══════════════════════════════════════════════════

CATEGORY_MAPPING = {
    # 컨텐츠 & 작품
    "음악/차트": "컨텐츠 & 작품",
    "앨범/신곡": "컨텐츠 & 작품",
    "콘서트/투어": "컨텐츠 & 작품",
    "드라마/방송": "컨텐츠 & 작품",
    "예능/방송": "컨텐츠 & 작품",
    "공연/전시": "컨텐츠 & 작품",
    "영화/OTT": "컨텐츠 & 작품",
    # 인물 & 아티스트
    "팬덤/SNS": "인물 & 아티스트",
    "스캔들/논란": "인물 & 아티스트",
    "인사/동정": "인물 & 아티스트",
    "미담/기부": "인물 & 아티스트",
    "연애/결혼": "인물 & 아티스트",
    "입대/군복무": "인물 & 아티스트",
    # 비즈니스 & 행사
    "산업/기획사": "비즈니스 & 행사",
    "해외반응": "비즈니스 & 행사",
    "마케팅/브랜드": "비즈니스 & 행사",
    "행사/이벤트": "비즈니스 & 행사",
    "기타": "비즈니스 & 행사",
}


def get_standard_category(sub_name: str) -> tuple[str, str]:
    category = CATEGORY_MAPPING.get(sub_name, "비즈니스 & 행사")
    return category, sub_name



