"""
database.py — DB 테이블 정의 및 연결 설정

테이블 구조:
  raw_news        : 크롤링 원본 저장 (1차)
  processed_news  : LLM 가공 결과 저장 (2차)
  past_news       : 아티스트 과거 관련 뉴스 저장 (3차)
"""

from datetime import datetime
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ── DB 연결 설정 ──
DATABASE_URL = "sqlite:///k_enter_news.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ── 1차 테이블: raw_news (크롤링 원본) ──
class RawNews(Base):
    __tablename__ = "raw_news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    url = Column(String(1000), unique=True, nullable=False)
    published_at = Column(DateTime, nullable=True)
    crawled_at = Column(DateTime, default=datetime.now)
    is_processed = Column(Boolean, default=False)
    category = Column(String(50), nullable=True)

    processed = relationship("ProcessedNews", back_populates="raw", uselist=False)

    def __repr__(self):
        return f"<RawNews(id={self.id}, title='{self.title[:30]}...')>"


# ── 2차 테이블: processed_news (LLM 가공 결과) ──
class ProcessedNews(Base):
    __tablename__ = "processed_news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_news_id = Column(Integer, ForeignKey("raw_news.id"), nullable=False)

    # ── 분류 (스키마: category, sub_category) ──
    category = Column(String(40), nullable=True)          # 중분류
    category_major = Column(String(40), nullable=True)    # 대분류
    category_sub = Column(String(40), nullable=True)      # 소분류
    sub_category = Column(String(100), nullable=True)     # 세분화 카테고리

    # ── 요약 (스키마: summary, summary_en) ──
    summary = Column(JSON, nullable=True)                 # List[str] 5~7문장 한국어
    summary_en = Column(JSON, nullable=True)              # List[str] 5~7문장 영어

    # ── 브리핑 (스키마: briefing) ──
    briefing = Column(JSON, nullable=True)                # [{"label": str, "content": str}, ...]

    # ── 태그 (스키마: keywords, artist) ──
    keywords = Column(JSON, nullable=True)                # List[str] 정확히 5개
    artist_tags = Column(JSON, nullable=True)             # List[str] 인물/그룹명

    # ── 감성 (스키마: sentiment) ──
    sentiment = Column(String(10), nullable=True)         # 긍정 | 부정 | 중립

    # ── 중요도 (스키마: importance, importance_reason) ──
    importance = Column(Integer, nullable=True)           # 1~10
    importance_reason = Column(Text, nullable=True)       # [IPa+사건b+파급c+기본1=총점]

    # ── 인사이트 (스키마: trend_insight, timeline) ──
    trend_insight = Column(Text, nullable=True)           # 한 줄 트렌드 인사이트
    timeline = Column(JSON, nullable=True)                # [{"date": "YYYY-MM", "event": str}, ...]

    # ── RAG (스키마: rag_sources, is_rag_used) ──
    rag_sources = Column(JSON, nullable=True)
    is_rag_used = Column(Boolean, default=False)

    # ── TTS (스키마: tts_text) ──
    tts_text = Column(Text, nullable=True)

    # ── 메타 (스키마: source_name, language) ──
    source_name = Column(String(100), nullable=True)
    language = Column(String(5), nullable=True)           # ko | en

    # ── 기타 ──
    url = Column(String(1000), nullable=True)
    thumbnail_url = Column(String(1000), nullable=True)
    processed_at = Column(DateTime, default=datetime.now)

    raw = relationship("RawNews", back_populates="processed")

    def __repr__(self):
        return f"<ProcessedNews(id={self.id}, category='{self.category}')>"


# ── 3차 테이블: past_news (아티스트 과거 관련 뉴스) ──
class PastNews(Base):
    __tablename__ = "past_news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    processed_news_id = Column(Integer, ForeignKey("processed_news.id"), nullable=False)
    artist_name = Column(String(200), nullable=False)
    artist_type = Column(String(20), nullable=True)
    artist_agency = Column(String(100), nullable=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    url = Column(String(1000), nullable=False)
    published_at = Column(DateTime, nullable=True)
    summary = Column(Text, nullable=True)
    category = Column(String(30), nullable=True)
    keywords = Column(JSON, nullable=True)
    sentiment = Column(String(10), nullable=True)
    sentiment_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    relation_type = Column(String(50), nullable=True)
    crawled_at = Column(DateTime, default=datetime.now)
    source_name = Column(String(100), nullable=True)
    thumbnail_url = Column(String(1000), nullable=True)

    __table_args__ = (
        UniqueConstraint("url", "artist_name", name="uq_past_url_artist"),
    )

    processed = relationship("ProcessedNews", backref="past_news_list")

    def __repr__(self):
        return f"<PastNews(id={self.id}, artist='{self.artist_name}', title='{self.title[:30]}...')>"


# ── 테이블 생성 ──
Base.metadata.create_all(engine)


# ── 기존 SQLite DB에 새 컬럼 추가 (ALTER TABLE) ──
def _sqlite_add_missing_columns() -> None:
    """기존 SQLite DB를 날리지 않고 새 컬럼만 추가."""
    if engine.dialect.name != "sqlite":
        return

    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(processed_news)")).fetchall()
        existing = {r[1] for r in rows}

        new_columns: list[tuple[str, str]] = [
            ("category_major",    "VARCHAR(40)"),
            ("category_sub",      "VARCHAR(40)"),
            ("sub_category",      "VARCHAR(100)"),
            ("summary_en",        "TEXT"),
            ("briefing",          "TEXT"),
            ("importance",        "INTEGER"),
            ("importance_reason", "TEXT"),
            ("trend_insight",     "TEXT"),
            ("timeline",          "TEXT"),
            ("rag_sources",       "TEXT"),
            ("is_rag_used",       "INTEGER"),
            ("language",          "VARCHAR(5)"),
        ]

        for col, sqltype in new_columns:
            if col in existing:
                continue
            try:
                conn.execute(text(f"ALTER TABLE processed_news ADD COLUMN {col} {sqltype}"))
                conn.commit()
                print(f"[database] 컬럼 추가됨: {col} ({sqltype})")
            except Exception as e:
                conn.rollback()
                print(f"[database] 컬럼 추가 실패: {col} — {e!r}")


_sqlite_add_missing_columns()


# ── 세션 헬퍼 ──
@contextmanager
def get_session():
    """
    사용법:
        with get_session() as session:
            session.add(...)
            session.commit()
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
