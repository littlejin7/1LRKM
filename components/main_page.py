"""
components/main_page.py — 대시보드 메인 컴포넌트 (수묵화 스타일)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import io
from datetime import datetime

import edge_tts
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from categories import accent_color_for_row, resolve_row_categories

SENT_LABEL = {"positive": "긍정", "neutral": "중립", "negative": "부정"}
TITLE_IMG = Path(__file__).resolve().parent / "assets" / "title.png"

# ── TTS ──────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def tts_to_bytes(text: str) -> bytes:
    async def _gen():
        communicate = edge_tts.Communicate(
            text=text, voice="ko-KR-SunHiNeural", rate="+50%",
        )
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()
    return asyncio.run(_gen())


# ── 유틸 헬퍼 ────────────────────────────────────────────────────────────────

def _thumb_html(url: str, featured: bool = False) -> str:
    cls = "featured-thumb" if featured else "news-thumb"
    fallback = "https://via.placeholder.com/640x360?text=No+Image"
    src = url.strip() if url else fallback
    return f'<img class="{cls}" src="{src}" alt="thumbnail" onerror="this.src=\'{fallback}\'" />'


def _badge(sentiment: str) -> str:
    if sentiment == "positive":
        return '<span class="badge-pos">● 긍정</span>'
    if sentiment == "negative":
        return '<span class="badge-neg">● 부정</span>'
    return '<span class="badge-neu">● 중립</span>'


def _cat_badge(item: dict) -> str:
    _, sub = resolve_row_categories(item)
    color = accent_color_for_row(item)
    return (
        f'<span style="background:{color}18;color:{color};border:1px solid {color}55;'
        f'padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;">{sub}</span>'
    )


def _change_badge(score: float) -> str:
    if score >= 0.8:
        return '<span class="change-up">↑</span>'
    if score <= 0.3:
        return '<span class="change-down">↓</span>'
    return '<span class="change-same">→</span>'


# ── 필터 ─────────────────────────────────────────────────────────────────────

def _match(item: dict, keyword: str, major: str, sub: str, sentiments: list[str]) -> bool:
    item_major, item_sub = resolve_row_categories(item)
    if major != "전체" and item_major != major:
        return False
    if sub != "전체" and item_sub != sub:
        return False
    item_sent_ko = SENT_LABEL.get(item.get("sentiment", "neutral"), "중립")
    if sentiments and item_sent_ko not in sentiments:
        return False
    if keyword.strip():
        q = keyword.lower()
        pool = " ".join([
            item.get("title", ""),
            item.get("source_name", ""),
            item.get("artist_name", ""),
            " ".join(map(str, item.get("artist_tags", []))),
            " ".join(map(str, item.get("keywords", []))),
        ]).lower()
        return q in pool
    return True


# ── 헤더 ─────────────────────────────────────────────────────────────────────

def render_header():
    today = datetime.now().strftime("%Y년 %m월 %d일")
    
    # 날짜 오른쪽 정렬
    st.markdown(
        f'<div style="text-align:right;"><span class="date-badge">📅 {today}</span></div>',
        unsafe_allow_html=True
    )
    
    # 이미지 가운데 정렬
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.image(str(TITLE_IMG), use_container_width=True)  # 크기 크게
    
    st.markdown('<hr style="border:none;border-top:2px solid #2c1810;margin:8px 0 12px;">', unsafe_allow_html=True)

# ── 메트릭 카드 ───────────────────────────────────────────────────────────────

def render_metrics(processed: list, past: list):
    total = len(processed) + len(past)
    pos_count = sum(1 for x in processed if x.get("sentiment") == "positive")
    neg_count = sum(1 for x in processed if x.get("sentiment") == "negative")
    pos_pct = f"{round(pos_count / len(processed) * 100)}%" if processed else "0%"

    top_artist = "-"
    if processed:
        top = max(processed, key=lambda x: float(x.get("sentiment_score", 0)))
        tags = top.get("artist_tags", [])
        top_artist = tags[0] if tags else top.get("title", "-")[:6]

    m1, m2, m3, m4 = st.columns(4)
    metrics = [
        ("📰 오늘 뉴스",   f"{total}건",     f"최신 {len(processed)}건", "#155724"),
        ("🟢 긍정 기사",   pos_pct,          f"+{pos_count}건 ↑",        "#155724"),
        ("🔴 부정 급등",   f"{neg_count}건", f"+{neg_count} ↑",          "#721c24"),
        ("🔥 핫 키워드", top_artist,       "1위",                       "#856404"),
    ]
    for col, (label, val, delta, dcolor) in zip([m1, m2, m3, m4], metrics):
        with col:
            st.markdown(f"""
            <div class="metric-card">
              <div class="metric-label">{label}</div>
              <div class="metric-value">{val}</div>
              <div class="metric-delta" style="color:{dcolor}">{delta}</div>
            </div>""", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)


# ── 오늘의 랭킹 ───────────────────────────────────────────────────────────────

def render_ranking(filtered: list):
    if not filtered:
        st.markdown('<div style="color:#8b7355;text-align:center;padding:40px;">조건에 맞는 기사가 없습니다.</div>', unsafe_allow_html=True)
        return

    title_col, btn_col = st.columns([4, 1])
    with title_col:
        st.markdown('<div class="section-title">🏆 오늘의 랭킹</div>', unsafe_allow_html=True)
    with btn_col:
        briefing_click = st.button('🎙️ 오늘의 뉴스 브리핑 듣기', use_container_width=True)

    featured = filtered[0]
    tags = featured.get("artist_tags", [])
    artist_name = tags[0] if tags else featured.get("source_name", "-")
    summary = featured.get("summary", "")
    summary_text = summary[0] if isinstance(summary, list) and summary else (summary or "")
    score = float(featured.get("sentiment_score", 0))
    score_display = f"{score * 100:.0f}점" if score <= 1.0 else f"{score:.0f}점"

    if briefing_click:
        top5 = filtered[:5]
        script = '안녕하세요, 오늘의 K엔터 뉴스 브리핑입니다. '
        for i, item in enumerate(top5, 1):
            tags = item.get('artist_tags', [])
            artist = tags[0] if tags else ''
            tts_text = item.get('tts_text', '')
            summary = item.get('summary', '')
            text = tts_text or (summary[0] if isinstance(summary, list) and summary else summary or '')
            script += f'{i}위 뉴스입니다. {artist} {text[:100]} '
        with st.spinner('음성 생성 중...'):
            audio = tts_to_bytes(script[:1000])
            st.audio(audio, format='audio/mp3', autoplay=True)

    left, right = st.columns([1, 2])

    # ── 1위 featured 카드 ────────────────────────────
    with left:
        with st.container(border=True):
            st.markdown(f"""
            <div>
              {_thumb_html(featured.get("thumbnail_url", ""), featured=True)}
              <div class="featured-rank">01</div>
              <div style="margin:8px 0 4px;display:flex;align-items:center;gap:8px;">
                {_badge(featured.get("sentiment","neutral"))}
                <span style="font-size:11px;color:#8b7355;">기사 1건</span>
              </div>
              <div class="featured-artist">{artist_name}</div>
              <div class="featured-headline">{featured.get("title","")[:35]}</div>
              <div class="featured-summary">{summary_text[:120]}</div>
              <div style="margin-top:16px;padding-top:12px;border-top:1px solid #d4c4a8;">
                <span style="font-size:12px;color:#8b7355;">감성 스코어</span>
                <span style="font-size:22px;font-weight:900;color:#155724;
                    margin-left:8px;font-family:'Noto Serif KR',serif;">{score_display}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

        
            if st.button("📄 상세보기", key=f"detail_1_{featured['id']}", use_container_width=True):
                st.session_state["detail_id"] = featured["id"]
                st.switch_page("pages/dashboard.py")


    # ── 2위~10위 랭킹 카드 그리드 ────────────────────
    with right:
        rest = filtered[1:10]
        col_a, col_b = st.columns(2)

        for i, item in enumerate(rest):
            rank = i + 2
            rank_cls = "top3" if rank <= 3 else ""
            item_tags = item.get("artist_tags", [])
            item_artist = item_tags[0] if item_tags else item.get("source_name", "-")
            item_summary = item.get("summary", "")
            item_summary_text = item_summary[0] if isinstance(item_summary, list) and item_summary else (item_summary or "")
            item_score = float(item.get("sentiment_score", 0))
            item_score_display = f"{item_score * 100:.0f}" if item_score <= 1.0 else f"{item_score:.0f}"
            change_html = _change_badge(item_score)

            col = col_a if i % 2 == 0 else col_b
            with col:
                with st.container(border=True):
                    st.markdown(f"""
                    <div>
                      {_thumb_html(item.get("thumbnail_url", ""))}
                      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
                        <span class="rank-num {rank_cls}">{str(rank).zfill(2)}</span>
                        <div style="flex:1;min-width:0;">
                          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                            <span class="artist-name">{item_artist}</span>
                            {change_html}
                          </div>
                          <div class="headline">{item.get("title","")[:30]}</div>
                        </div>
                      </div>
                      <div class="summary-text">{item_summary_text[:70]}</div>
                      <div style="display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap;">
                        {_badge(item.get("sentiment","neutral"))}
                        <span style="font-size:11px;color:#8b7355;">기사 1건</span>
                        <span style="font-size:11px;color:#8b4513;margin-left:auto;font-weight:700;">
                          {item_score_display}점
                        </span>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                
                    if st.button("📄 상세보기", key=f"detail_{rank}_{item['id']}", use_container_width=True):
                       st.session_state["detail_id"] = item["id"]
                       st.switch_page("pages/dashboard.py")



# ── 감성 추이 차트 ────────────────────────────────────────────────────────────

def render_sentiment_chart(processed: list):
    st.markdown('<div class="section-title">📊 오늘의 감성 추이</div>', unsafe_allow_html=True)

    pos = sum(1 for x in processed if x.get("sentiment") == "positive")
    neg = sum(1 for x in processed if x.get("sentiment") == "negative")
    neu = sum(1 for x in processed if x.get("sentiment") == "neutral")

    sub_count: dict[str, int] = {}
    for item in processed:
        _, sub = resolve_row_categories(item)
        sub_count[sub] = sub_count.get(sub, 0) + 1

    col1, col2 = st.columns([1, 2])

    with col1:
        fig_pie = go.Figure(data=[go.Pie(
            labels=["긍정", "부정", "중립"],
            values=[pos, neg, neu],
            hole=0.55,
            marker=dict(colors=["#6aaa6a", "#cc6666", "#6699cc"]),
        )])
        fig_pie.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#5c4a3a", family="Noto Sans KR"),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#5c4a3a")),
            margin=dict(l=10, r=10, t=10, b=10),
            height=220,
        )
        fig_pie.update_traces(textinfo="percent", textfont_size=13)
        st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        if sub_count:
            df = pd.DataFrame([
                {"카테고리": k, "기사수": v}
                for k, v in sorted(sub_count.items(), key=lambda x: -x[1])
            ])
            fig_bar = go.Figure(go.Bar(
                x=df["기사수"],
                y=df["카테고리"],
                orientation="h",
                marker_color="#8b4513",
                marker_opacity=0.75,
            ))
            fig_bar.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#5c4a3a", family="Noto Sans KR"),
                xaxis=dict(gridcolor="#d4c4a8", color="#5c4a3a"),
                yaxis=dict(gridcolor="#d4c4a8", color="#5c4a3a"),
                margin=dict(l=10, r=10, t=10, b=10),
                height=220,
            )
            st.plotly_chart(fig_bar, use_container_width=True)


# ── 과거 기사 ─────────────────────────────────────────────────────────────────

def render_past(filtered_past: list):
    if not filtered_past:
        return
    st.markdown('<div class="section-title">🗂️ 연관 과거 기사</div>', unsafe_allow_html=True)
    cols_p = st.columns(2)
    for i, item in enumerate(filtered_past[:10]):
        summary = item.get("summary", "")
        with cols_p[i % 2]:
            st.markdown(f"""
            <div class="news-card">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
                {_badge(item.get("sentiment","neutral"))}
                {_cat_badge(item)}
              </div>
              <div class="artist-name">{item.get("artist_name") or "-"}</div>
              <div class="headline">{item.get("title","")[:40]}</div>
              <div class="summary-text">{(summary or "")[:80]}</div>
              <div style="display:flex;gap:8px;margin-top:6px;font-size:11px;color:#8b7355;">
                <span>📰 {item.get("source_name","-")}</span>
                <span>📅 {item.get("published_at","-")}</span>
                <span style="margin-left:auto;color:#8b4513;font-weight:700;">
                    관련도 {float(item.get("relevance_score",0)):.2f}
                </span>
              </div>
            </div>
            """, unsafe_allow_html=True)


# ── 메인 대시보드 ─────────────────────────────────────────────────────────────

def render_dashboard(
    processed: list,
    past: list,
    keyword: str,
    major: str,
    sub: str,
    sentiments: list[str],
):
    render_header()
    render_metrics(processed, past)

    filtered_processed = [x for x in processed if _match(x, keyword, major, sub, sentiments)]
    filtered_past      = [x for x in past      if _match(x, keyword, major, sub, sentiments)]

    render_ranking(filtered_processed)
    render_sentiment_chart(processed)
    render_past(filtered_past)