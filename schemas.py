"""
KpopNewsSummary — LLM structured output 계약.

DB 저장은 `summary_to_processed_payload`가 선택한 컬럼만 채운다(앨범·차트 등은 LLM 필드만 유지).

[필드별 엄격 규칙]
summary        : 한국어 '요약 카드' 배열. 정확히 4~6개.
각 카드: {label, content}
label: 2~10자 한글 명사구(짧고 구체). 각 줄의 포인트를 한눈에 보이게.
content: 본문 근거 한 줄(존댓말). 서로 다른 관점(사실/맥락/영향 등)에서 압축해 써라.    
금지: summary 카드 content를 서로 복붙/중복으로 문장 수를 채우는 행위.

summary_en     : 영어 '요약 카드' 배열. summary와 카드 개수(4~6)와 순서가 정확히 1:1 대응되게 작성하라.
각 카드: {label, content}
label: 2~30자 영어 명사구(짧고 구체).
content: 영어 한 줄 요지(complete sentence). 과장/추측 금지.
i번째 summary_en 카드는 i번째 summary 카드와 같은 사실/초점을 영어로 옮긴 것이다.

artist_tags    : 제목/본문에 실제로 등장한 뮤지션·그룹·솔로명. 없으면 [].
keywords       : 정확히 3개. 비인명 축(테마·형식·행사·차트명 등)만.
sub_category   : 허용 목록에서 정확히 하나. 오타/변형/영문 라벨 금지.
sentiment      : "긍정"|"부정"|"중립" 중 하나.
sentiment_score: 항상 null. (백엔드에서 sentiment/importance로 계산)
importance     : 1~10 정수.
importance_reason: [IPa+사건b+파급c+기본1=총점] 형식. a,b,c는 0~3 정수. 총점 = importance 값과 일치.
trend_insight  : 한 줄(한국어). 본문 근거 불충분하면 반드시 빈 문자열 "".
timeline       : date는 "YYYY-MM" 형식. 본문에 명시된 날짜만. 없으면 [].
tts_text       : 한국어 구어체 라디오 브리핑(150~220자 권장). URL/해시태그/이모지/마크다운 금지.
"""


import os
import re
from typing import List, Literal, Optional, get_args  

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from category_taxonomy import ALL_SUBCATEGORIES   #이거 분석해야함. 

# ─── 카테고리 ───────────────────────────────────────────
NewsCategory = Literal[
    "음악/차트",
    "앨범/신곡",
    "콘서트/투어",
    "드라마/방송",
    "예능/방송",
    "공연/전시",
    "영화/OTT",
    "팬덤/SNS",
    "스캔들/논란",
    "인사/동정",
    "미담/기부",
    "연애/결혼",
    "입대/군복무",
    "산업/기획사",
    "해외반응",
    "마케팅/브랜드",
    "행사/이벤트",
    "기타",
]

ALLOWED_NEWS_CATEGORIES: tuple[str, ...] = ALL_SUBCATEGORIES

if set(get_args(NewsCategory)) != set(ALL_SUBCATEGORIES):
    raise RuntimeError(
        "NewsCategory Literal must match category_taxonomy.ALL_SUBCATEGORIES"
    )


# ─── 요약 카드 모델 ─────────────────────────────────────
class KoreanSummaryCard(BaseModel):
    """한국어 요약 카드 — label + content 구조."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(..., min_length=2, max_length=10, description="2~10자 한글 명사구")
    content: str = Field(..., min_length=1, max_length=300, description="본문 근거 한 줄(존댓말)")


class EnglishSummaryCard(BaseModel):
    """영어 요약 카드 — label + content 구조. summary와 1:1 대응."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(..., min_length=2, max_length=30, description="English label (2~30 chars)")
    content: str = Field(..., min_length=1, max_length=300, description="One complete English sentence")


# ─── 서브 모델 ──────────────────────────────────────────

class TimelineItem(BaseModel):
    """본문에 명시된 날짜·시점이 있는 사건만 포함. 없으면 [] 반환."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: str = Field(..., description="YYYY-MM 형식만 허용")
    event: str = Field(
        ..., min_length=1, max_length=200, description="본문에 명시된 사건"
    )

    @field_validator("date", mode="before")
    @classmethod
    def _validate_date_format(cls, v: str) -> str:
        s = str(v or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}", s):
            raise ValueError(f"date는 YYYY-MM 형식이어야 합니다. (입력값: {s!r})")
        return s


class ChartData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    billboard_200_rank: Optional[int] = Field(
        default=None, description="빌보드 200 순위. 양의 정수만."
    )
    first_week_units: Optional[int] = Field(
        default=None, description="첫 주 판매 수. 아라비아 숫자 정수."
    )
    gaon_rank: Optional[int] = Field(
        default=None, description="가온 차트 순위. 양의 정수."
    )
    other_chart_note: Optional[str] = Field(
        None, description="위 필드에 담기 어려운 차트·수치를 짧게"
    )


# ─── 메인 스키마 ─────────────────────────────────────────
class KpopNewsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
        
    # 한국어 요약 카드 4~6개
    summary:List[KoreanSummaryCard] = Field(...,min_length=4,max_length=6,description=(
            "한국어 요약 카드 {label, content} 배열. 정확히 4~6개. "
            "짧은 기사도 핵심 사실·맥락·영향 등 서로 다른 초점으로 구성(본문·제목 근거, 환각 금지). "
            "본문에 없는 내용으로 카드 개수를 채우지 말 것."
        ),
    )
    
    # 영어 요약 카드 4~6개 (summary 와 1:1)
    summary_en: List[EnglishSummaryCard] = Field(...,min_length=4,max_length=6,description="영어 요약 카드 {label, content} 배열. summary 와 카드 개수·순서 동일(1:1 대응). "
            "각 카드는 동일 인덱스의 한국어 카드와 같은 초점..",
    )

    # 태그
    keywords: List[str] = Field(
        ...,
        min_length=5,
        max_length=5,
        description="핵심 키워드 정확히 5개. 인명·그룹명 금지(그런 이름은 artist_tags 전용). 매체·형식·테마·장르·행사 등 비인명 축만.",
    )
    artist_tags: List[str] = Field(
        default_factory=list,
        max_length=30,
        description="본문·제목에 등장한 뮤지션·그룹·솔로명(로마자 표기). 언급된 인물·그룹은 여기에 넣고, 같은 이름을 keywords에 넣지 말 것. 없으면 []",
    )

    # 분류
    category: NewsCategory = Field(..., description="중분류 정확히 하나.")
    sub_category: Optional[str] = Field(
        None,
        max_length=100,
        description="허용 목록에서 정확히 하나. 오타/변형/영문 라벨 금지.",
    )

    # 메타
    source_name: Optional[str] = Field(
        None, max_length=100, description="언론사·사이트명 등"
    )
    language: Literal["ko", "en"] = Field(default="ko")

    # 감성
    sentiment: Literal["긍정", "부정", "중립"]  # ✅ 유지 (대시보드 뱃지 + Mistral 참조)
    # sentiment_score ← ❌ 제거

    # 중요도
    importance: int = Field(
        ...,
        ge=1,
        le=10,
        description=(
            "1~10. 내부 루브릭: IP(주체 영향력) 0~3 + 사건 무게 0~3 + 시장·글로벌 파급 0~3 → 합 0~9에 기본점 1 가산, 상한 10. "
            "7~8점 쏠림 금지. importance_reason에 근거 한 줄을 적을 것."
        ),
    )

    importance_reason: Optional[str] = Field(
        None,
        max_length=400,
        description=(
            "필수에 가깝게 한 줄 작성. 형식: [IPa+사건베+파급씨+기본1=총점] 한국어 근거. "
            "괄호 안 IP·사건·파급(각 0~3 정수) 합에 기본1을 더한 값이 importance와 반드시 일치해야 한다. "
            "본문에 팬·SNS 근거가 없으면 팬덤류 표현으로 점수를 설명하지 말 것."
        ),
    )

    # 인사이트
    trend_insight: str = Field(
        default="",
        description="본문·키워드만으로 한 줄(한국어) 도출. 본문 근거 없을시 null.",
    )
    timeline: List[TimelineItem] = Field(
        default_factory=list,
        description="본문에 명시된 날짜가 있는 사건만. 없으면 [].",
    )

    # 차트
    chart_data: Optional[ChartData] = Field(
        None, description="차트·판매 수치가 없으면 null."
    )

    # RAG
    rag_sources: Optional[List[str]] = Field(None, description="RAG 미사용 시 null.")
    is_rag_used: bool = Field(default=False)

    # TTS
    tts_text: str = Field(
        default="",
        max_length=500,
        description="한국어 구어체 라디오 브리핑(150~220자 권장). URL/해시태그/이모지/마크다운 금지.",
    )

    # ─── validators ──────────────────────────────────────
    @field_validator("tts_text")
    @classmethod
    def _tts_text_strip(cls, v: str) -> str:
        s = (v or "").strip()
        if os.getenv("SUMMARY_BILINGUAL", "").strip().lower() in ("1", "true", "yes"):
            out = re.sub(r"\s*\([^\)]*[A-Za-z][^\)]*\)", "", s)
            s = re.sub(r"\s+", " ", out).strip()
        return s

    @field_validator("trend_insight")
    @classmethod
    def _trend_insight_strip(cls, v: str) -> str:
        return (v or "").strip()

    @model_validator(mode="after")
    def _summary_en_matches_summary(self) -> "KpopNewsSummary":
        """summary_en 문장 수는 summary와 반드시 동일."""
        if len(self.summary_en) != len(self.summary):
            raise ValueError(
                f"summary_en은 summary와 문장 수가 동일해야 합니다. "
                f"(summary={len(self.summary)}, summary_en={len(self.summary_en)})"
            )
        return self

    @model_validator(mode="after")
    def _ensure_tts_text(self) -> "KpopNewsSummary":
        t = self.tts_text
        if len(t) > 500:
            self.tts_text = t[:500]
            return self
        if len(t) >= 30:
            return self

        _sum_lines = [str(s).strip() for s in self.summary if str(s).strip()]
        merged_sum = " ".join(_sum_lines[:3]).strip()
        brief_joined = " ".join(
            x.content.strip() for x in self.briefing if x.content
        ).strip()

        if merged_sum:
            t = f"{t} {merged_sum}".strip() if t else merged_sum
        if len(t) < 30 and brief_joined:
            t = f"{t} {brief_joined}".strip() if t else brief_joined

        if len(t) < 30:
            raise ValueError("tts_text가 너무 짧습니다. 최소 30자 이상 작성하세요.")
        self.tts_text = t[:500]
        return self

    @model_validator(mode="after")
    def _validate_importance_reason(self) -> "KpopNewsSummary":
        """importance_reason의 총점이 importance와 일치하는지 검증."""
        reason = self.importance_reason or ""
        match = re.search(r"=\s*(\d+)", reason)
        if match:
            total = int(match.group(1))
            if total != self.importance:
                raise ValueError(
                    f"importance_reason 총점({total})이 importance({self.importance})와 일치하지 않습니다."
                )
        return self

def summary_to_processed_payload(raw_news_id: int, data: KpopNewsSummary) -> dict:

    tts_db = _tts_strip_bilingual_parentheticals(data.tts_text)
    if len(tts_db) < 30:
        tts_db = (data.tts_text or "").strip()[:500]
    
    # 최종 반환 컬럼
    return {
        "raw_news_id": raw_news_id,
        "summary": list(data.summary),
        "category": data.category,
        "artist_tags": list(data.artist_tags),
        "keywords": list(data.keywords),
        "sentiment": data.sentiment,
        "importance": data.importance,
        "importance_reason": (data.importance_reason or "").strip() or None,
        "trend_insight": data.trend_insight,
        "rag_sources": data.rag_sources,
        "is_rag_used": bool(data.is_rag_used),
        "source_name": data.source_name,
        "language": data.language,
        "tts_text": tts_db,
    }