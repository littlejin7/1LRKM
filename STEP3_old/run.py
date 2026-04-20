"""
run.py — 진입점 (라우팅만 담당)

실행: streamlit run STEP3/run.py
"""

import sys
import sqlite3
import json
from pathlib import Path

# 모듈 경로 설정 (반드시 다른 import 전에)
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from components.styles import apply_styles
# from components.sidebar import render_sidebar
from components.main_page import render_dashboard

DB_PATH = Path("k_enter_news.db")

st.set_page_config(
    page_title="K-ENT Now",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 사이드바 제거 CSS
st.markdown(
    """
<style>
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
</style>
""",
    unsafe_allow_html=True,
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
    cur.execute(
        """
        SELECT
            p.id, r.title, p.url, p.category, p.summary,
            p.keywords, p.artist_tags, p.sentiment, p.importance,
            p.source_name, p.tts_text, p.processed_at, p.thumbnail_url
        FROM processed_news p
        JOIN raw_news r ON r.id = p.raw_news_id
        ORDER BY p.importance DESC, p.id DESC
    """
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r["id"],
            "title": r["title"] or "",
            "url": r["url"] or "",
            "category": r["category"] or "기타",
            "sub_category": "",
            "summary": _j(r["summary"]),
            "keywords": _j(r["keywords"]),
            "artist_tags": _j(r["artist_tags"]),
            "sentiment": r["sentiment"] or "neutral",
            "importance": r["importance"] or 0,
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
    cur.execute(
        """
        SELECT
            id, processed_news_id, artist_tags, title, url, summary,
            relation_type, relevance_score, sentiment, category,
            source_name, published_at
        FROM past_news
        ORDER BY id DESC
    """
    )
    rows = cur.fetchall()
    con.close()
    return [
        {
            "id": r["id"],
            "processed_news_id": r["processed_news_id"],
            "artist_name": (_j(r["artist_tags"])[0] if _j(r["artist_tags"]) else ""),
            "title": r["title"] or "",
            "url": r["url"] or "",
            "summary": r["summary"] or "",
            "relation_type": r["relation_type"] or "",
            "relevance_score": (
                r["relevance_score"] if r["relevance_score"] is not None else 0.0
            ),
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

    # 사이드바 없이 기본값 설정
    keyword = ""
    category = "전체"
    sub_category = "전체"
    sentiments = ["긍정", "부정", "중립"]
    # auto_refresh = False

    # 대시보드 렌더링
    render_dashboard(processed, past, keyword, category, sub_category, sentiments)


if __name__ == "__main__":
    main()
