import os
import re
from typing import Any, List, Literal, Optional, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# from category_taxonomy import ALL_SUBCATEGORIES   #이거 분석해야함.

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

# ALLOWED_NEWS_CATEGORIES: tuple[str, ...] = ALL_SUBCATEGORIES

# if set(get_args(NewsCategory)) != set(ALL_SUBCATEGORIES):
#    raise RuntimeError(
#        "NewsCategory Literal must match category_taxonomy.ALL_SUBCATEGORIES"
#    )


# ─── 요약 카드 모델 ─────────────────────────────────────
class KoreanSummaryCard(BaseModel):
    """한국어 요약 카드 — label + content 구조."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    label: str = Field(..., description="한글 명사구")
    content: str = Field(..., description="본문 근거 한 줄(존댓말)")

    @field_validator("label", mode="before")
    def _trunc_label(cls, v):
        return str(v)[:25] if v else ""


class EnglishSummaryCard(BaseModel):
    """영어 요약 카드 — label + content 구조. summary와 1:1 대응."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    label: str = Field(..., description="English label")
    content: str = Field(..., description="One complete English sentence")

    @field_validator("label", mode="before")
    def _trunc_label(cls, v):
        return str(v)[:50] if v else ""


# ─── 서브 모델 ──────────────────────────────────────────


class TimelineItem(BaseModel):
    """본문에 명시된 날짜·시점이 있는 사건만 포함. 없으면 [] 반환."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

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
    model_config = ConfigDict(extra="ignore")

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
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    # 한국어 요약 카드
    summary: List[KoreanSummaryCard] = Field(
        ...,
        description="한국어 요약 카드 배열.",
    )

    # 영어 요약 카드 (summary 와 1:1)
    summary_en: List[EnglishSummaryCard] = Field(
        default_factory=list,
        description="영어 요약 카드 배열.",
    )

    # 태그
    keywords: List[str] = Field(
        default_factory=list,
        description="핵심 키워드 정렬.",
    )
    artist_tags: List[str] = Field(
        default_factory=list,
        description="본문·제목에 등장한 뮤지션·그룹·솔로명(로마자 표기).",
    )

    # 분류
    category: Literal["컨텐츠 & 작품", "인물 & 아티스트", "비즈니스 & 행사"] = Field(
        ..., description="대분류"
    )
    sub_category: NewsCategory = Field(..., description="중분류 목록 중 하나")

    # 메타
    source_name: Optional[str] = Field(
        None, max_length=100, description="언론사·사이트명 등"
    )
    language: Literal["ko", "en"] = Field(default="ko")
    ko_title: str = Field(
        default="", max_length=100, description="기사 내용을 설명하는 한국어 번역 제목."
    )
    is_k_ent: bool = Field(
        default=True,
        description="한국 연예계/콘텐츠(K-pop, K-drama, 한국 배우 등) 관련 뉴스인지 여부. 완전히 무관한 할리우드/해외 뉴스는 False.",
    )

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
    @model_validator(mode="before")
    @classmethod
    def _auto_correct_llm_mistakes(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # AI가 summary를 배열이 아닌 단순 문자열(문단)로 내뱉었을 경우, 강제로 배열화하여 구제
            if "summary" in data and isinstance(data["summary"], str):
                data["summary"] = [
                    {"label": "핵심요약", "content": data["summary"][:500]}
                ]

            # AI가 summary를 통째로 빼먹은 최악의 경우, 제목으로라도 채워서 살림
            if "summary" not in data:
                fallback = (
                    data.get("ko_title") or data.get("title") or "요약 내용 확보 불가"
                )
                data["summary"] = [{"label": "원문 참고", "content": fallback[:500]}]

            # importance를 누락했을 경우 기본값 5로 구제
            if "importance" not in data:
                data["importance"] = 5

            # 오타 교정용 최소한의 장치
            sc = data.get("sub_category", "")
            if isinstance(sc, str):
                if sc == "영화/드라마":
                    data["sub_category"] = "영화/OTT"
                elif sc == "연애/결별":
                    data["sub_category"] = "연애/결혼"

            # AI가 category에 '콘텐츠 & 작품 / 앨범/신곡' 처럼 힌트를 복사했을 경우 분해
            cat = data.get("category", "")
            if (
                isinstance(cat, str)
                and "/" in cat
                and (
                    "컨텐츠" in cat
                    or "작품" in cat
                    or "인물" in cat
                    or "비즈니스" in cat
                )
            ):
                parts = cat.split("/")
                data["category"] = parts[0].strip()
                if "sub_category" not in data and len(parts) > 1:
                    data["sub_category"] = parts[1].strip()

            # AI가 대분류(category) 칸에 중분류(예: '앨범/신곡')를 적었을 경우 위치 교정
            valid_subs = [
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
            current_cat = data.get("category", "")
            if current_cat in valid_subs:
                data["sub_category"] = current_cat
                data["category"] = "컨텐츠 & 작품"

            # 필수 필드 누락 시 기본값
            if "category" not in data:
                data["category"] = "비즈니스 & 행사"
            if "sub_category" not in data:
                data["sub_category"] = "기타"
            if "sentiment" not in data:
                data["sentiment"] = "중립"

        return data

    @field_validator("category", mode="before")
    @classmethod
    def _fix_category_typo(cls, v: str) -> str:
        if isinstance(v, str) and v == "콘텐츠 & 작품":
            return "컨텐츠 & 작품"
        return v

    @field_validator("keywords", mode="before")
    @classmethod
    def _fix_keywords_length(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            return v
        if len(v) > 5:
            return v[:5]
        while len(v) < 5:
            v.append("기타")
        return v

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
        """summary_en 부족하면 임시 채우기"""
        diff = len(self.summary) - len(self.summary_en)
        if diff > 0:
            for _ in range(diff):
                self.summary_en.append(
                    EnglishSummaryCard(label="Auto", content="Auto generated.")
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

        _sum_lines = [
            str(s.content).strip()
            for s in getattr(self, "summary", [])
            if getattr(s, "content", "")
        ]
        merged_sum = " ".join(_sum_lines[:3]).strip()

        if merged_sum:
            t = f"{t} {merged_sum}".strip() if t else merged_sum

        if len(t) < 30:
            raise ValueError("tts_text가 너무 짧습니다. 최소 30자 이상 작성하세요.")
        self.tts_text = t[:500]
        return self

    @model_validator(mode="after")
    def _validate_importance_reason(self) -> "KpopNewsSummary":
        """importance_reason의 총점이 importance와 일치하는지 검증하고 다르면 자동 교정합니다."""
        reason = self.importance_reason or ""
        match = re.search(r"=\s*(\d+)", reason)
        if match:
            total = int(match.group(1))
            if total != self.importance:
                # LLM의 숫자 불일치 시 에러를 내지 않고 문자열 안의 산식 결과값으로 자동 맞춤
                self.importance = total
        return self


def _tts_strip_bilingual_parentheticals(text: str) -> str:
    """TTS 텍스트에서 영문/괄호 등을 정제하는 헬퍼 함수"""
    if not text:
        return ""
    # 괄호와 그 안의 영문/숫자 등을 제거하는 정규식
    cleaned = re.sub(r"\s*\([^\)]*[A-Za-z0-9][^\)]*\)", "", text)
    # 중복 공백 제거
    return re.sub(r"\s+", " ", cleaned).strip()


def summary_to_processed_payload(raw_news_id: int, data: KpopNewsSummary) -> dict:
    # TTS 텍스트 처리
    tts_db = _tts_strip_bilingual_parentheticals(data.tts_text)
    if len(tts_db) < 30:
        tts_db = (data.tts_text or "").strip()[:500]

    # 최종 반환 컬럼 (누락된 필드 추가)
    return {
        "raw_news_id": raw_news_id,
        "summary": [s.model_dump() for s in data.summary],  # 객체를 딕셔너리로 변환
        "summary_en": [s.model_dump() for s in data.summary_en],  # 누락 필드 추가
        "category": data.category,
        "sub_category": data.sub_category,  # 누락 필드 추가
        "artist_tags": list(data.artist_tags),
        "keywords": list(data.keywords),
        "sentiment": data.sentiment,
        "importance": data.importance,
        "importance_reason": (data.importance_reason or "").strip() or None,
        "trend_insight": data.trend_insight,
        "timeline": [t.model_dump() for t in data.timeline],  # 누락 필드 추가
        "rag_sources": data.rag_sources,
        "is_rag_used": bool(data.is_rag_used),
        "source_name": data.source_name,
        "language": data.language,
        "ko_title": data.ko_title,
        "is_k_ent": data.is_k_ent,
        "tts_text": tts_db,
    }
