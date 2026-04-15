"""
streamlit_app.py — 뉴스 대시보드 UI
실행: streamlit run streamlit_app.py
"""

import streamlit as st
from news_langgraph import build_graph, NewsState
from database import SessionLocal, ProcessedNews

# ── 페이지 설정 ──
st.set_page_config(
    page_title="K-엔터 뉴스 브리핑",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');

* { font-family: 'Noto Sans KR', sans-serif; }

/* 전체 배경 */
.stApp { background-color: #f8f9fb; }

/* 제목 */
.news-title {
    font-size: 1.6rem;
    font-weight: 900;
    line-height: 1.4;
    color: #0d1117;
    margin-bottom: 4px;
}
.news-meta {
    font-size: 0.82rem;
    color: #888;
    margin-bottom: 20px;
}

/* 섹션 헤더 */
.section-label {
    font-size: 0.78rem;
    font-weight: 700;
    color: #555;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 10px;
    margin-top: 20px;
}

/* 핵심 요약 */
.summary-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 8px;
    font-size: 0.93rem;
    color: #1a1a2e;
    line-height: 1.6;
}
.summary-num {
    min-width: 22px;
    height: 22px;
    background: #0d1117;
    color: white;
    border-radius: 50%;
    font-size: 0.72rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 2px;
}

/* 브리핑 */
.briefing-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 10px;
    font-size: 0.92rem;
    color: #1a1a2e;
    line-height: 1.6;
}
.briefing-label {
    background: #e8f0fe;
    color: #1a56db;
    font-size: 0.75rem;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 20px;
    white-space: nowrap;
    margin-top: 2px;
}

/* 키워드 태그 */
.keyword-wrap { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.keyword-tag {
    background: #f0f0f0;
    color: #333;
    font-size: 0.82rem;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: 500;
}

/* 위젯 카드 */
.widget-card {
    background: white;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
}
.widget-title {
    font-size: 0.78rem;
    font-weight: 700;
    color: #888;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.dot-green  { width: 8px; height: 8px; background: #2ecc71; border-radius: 50%; display: inline-block; }
.dot-blue   { width: 8px; height: 8px; background: #3498db; border-radius: 50%; display: inline-block; }
.dot-purple { width: 8px; height: 8px; background: #9b59b6; border-radius: 50%; display: inline-block; }

/* So What 텍스트 */
.so-what-text {
    font-size: 0.95rem;
    color: #1a1a2e;
    line-height: 1.75;
    font-weight: 500;
}

/* 타임라인 */
.timeline-item {
    display: flex;
    gap: 12px;
    margin-bottom: 14px;
    align-items: flex-start;
}
.timeline-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-top: 5px;
    flex-shrink: 0;
}
.timeline-dot-active  { background: #2ecc71; }
.timeline-dot-neutral { background: #bbb; }
.timeline-date  { font-size: 0.78rem; color: #888; margin-bottom: 2px; }
.timeline-event { font-size: 0.88rem; font-weight: 600; color: #1a1a2e; }
.sentiment-badge {
    display: inline-block;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 10px;
    margin-top: 4px;
    font-weight: 600;
}
.badge-positive { background: #d4edda; color: #155724; }
.badge-negative { background: #f8d7da; color: #721c24; }
.badge-neutral  { background: #e2e3e5; color: #495057; }
.badge-current  { background: #cce5ff; color: #004085; }

/* RAG 카드 */
.rag-card {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    padding: 12px 0;
    border-bottom: 1px solid #f0f0f0;
}
.rag-card:last-child { border-bottom: none; }
.rag-score {
    min-width: 42px; height: 42px;
    border-radius: 8px;
    background: #f0f0f0;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.78rem; font-weight: 700; color: #333;
}
.rag-score-high { background: #d4edda; color: #155724; }
.rag-score-mid  { background: #fff3cd; color: #856404; }
.rag-score-low  { background: #e2e3e5; color: #495057; }
.rag-title { font-size: 0.88rem; font-weight: 600; color: #1a1a2e; margin-bottom: 3px; }
.rag-meta  { font-size: 0.75rem; color: #888; }
.rag-link  { font-size: 0.75rem; color: #1a56db; cursor: pointer; }

/* 구분선 */
.divider { border: none; border-top: 1px solid #eee; margin: 16px 0; }
</style>
""", unsafe_allow_html=True)


# ── DB에서 바로 읽어오기 ──
def load_from_db():
    session = SessionLocal()
    try:
        rows = (
            session.query(ProcessedNews)
            .filter(ProcessedNews.importance.isnot(None))
            .order_by(ProcessedNews.importance.desc())
            .limit(10)
            .all()
        )
        top_news_list = []
        for news in rows:
            top_news_list.append({
                "id": news.id,
                "title": news.raw.title if news.raw else "",
                "summary": news.summary or [],
                "keywords": news.keywords or [],
                "artist_tags": news.artist_tags or [],
                "importance": news.importance,
                "importance_reason": news.importance_reason or "",
                "sub_category": news.sub_category or "",
                "trend_insight": news.trend_insight or "",
                "source_name": news.source_name or "",
                "published_at": str(news.raw.published_at) if news.raw.published_at else "",
                "timeline": news.timeline or [],
            })
        return {
            "top_news_list": top_news_list,
            "related_news_map": {},
            "summaries_map": {},
            "report_text": "",
            "tts_output_path": "",
        }
    finally:
        session.close()


# ── 파이프라인 실행 (캐시) ──
@st.cache_resource(show_spinner="🔄 뉴스 파이프라인 실행 중...")
def run_pipeline():
    # trend_insight 이미 저장돼 있으면 파이프라인 스킵
    session = SessionLocal()
    try:
        already_done = (
            session.query(ProcessedNews)
            .filter(ProcessedNews.trend_insight.isnot(None))
            .count()
        )
    finally:
        session.close()

    if already_done > 0:
        return load_from_db()

    # 없으면 파이프라인 실행
    app = build_graph()
    initial_state: NewsState = {
        "top_news_list": [],
        "related_news_map": {},
        "summaries_map": {},
        "report_text": "",
        "tts_output_path": "",
    }
    return app.invoke(initial_state)


# ── 유사도 점수 변환 ──
def score_to_pct(score: float) -> int:
    return max(0, min(100, int((1 - score) * 100)))


def score_class(pct: int) -> str:
    if pct >= 85: return "rag-score-high"
    if pct >= 70: return "rag-score-mid"
    return "rag-score-low"


# ── 메인 ──
def main():
    st.markdown("## 📰 K-엔터 뉴스 브리핑")
    st.markdown("<hr class='divider'>", unsafe_allow_html=True)

    final_state   = run_pipeline()
    top_news_list = final_state["top_news_list"]
    related_map   = final_state["related_news_map"]

    if not top_news_list:
        st.error("뉴스 데이터가 없습니다. 파이프라인을 먼저 실행해 주세요.")
        return

    # 순위 선택
    rank_labels = [f"{i+1}위" for i in range(len(top_news_list))]
    selected_rank = st.radio(
        "뉴스 순위 선택",
        rank_labels,
        horizontal=True,
        label_visibility="collapsed",
    )
    idx = rank_labels.index(selected_rank)

    news    = top_news_list[idx]
    related = related_map.get(idx, [])
    so_what = news.get("trend_insight", "")

    st.markdown("<hr class='divider'>", unsafe_allow_html=True)

    # ── 2컬럼 레이아웃 ──
    left, right = st.columns([6, 4], gap="large")

    # ════════════════════════════════
    # 왼쪽: 뉴스 본문
    # ════════════════════════════════
    with left:
        st.markdown(f"<div class='news-title'>{news['title']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='news-meta'>{news['source_name']} · {news['published_at'][:10] if news['published_at'] else ''}</div>", unsafe_allow_html=True)

        # 핵심 요약
        st.markdown("<div class='section-label'>핵심 요약</div>", unsafe_allow_html=True)
        summary_html = ""
        for i, s in enumerate(news.get("summary", [])):
            summary_html += f"""
            <div class='summary-item'>
                <div class='summary-num'>{i+1}</div>
                <div>{s}</div>
            </div>"""
        st.markdown(summary_html, unsafe_allow_html=True)

       # 3줄 브리핑
        #st.markdown("<div class='section-label'>3줄 브리핑</div>", unsafe_allow_html=True)
        #briefing_html = ""
        #for b in news.get("briefing", []):
        #    label   = b.get("label", "")
        #    content = b.get("content", "")
        #    briefing_html += f"""
        #    <div class='briefing-row'>
        #        <span class='briefing-label'>{label}</span>
        #        <span>{content}</span>
        #    </div>"""
        #st.markdown(briefing_html, unsafe_allow_html=True)

        # 키워드
        st.markdown("<div class='section-label'>키워드</div>", unsafe_allow_html=True)
        kw_html = "<div class='keyword-wrap'>"
        for kw in news.get("keywords", []):
            kw_html += f"<span class='keyword-tag'>{kw}</span>"
        kw_html += "</div>"
        st.markdown(kw_html, unsafe_allow_html=True)

    # ════════════════════════════════
    # 오른쪽: 위젯 3개
    # ════════════════════════════════
    with right:

        # ── 위젯 1: So What? (비즈니스 시사평) ──
        st.markdown(f"""
        <div class='widget-card'>
            <div class='widget-title'>
                <span class='dot-green'></span>
                위젯 1 · 비즈니스 시사평 (So What?)
            </div>
            <div class='so-what-text'>{so_what}</div>
        </div>
        """, unsafe_allow_html=True)

        # ── 위젯 2: 6개월 타임라인 ──
        timeline = news.get("timeline", [])
        timeline_html = f"""
        <div class='widget-card'>
            <div class='widget-title'>
                <span class='dot-blue'></span>
                위젯 2 · {news['artist_tags'][0] if news.get('artist_tags') else ''} 6개월 타임라인
            </div>"""
        for i, item in enumerate(timeline):
            is_last   = (i == len(timeline) - 1)
            dot_class = "timeline-dot-active" if is_last else "timeline-dot-neutral"
            badge_cls = "badge-current" if is_last else "badge-neutral"
            badge_txt = "긍정·현재" if is_last else "중립"
            timeline_html += f"""
            <div class='timeline-item'>
                <div class='timeline-dot {dot_class}'></div>
                <div>
                    <div class='timeline-date'>{item.get('date', '')}</div>
                    <div class='timeline-event'>{item.get('event', '')}</div>
                    <span class='sentiment-badge {badge_cls}'>{badge_txt}</span>
                </div>
            </div>"""
        timeline_html += "</div>"
        st.markdown(timeline_html, unsafe_allow_html=True)

        # ── 위젯 3: 과거 유사 사례 RAG ──
        rag_html = """
        <div class='widget-card'>
            <div class='widget-title'>
                <span class='dot-purple'></span>
                위젯 3 · 과거 유사 사례 RAG
            </div>"""
        for r in related:
            meta    = r.get("metadata", {})
            score   = r.get("score", 1.0)
            pct     = score_to_pct(score)
            s_class = score_class(pct)
            title   = meta.get("title") or r["content"][:60]
            artist  = meta.get("artist_name", "")
            cat     = meta.get("category", "")
            pub     = (meta.get("published_at") or "")[:7]
            rag_html += f"""
            <div class='rag-card'>
                <div class='rag-score {s_class}'>{pct}%</div>
                <div>
                    <div class='rag-title'>{title}</div>
                    <div class='rag-meta'>{cat} · {artist} · {pub}</div>
                </div>
            </div>"""
        rag_html += "</div>"
        st.markdown(rag_html, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
