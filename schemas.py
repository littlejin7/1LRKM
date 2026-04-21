# -*- coding: utf-8 -*-
import os
import re
import json
from typing import Any, List, Literal, Optional, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ─── 카테고리 ───────────────────────────────────────────
# 한글 리터럴이 포함된 Enum형 리스트
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


# ─── 요약 카드 모델 ─────────────────────────────────────
class KoreanSummaryCard(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    label: str = Field(..., description="한글 명사구")
    content: str = Field(..., description="본문 근거 한 줄(존댓말)")

    @field_validator("label", mode="before")
    def _trunc_label(cls, v):
        return str(v)[:25] if v else ""


class EnglishSummaryCard(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    label: str = Field(..., description="English label")
    content: str = Field(..., description="One complete English sentence")

    @field_validator("label", mode="before")
    def _trunc_label(cls, v):
        return str(v)[:50] if v else ""


# ─── 서브 모델 ──────────────────────────────────────────
class TimelineItem(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    date: str = Field(..., description="")
    event: str = Field(..., min_length=1, max_length=200)

    @field_validator("date", mode="before")
    @classmethod
    def _validate_date_format(cls, v: str) -> str:
        s = str(v or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}", s):
            return "2024-01"  # Fallback
        return s


class ChartData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    billboard_200_rank: Optional[int] = None
    first_week_units: Optional[int] = None
    gaon_rank: Optional[int] = None
    other_chart_note: Optional[str] = None


# ─── 메인 스키마 ─────────────────────────────────────────
class KpopNewsSummary(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    summary: List[KoreanSummaryCard] = Field(..., min_length=1)
    summary_en: List[EnglishSummaryCard] = Field(default_factory=list, min_length=1)
    keywords: List[str] = Field(default_factory=list)
    artist_tags: List[str] = Field(default_factory=list)

    category: Literal["컨텐츠 & 작품", "인물 & 아티스트", "비즈니스 & 행사"]
    sub_category: str  # Loose validation first, then fix in validator

    source_name: Optional[str] = None
    language: Literal["ko", "en"] = "ko"
    ko_title: str = ""
    is_k_ent: bool = True
    sentiment: Literal["긍정", "부정", "중립"] = "중립"
    importance: int = Field(5, ge=1, le=10)
    importance_reason: Optional[str] = None
    trend_insight: str = ""
    timeline: List[TimelineItem] = Field(default_factory=list)
    chart_data: Optional[ChartData] = None
    rag_sources: Optional[List[str]] = None
    is_rag_used: bool = False
    tts_text: str = ""
    image_search_query: str = ""  # 실시간 이미지 검색용 (DB 저장 안 함)

    @model_validator(mode="before")
    @classmethod
    def _pre_fix_ai_errors(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # 1. summary / summary_en 보정 (리스트가 아닌 경우 또는 문자열 리스트인 경우 대응)
        for key in ["summary", "summary_en"]:
            val = data.get(key)
            if val is None:
                data[key] = []
            elif isinstance(val, str):
                # 문자열 하나만 온 경우 객체 리스트로 변환
                data[key] = [{"label": "요약", "content": val}]
            elif isinstance(val, list):
                new_list = []
                for item in val:
                    if isinstance(item, str):
                        new_list.append({"label": "주요내용", "content": item})
                    elif isinstance(item, dict):
                        new_list.append(item)
                data[key] = new_list

        # 2. 중요도(importance) 보정 (문자열로 온 경우 숫자로 변환)
        imp = data.get("importance")
        if imp is not None:
            try:
                data["importance"] = int(imp)
            except:
                data["importance"] = 5  # 기본값

        # 3. 감성(sentiment) 보정 (이상한 값이 오면 중립으로)
        sent = data.get("sentiment", "중립")
        if sent not in ["긍정", "부정", "중립"]:
            if "pos" in str(sent).lower() or "good" in str(sent).lower():
                data["sentiment"] = "긍정"
            elif "neg" in str(sent).lower() or "bad" in str(sent).lower():
                data["sentiment"] = "부정"
            else:
                data["sentiment"] = "중립"

        return data

    @model_validator(mode="before")
    @classmethod
    def _fix_all_encodings_and_categories(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # 1. 카테고리 보정 (가장 중요한 부분)
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

        sc = str(data.get("sub_category", "")).strip()
        # AI가 인코딩 문제나 오타로 잘못 보냈을 경우 가장 유사한 것으로 매칭
        if sc not in valid_subs:
            for v in valid_subs:
                # 글자 깨짐 대응: 핵심 키워드가 포함되어 있으면 인정 (예: "드라마" 포함 시 "드라마/방송")
                core = v.split("/")[0]
                if core in sc or sc in v:
                    data["sub_category"] = v
                    break
            else:
                data["sub_category"] = "기타"
        else:
            data["sub_category"] = sc

        # 2. 대분류 보정
        cat = str(data.get("category", "")).strip()
        if "컨텐츠" in cat or "작품" in cat:
            data["category"] = "컨텐츠 & 작품"
        elif "인물" in cat or "아티스트" in cat:
            data["category"] = "인물 & 아티스트"
        elif "비즈니스" in cat or "행사" in cat:
            data["category"] = "비즈니스 & 행사"
        else:
            data["category"] = "비즈니스 & 행사"

        # 3. 기타 필수 필드 보정
        if "sentiment" not in data or data["sentiment"] not in ["긍정", "부정", "중립"]:
            data["sentiment"] = "중립"

        return data

    @model_validator(mode="after")
    def _final_polishing(self) -> "KpopNewsSummary":
        # 아티스트 태그 보정
        if not self.artist_tags:
            self.artist_tags = ["K-Enter"]
        return self


def summary_to_processed_payload(raw_news_id: int, data: KpopNewsSummary) -> dict:
    return {
        "raw_news_id": raw_news_id,
        "summary": [s.model_dump() for s in data.summary],
        "summary_en": [s.model_dump() for s in data.summary_en],
        "category": data.category,
        "sub_category": data.sub_category,
        "artist_tags": list(data.artist_tags),
        "keywords": list(data.keywords),
        "sentiment": data.sentiment,
        "importance": data.importance,
        "importance_reason": data.importance_reason,
        "trend_insight": data.trend_insight,
        "timeline": [t.model_dump() for t in data.timeline],
        "source_name": data.source_name,
        "language": data.language,
        "ko_title": data.ko_title,
        "is_k_ent": data.is_k_ent,
        "tts_text": data.tts_text,
    }
