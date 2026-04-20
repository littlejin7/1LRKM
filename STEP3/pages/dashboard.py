

import sqlite3
import json
import streamlit as st
from rag_search import build_graph, NewsState
from database import SessionLocal, ProcessedNews
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from components.styles import apply_styles

apply_styles()

# ── 페이지 설정 ──
st.set_page_config(
    page_title="K-엔터 뉴스 브리핑",
    layout="wide",
    initial_sidebar_state="collapsed",
)
# 사이드바x
st.markdown(
    """
<style>
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ── CSS ──
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');

* { font-family: 'Noto Sans KR', sans-serif; }

.stApp { background-color: #f8f9fb; }

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
.section-label {
    font-size: 0.78rem;
    font-weight: 700;
    color: #555;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 10px;
    margin-top: 20px;
}

/* 요약 카드 (label + content) */
# 비율고정#
.summary-row {
    display: grid;
    grid-template-columns: 2fr 8fr;
    gap: 10px;
    margin-bottom: 10px;
    font-size: 0.92rem;
    color: #1a1a2e;
    line-height: 1.6;
    align-items: start;
}
.summary-label {
    background: #e8f0fe;
    color: #1a56db;
    font-size: 0.75rem;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 20px;
    font-weight: 700;
    word-break: keep-all;
    text-align: center;
    line-height: 1.5;
}

/* 키워드 태그 */
.keyword-wrap { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.keyword-tag {
    background: #FFB3B3;
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
    position: relative;  /* 추가 */
}
.timeline-item::before {
    content: '';
    position: absolute;
    left: 4px;
    top: 14px;
    width: 2px;
    height: calc(100% + 14px);
    background: #e0e0e0;
}
.timeline-item:last-child::before {
    display: none;
}
.timeline-wrap {
    position: relative;
    padding-left: 4px;
}
.timeline-dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
.timeline-dot-active  { background: #2ecc71; }
.timeline-dot-neutral { background: #bbb; }
.timeline-dot-negative { background: #e74c3c; }
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
.badge-current { background: #cce5ff; color: #004085; }
.badge-neutral { background: #e2e3e5; color: #495057; }
.badge-negative { background: #f8d7da; color: #721c24; }

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
    display: flex; align-items: center; justify-content: center;
    font-size: 0.78rem; font-weight: 700;
}
.rag-score-high { background: #d4edda; color: #155724; }
.rag-score-mid  { background: #fff3cd; color: #856404; }
.rag-score-low  { background: #e2e3e5; color: #495057; }
.rag-title { font-size: 0.88rem; font-weight: 600; color: #1a1a2e; margin-bottom: 3px; }
.rag-meta  { font-size: 0.75rem; color: #888; }

.divider { border: none; border-top: 1px solid #eee; margin: 16px 0; }
</style>
""",
    unsafe_allow_html=True,
)


# ── JSON 파싱 헬퍼 ──
def parse_json(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except Exception:
        return []


# ── DB에서 바로 읽어오기 ──
def load_from_db():
    from vectorstore import get_stores

    conn = sqlite3.connect("k_enter_news.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    category_limits = {
        "컨텐츠 & 작품": 5,
        "인물 & 아티스트": 3,
        "비즈니스 & 행사": 2,
    }

    # 중복 방지를 위해 넉넉하게 가져옴
    temp_rows = []
    for category, limit in category_limits.items():
        cursor.execute(
            """
            SELECT p.id, p.raw_news_id, p.category, p.sub_category,
                p.summary, p.summary_en, p.keywords, p.artist_tags,
                p.sentiment, p.importance, p.importance_reason,
                p.trend_insight, p.timeline, p.source_name,
                p.url, p.published_at, p.ko_title, p.thumbnail_url
            FROM processed_news p
            WHERE p.importance IS NOT NULL
            AND p.category = ?
            ORDER BY p.importance DESC, p.id DESC
            LIMIT 20
        """,
            (category,),
        )
        temp_rows.extend(cursor.fetchall())

    # 중요도 순으로 정렬
    temp_rows = sorted(temp_rows, key=lambda x: x["importance"], reverse=True)
    conn.close()

    top_news_list = []
    seen_artists = set()
    
    # 카테고리별로 현재 몇 개 뽑았는지 카운트
    cat_counts = {cat: 0 for cat in category_limits.keys()}

    for row in temp_rows:
        cat = row["category"]
        if cat_counts[cat] >= category_limits.get(cat, 0):
            continue
            
        tags = parse_json(row["artist_tags"])
        artist = tags[0].strip().lower() if tags else None
        
        # 중복 아티스트 체크 (이름이 있거나 K-Enter가 아닐 때만)
        if artist and artist != "k-enter":
            if artist in seen_artists:
                continue
            seen_artists.add(artist)

        # 뉴스 리스트에 추가
        top_news_list.append({
            "id": row["id"],
            "title": row["ko_title"] or "",
            "summary": parse_json(row["summary"]),
            "summary_en": parse_json(row["summary_en"]),
            "keywords": parse_json(row["keywords"]),
            "artist_tags": tags,
            "importance": row["importance"],
            "importance_reason": row["importance_reason"] or "",
            "sub_category": row["sub_category"] or "",
            "category": cat,
            "sentiment": row["sentiment"] or "neutral",
            "trend_insight": row["trend_insight"] or "",
            "source_name": row["source_name"] or "",
            "published_at": str(row["published_at"]) if row["published_at"] else "",
            "timeline": parse_json(row["timeline"]),
            "thumbnail_url": row["thumbnail_url"] or "",
        })
        cat_counts[cat] += 1
        
        # 총 10개 차면 중단 (혹시 모르니)
        if len(top_news_list) >= sum(category_limits.values()):
            break

    # ChromaDB에서 관련 과거뉴스 검색
    _, past_store = get_stores()
    related_news_map = {}
    for i, news in enumerate(top_news_list):
        query_text = news["title"] + " " + " ".join(news["keywords"])
        results = past_store.similarity_search_with_score(query_text, k=3)
        related_news_map[i] = [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
            }
            for doc, score in results
        ]

    return {
        "top_news_list": top_news_list,
        "related_news_map": related_news_map,
        "summaries_map": {},
        "report_text": "",
        "tts_output_path": "",
    }


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
        # 🚨🚨tts영어
        # "en_tts_output_path": ""
    }
    return app.invoke(initial_state)


# ── 유사도 점수 변환 ──
def score_to_pct(score: float) -> int:
    return max(0, min(100, int((1 - score) * 100)))


def score_class(pct: int) -> str:
    if pct >= 85:
        return "rag-score-high"
    if pct >= 70:
        return "rag-score-mid"
    return "rag-score-low"


# ── 메인 ──


def main():
    # ✅ 뒤로가기 버튼 추가
    if st.button("← 대시보드로 돌아가기"):
        st.switch_page("app.py")

    st.markdown("## 📰 K-엔터 뉴스 브리핑")
    st.markdown("<hr class='divider'>", unsafe_allow_html=True)

    final_state = run_pipeline()
    top_news_list = final_state["top_news_list"]
    related_map = final_state["related_news_map"]

    if not top_news_list:
        st.error("뉴스 데이터가 없습니다.")
        return

## 1개만 표시 되게
    idx = 0
    if "detail_id" in st.session_state:
     target_id = st.session_state["detail_id"]
     for j, news_item in enumerate(top_news_list):
            if news_item["id"] == target_id:
              idx = j
              break

    news = top_news_list[idx]

## 맘에 안들면 삭제 ## 이전 다음 버튼

    col1, col2, col3 = st.columns([1, 4, 1])
    with col1:
        if idx > 0:
            if st.button("◀ 이전"):
                st.session_state["detail_id"] = top_news_list[idx - 1]["id"]
                st.rerun()
    with col2:
                st.markdown(f"<div style='text-align:center;font-weight:700;'>{idx+1}위 / {len(top_news_list)}위</div>", unsafe_allow_html=True)
    with col3:
        if idx < len(top_news_list) - 1:
            if st.button("다음 ▶"):
                st.session_state["detail_id"] = top_news_list[idx + 1]["id"]
                st.rerun()
    so_what = news.get("trend_insight", "")

    # 85% 이상 유사도 필터링
    related = [r for r in related_map.get(idx, []) if score_to_pct(r["score"]) >= 85]

    st.markdown("<hr class='divider'>", unsafe_allow_html=True)

    left, right = st.columns([6, 4], gap="large")

    # ════════════════════════════════
    # 왼쪽: 뉴스 본문
    # ════════════════════════════════
    with left:
        # 제목 + 메타
        st.markdown(
            f"<div class='news-title'>{news['title']}</div>", unsafe_allow_html=True
        )
        st.markdown(
            f"<div class='news-meta'>{news['source_name']} · "
            f"{news['published_at'][:10] if news['published_at'] else ''}</div>",
            unsafe_allow_html=True,
        )

        # 요약 카드 (label + content)
        st.markdown(
            "<div class='section-label'>요약 카드 (SUMMARY)</div>",
            unsafe_allow_html=True,
        )
        summary_html = ""
        for item in news.get("summary", []):
            if isinstance(item, dict):
                label = item.get("label", "")
                content = item.get("content", "")
            else:
                label, content = "", str(item)
            summary_html += f"""
            <div class='summary-row'>
                <span class='summary-label'>{label}</span>
                <span>{content}</span>
            </div>"""
        st.markdown(summary_html, unsafe_allow_html=True)

        # 요약 카드 (ENGLISH)
        st.markdown(
            "<div class='section-label'>요약 카드 (ENGLISH)</div>",
            unsafe_allow_html=True,
        )
        summary_en_html = ""
        for item in news.get("summary_en", []):
            if isinstance(item, dict):
                label = item.get("label", "")
                content = item.get("content", "")
            else:
                label, content = "", str(item)
            summary_en_html += f"""
            <div class='summary-row'>
                <span class='summary-label'>{label}</span>
                <span>{content}</span>
            </div>"""
        st.markdown(summary_en_html, unsafe_allow_html=True)

        # 키워드
        st.markdown("<div class='section-label'>키워드</div>", unsafe_allow_html=True)
        kw_html = "<div class='keyword-wrap'>"
        for kw in news.get("keywords", []):
            kw_html += f"<span class='keyword-tag'>{kw}</span>"
        kw_html += "</div>"
        st.markdown(kw_html, unsafe_allow_html=True)

    # ════════════════════════════════
    # 오른쪽: 위젯
    # ════════════════════════════════
    with right:

        # ── 위젯 1: So What? ──
        st.markdown(
            f"""
        <div class='widget-card'>
            <div class='widget-title'>
                <span class='dot-green'></span>
                위젯 1 · SO WHAT? 비즈니스 시사평
            </div>
            <div class='so-what-text'>{so_what}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # ── 위젯 2: 타임라인 ──
        # TODO: processed_news에 timeline 데이터 추가되면 빈 공백 자동으로 채워질 것

        timeline = news.get("timeline", [])
        tags = parse_json(news.get("artist_tags", []))
        artist_name = tags[0] if tags else ""
        timeline_html = f"""
        <div class='widget-card'>
            <div class='widget-title'>
                <span class='dot-blue'></span>
                위젯 2 · 연관 기사 타임라인
            </div>
            <div class='timeline-wrap'>"""
        for i, item in enumerate(timeline):
            is_last = (i == 0)

            sentiment = item.get("sentiment", "neutral")

            if sentiment == "positive":
                dot_class = "timeline-dot-active"
            elif sentiment == "negative":
                dot_class = "timeline-dot-negative"
            else:
                dot_class = "timeline-dot-neutral"

            if sentiment == "positive":
                badge_cls = "badge-current"
                badge_txt = "긍정"
            elif sentiment == "negative":
                badge_cls = "badge-negative"
                badge_txt = "부정"
            else:
                badge_cls = "badge-neutral"
                badge_txt = "중립"

            if is_last:
                badge_txt += "·현재"

            timeline_html += f"""
            <div class='timeline-item'>
                <div class='timeline-dot {dot_class}'></div>
                <div>
                    <div class='timeline-date'>{item.get('date', '')}</div>
                    <div class='timeline-event'>{item.get('event', '')}</div>
                    <span class='sentiment-badge {badge_cls}'>{badge_txt}</span>
                </div>
            </div>"""
        timeline_html += "</div></div>"
        st.markdown(timeline_html, unsafe_allow_html=True)

        # ── 위젯 3: 과거 유사 사례 (85% 이상만) ──
        rag_html = """
<div class='widget-card'>
    <div class='widget-title'>
        <span class='dot-purple'></span>
        위젯 3 · 과거 유사 사례
    </div>"""
        if related:
            for r in related:
                meta = r.get("metadata", {})
                score = r.get("score", 1.0)
                pct = score_to_pct(score)
                s_class = score_class(pct)
                title = meta.get("title") or r["content"][:60]
                cat = meta.get("sub_category", "")
                artist_list = meta.get("artist_tags", [])
                # 만약 리스트가 아니라 문자열(JSON)로 저장되어 있을 경우를 대비
                if isinstance(artist_list, str):
                    try:
                        artist_list = json.loads(artist_list)
                    except:
                        artist_list = [artist_list]
                artist = artist_list[0] if artist_list else ""
                rag_html += f"""
                <div class='rag-card'>
                    <div class='rag-score {s_class}'>{pct}%</div>
                    <div>
                        <div class='rag-title'>{title}</div>
                        <div class='rag-meta'>{cat} · {artist} · past_news rel={pct/100:.2f}</div>
                    </div>
                </div>"""
        else:
            rag_html += "<div style='font-size:0.88rem; color:#888; padding: 8px 0;'>유사도 85% 이상 기사가 없습니다.</div>"
        rag_html += "</div>"
        st.markdown(rag_html, unsafe_allow_html=True)


if __name__ == "__main__":
    main()