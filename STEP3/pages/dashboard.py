import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from components.styles import apply_styles
from components.news.widget1 import render as render_so_what
from components.news.widget2 import render as render_timeline
from components.news.widget3 import render as render_related, score_to_pct
from components.news.news_main import render as render_body
from components.news.news_nav import render as render_navigator
from components.news.news_pip import run_pipeline

apply_styles()

# ── 페이지 설정 ──
st.set_page_config(
    page_title="K-엔터 뉴스 브리핑",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown("""
<style>
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ── CSS ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');

* { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background-color: #f8f9fb; }

.news-title {
    font-size: 1.6rem; font-weight: 900;
    line-height: 1.4; color: #0d1117; margin-bottom: 4px;`
}
.news-meta { font-size: 0.82rem; color: #888; margin-bottom: 20px; }
.section-label {
    font-size: 0.78rem; font-weight: 700; color: #555;
    letter-spacing: 0.05em; text-transform: uppercase;
    margin-bottom: 10px; margin-top: 20px;
}
.keyword-wrap { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.keyword-tag {
    background: #FFB3B3; color: #333; font-size: 0.82rem;
    padding: 4px 12px; border-radius: 20px; font-weight: 500;
}
.widget-card {
    background: white; border-radius: 12px; padding: 18px;
    margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.07);
}
.widget-title {
    font-size: 0.78rem; font-weight: 700; color: #888;
    margin-bottom: 12px; display: flex; align-items: center; gap: 6px;
}
.dot-green  { width:8px; height:8px; background:#2ecc71; border-radius:50%; display:inline-block; }
.dot-blue   { width:8px; height:8px; background:#3498db; border-radius:50%; display:inline-block; }
.dot-purple { width:8px; height:8px; background:#9b59b6; border-radius:50%; display:inline-block; }
.so-what-text { font-size:0.95rem; color:#1a1a2e; line-height:1.75; font-weight:500; }
.timeline-item {
    display:flex; gap:12px; margin-bottom:14px;
    align-items:flex-start; position:relative;
}
.timeline-item::before {
    content:''; position:absolute; left:4px; top:14px;
    width:2px; height:calc(100% + 14px); background:#e0e0e0;
}
.timeline-item:last-child::before { display:none; }
.timeline-wrap { position:relative; padding-left:4px; }
.timeline-dot { width:10px; height:10px; border-radius:50%; margin-top:5px; flex-shrink:0; }
.timeline-dot-active   { background:#2ecc71; }
.timeline-dot-neutral  { background:#bbb; }
.timeline-dot-negative { background:#e74c3c; }
.timeline-date  { font-size:0.78rem; color:#888; margin-bottom:2px; }
.timeline-event { font-size:0.88rem; font-weight:600; color:#1a1a2e; }
.sentiment-badge {
    display:inline-block; font-size:0.7rem; padding:2px 8px;
    border-radius:10px; margin-top:4px; font-weight:600;
}
.badge-current  { background:#cce5ff; color:#004085; }
.badge-neutral  { background:#e2e3e5; color:#495057; }
.badge-negative { background:#f8d7da; color:#721c24; }
.rag-card {
    display:flex; gap:12px; align-items:flex-start;
    padding:12px 0; border-bottom:1px solid #f0f0f0;
}
.rag-card:last-child { border-bottom:none; }
.rag-score {
    min-width:42px; height:42px; border-radius:8px;
    display:flex; align-items:center; justify-content:center;
    font-size:0.78rem; font-weight:700;
}
.rag-score-high { background:#d4edda; color:#155724; }
.rag-score-mid  { background:#fff3cd; color:#856404; }
.rag-score-low  { background:#e2e3e5; color:#495057; }
.rag-title { font-size:0.88rem; font-weight:600; color:#1a1a2e; margin-bottom:3px; }
.rag-meta  { font-size:0.75rem; color:#888; }
.divider   { border:none; border-top:1px solid #eee; margin:16px 0; }
</style>
""", unsafe_allow_html=True)


def main():
    if st.button("← 대시보드로 돌아가기"):
        st.switch_page("run.py")

    st.markdown("## 📰 K-엔터 뉴스 브리핑")
    st.markdown("<hr class='divider'>", unsafe_allow_html=True)

    final_state = run_pipeline()
    top_news_list = final_state["top_news_list"]
    related_map = final_state["related_news_map"]

    if not top_news_list:
        st.error("뉴스 데이터가 없습니다.")
        return

    # idx 계산
    idx = 0
    if "detail_id" in st.session_state:
        target_id = st.session_state["detail_id"]
        for j, item in enumerate(top_news_list):
            if item["id"] == target_id:
                idx = j
                break

    news = top_news_list[idx]

    render_navigator(idx, top_news_list)
    st.markdown("<hr class='divider'>", unsafe_allow_html=True)

    left, right = st.columns([6, 4], gap="large")

    with left:
        render_body(news)

    with right:
        render_so_what(news.get("trend_insight", ""))
        render_timeline(
            timeline=news.get("timeline", []),
            artist_tags=news.get("artist_tags", []),
        )
        related = [
            r for r in related_map.get(idx, [])
            if 30 <= score_to_pct(r["score"]) <= 75
        ][:3]
        render_related(related)

if __name__ == "__main__":
    main()
