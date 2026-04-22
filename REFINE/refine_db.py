"""
1-1차 refine로 검증된 KpopNewsSummary를 processed_news 행에 반영(덮어쓰기).

- raw_news_id는 항상 기존 행 값(외부 LLM이 잘못 적은 ID를 믿지 않음).
- url / thumbnail_url / published_at / crawled_at은 기존 행 유지(메타 보존).
- briefing은 Pydantic 모델에 없을 수 있어 `parsed` 원본에 키가 있으면 그걸 쓰고, 없으면 기존 DB 값 유지.
- trend_insight: 1-1차 정책상 후속(RAG)에서 채우므로 **저장 시 항상 DB NULL** (LLM이 문장을 넣어도 반영하지 않음).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from database import ProcessedNews
from schemas import KpopNewsSummary, summary_to_processed_payload

_EXCLUDE_FROM_PROCESSED_DUMP = frozenset({"id", "processed_at"})


def processed_news_row_to_dict(p: ProcessedNews) -> dict:
    """DB `processed_news` 행 → refine 입력용 dict (랩·배치 공용)."""
    out: dict = {}
    for c in p.__table__.columns:
        if c.name in _EXCLUDE_FROM_PROCESSED_DUMP:
            continue
        v = getattr(p, c.name)
        if hasattr(v, "isoformat") and v is not None:
            out[c.name] = v.isoformat()
        else:
            out[c.name] = v
    return out


def apply_refined_to_processed(
    session: Session,
    processed_id: int,
    validated: KpopNewsSummary,
    parsed: dict[str, Any] | None = None,
) -> ProcessedNews:
    """
    `processed_news.id == processed_id` 행을 refine 결과로 갱신하고 commit한다.

    Raises:
        ValueError: 해당 id 행이 없을 때
    """
    row = session.query(ProcessedNews).filter(ProcessedNews.id == int(processed_id)).first()
    if row is None:
        raise ValueError(f"processed_news id={processed_id} 없음")

    existing_cols = {c.name for c in row.__table__.columns}

    raw_id = int(row.raw_news_id)
    payload = summary_to_processed_payload(raw_id, validated)

    # LLM이 trend_insight에 글을 써도 1-1차 DB 반영에서는 비운다(프롬프트와 달리 모델이 자주 채움).
    payload["trend_insight"] = None

    # briefing은 레포/DB 스키마에 따라 없을 수 있다.
    if "briefing" in existing_cols:
        if parsed is not None and "briefing" in parsed:
            payload["briefing"] = parsed["briefing"]
        else:
            payload["briefing"] = getattr(row, "briefing", None)
    else:
        payload.pop("briefing", None)

    for key, val in payload.items():
        if key == "raw_news_id":
            continue
        if key not in existing_cols:
            continue
        setattr(row, key, val)

    row.processed_at = datetime.now()
    session.commit()
    session.refresh(row)
    return row
