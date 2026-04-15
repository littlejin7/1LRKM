"""
app.py — 진입점 (라우팅만 담당)

실행: poetry run streamlit run app.py
"""

import sys
import sqlite3
import json
from pathlib import Path

# 모듈 경로 설정 (반드시 다른 import 전에)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from components.styles import apply_styles
from components.sidebar import render_sidebar
from components.main_page import render_dashboard

DB_PATH = Path("k_enter_news.db")

st.set_page_config(
    page_title="K-ENT Now",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_styles()


# ── DB 유틸 ───────────────────────────────────────────────────────────────────

def _open():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def _j(v):
    if v is None:
        return []
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return []


@st.cache_data(show_spinner=False)
def load_processed():
    con = _open()
    cur = con.cursor()
    cur.execute("""
        SELECT
            p.id, r.title, p.url, p.category, p.summary,
            p.keywords, p.artist_tags, p.sentiment, p.sentiment_score,
            p.source_name, p.tts_text, p.processed_at, p.thumbnail_url
        FROM processed_news p
        JOIN raw_news r ON r.id = p.raw_news_id
        ORDER BY p.id DESC
    """)
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r["id"],
            "title": r["title"] or "",
            "url": r["url"] or "",
            "category": r["category"] or "기타",
            "summary": _j(r["summary"]),
            "keywords": _j(r["keywords"]),
            "artist_tags": _j(r["artist_tags"]),
            "sentiment": r["sentiment"] or "neutral",
            "sentiment_score": r["sentiment_score"] if r["sentiment_score"] is not None else 0.0,
            "source_name": r["source_name"] or "",
            "tts_text": r["tts_text"] or "",
            "processed_at": r["processed_at"] or "",
            "thumbnail_url": r["thumbnail_url"] or "",
        }
        for r in rows
    ]


@st.cache_data(show_spinner=False)
def load_past():
    con = _open()
    cur = con.cursor()
    # 1. 쿼리에서는 thumbnail_url을 뺐습니다.
    cur.execute("""
        SELECT
            id, processed_news_id, artist_name, title, url, summary,
            relation_type, relevance_score, sentiment, category,
            source_name, published_at
        FROM past_news
        ORDER BY id DESC
    """)
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r["id"],
            "processed_news_id": r["processed_news_id"],
            "artist_name": r["artist_name"] or "",
            "title": r["title"] or "",
            "url": r["url"] or "",
            "summary": r["summary"] or "",
            "relation_type": r["relation_type"] or "",
            "relevance_score": r["relevance_score"] if r["relevance_score"] is not None else 0.0,
            "sentiment": r["sentiment"] or "neutral",
            "category": r["category"] or "기타",
            "source_name": r["source_name"] or "",
            "published_at": r["published_at"] or "",
        }
        for r in rows
    ]

# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    if not DB_PATH.exists():
        st.error("현재 폴더에 k_enter_news.db 파일이 없습니다.")
        st.stop()

    processed = load_processed()
    past = load_past()

    # 사이드바 → keyword, 대분류, 중분류, 감성필터, 자동새로고침
    keyword, major, sub, sentiments, auto_refresh = render_sidebar()

    # 대시보드 렌더링
    render_dashboard(processed, past, keyword, major, sub, sentiments)


if __name__ == "__main__":
    main()