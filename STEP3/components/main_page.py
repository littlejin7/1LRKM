import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import base64

# -- 보고서
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from categories import accent_color_for_row, resolve_row_categories

SENT_LABEL = {
    "positive": "긍정",
    "neutral": "중립",
    "negative": "부정",
    "긍정": "긍정",
    "중립": "중립",
    "부정": "부정",
}
TITLE_IMG = Path(__file__).resolve().parent / "assets" / "title.png"
LOGOS_IMG = Path(__file__).resolve().parent / "assets" / "mag.png"

# ── 유틸 헬퍼 ────────────────────────────────────────────────────────────────
def _safe_tags(val) -> list:
    if not val: return []
    if isinstance(val, list): return val
    if isinstance(val, str):
        try:
            import json
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except: return [val]
    return [str(val)]

def _thumb_html(url: str, featured: bool = False) -> str:
    cls = "featured-thumb" if featured else "news-thumb"
    fallback = "https://via.placeholder.com/640x360?text=No+Image"
    src = url.strip() if url else fallback
    return f'<img class="{cls}" src="{src}" alt="thumbnail" referrerpolicy="no-referrer" onerror="this.src=\'{fallback}\'" />'


def _badge(sentiment: str) -> str:
    if sentiment in ["positive", "긍정"]:
        return '<span class="badge-pos">● 긍정</span>'
    if sentiment in ["negative", "부정"]:
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


def _match(
    item: dict, keyword: str, category: str, sub_category: str, sentiments: list[str]
) -> bool:
    item_major, item_sub = resolve_row_categories(item)
    if category != "전체" and item_major != category:
        return False
    if sub_category != "전체" and item_sub != sub_category:
        return False
    item_sent_ko = SENT_LABEL.get(item.get("sentiment", "neutral"), "중립")
    if sentiments and item_sent_ko not in sentiments:
        return False
    if keyword.strip():
        q = keyword.lower()
        pool = " ".join(
            [
                item.get("title", ""),
                item.get("source_name", ""),
                " ".join(map(str, _safe_tags(item.get("artist_tags", [])))),
                " ".join(map(str, item.get("keywords", []))),
            ]
        ).lower()
        return q in pool
    return True


# ── 헤더 ─────────────────────────────────────────────────────────────────────

def get_base64_image(image_path):
    with open(image_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()
####여기서부터 #####
def render_header():
    img_base64 = get_base64_image(TITLE_IMG)
    
    st.markdown(f"""
        <style>
            .fixed-header {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                z-index: 9999;
                height: 160px;
                background-image: url("data:image/png;base64,{img_base64}");
                background-size: auto 150px;
                background-position: center;
                background-repeat: no-repeat;
                background-color: transparent;
                margin-top: -10px;
            }}
        </style>
        <div class="fixed-header"></div>
    """, unsafe_allow_html=True)
####여기까지 변경 #####
# ── 보고서 PDF 생성 ───────────────────────────────────────────────────────────
def generate_report_pdf(filtered: list) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 60, "K-ENT Today News Report")
    c.setFont("Helvetica", 11)
    c.drawString(50, height - 85, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.line(50, height - 100, width - 50, height - 100)

    y = height - 130
    for i, item in enumerate(filtered[:10], 1):
        if y < 100:
            c.showPage()
            y = height - 60

        title = item.get("title", "")[:50]
        category = item.get("sub_category", item.get("category", ""))
        sentiment = item.get("sentiment", "")

        summary = item.get("summary", "")
        if isinstance(summary, list) and summary:
            first = summary[0]
            summary_text = (
                first.get("content", str(first))
                if isinstance(first, dict)
                else str(first)
            )
        else:
            summary_text = str(summary or "")

        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, f"{i}. {title}")
        y -= 18
        c.setFont("Helvetica", 10)
        c.drawString(60, y, f"Category: {category}  |  Sentiment: {sentiment}")
        y -= 15
        c.setFont("Helvetica", 9)
        c.drawString(60, y, summary_text[:80])
        y -= 25
        c.line(50, y, width - 50, y)
        y -= 15

    c.save()
    buffer.seek(0)
    return buffer.read()


# ── 메트릭 카드 ───────────────────────────────────────────────────────────────

def render_metrics(processed: list, past: list):
    total = len(processed) + len(past)
    pos_count = sum(1 for x in processed if x.get("sentiment") in ["positive", "긍정"])
    neg_count = sum(1 for x in processed if x.get("sentiment") in ["negative", "부정"])
    pos_pct = f"{round(pos_count / len(processed) * 100)}%" if processed else "0%"

    top_artist = "-"
    if processed:
        top = processed[0]  # 이미 importance 순 정렬된 첫 번째 = 1위
        tags = _safe_tags(top.get("artist_tags", []))
        top_artist = tags[0] if tags else top.get("title", "-")[:6]

    m1, m2, m3, m4 = st.columns(4)
    metrics = [
        ("📰 오늘 뉴스", f"{total}건", f"최신 {len(processed)}건", "#155724"),
        ("🟢 긍정 기사", pos_pct, f"+{pos_count}건 ↑", "#155724"),
        ("🔴 부정 급등", f"{neg_count}건", f"+{neg_count} ↑", "#721c24"),
        ("🔥 핫 키워드", top_artist, "1위", "#856404"),
    ]
    for col, (label, val, delta, dcolor) in zip([m1, m2, m3, m4], metrics):
        with col:
            st.markdown(
                f"""
                        <div class="metric-card">
                          <div class="metric-label">{label}</div>
                          <div class="metric-value">{val}</div>
                          <div class="metric-delta" style="color:{dcolor}">{delta}</div>
                        </div>""",
                unsafe_allow_html=True,
            )
    st.markdown("<br>", unsafe_allow_html=True)


# ── 오늘의 랭킹 ───────────────────────────────────────────────────────────────

def render_ranking(filtered: list):
    mp3_path = Path(__file__).resolve().parent.parent.parent / "news_report_ko.mp3" 
    txt_path = Path(__file__).resolve().parent.parent.parent / "news_report.txt"
    if not filtered:
        st.markdown('<div style="color:#8b7355;text-align:center;padding:40px;">조건에 맞는 기사가 없습니다.</div>',unsafe_allow_html=True)
        return

    title_col, report_col, btn_col = st.columns([3, 1, 1])
    with title_col:
        st.markdown(
            '<div class="section-title">🏆 오늘의 랭킹</div>', unsafe_allow_html=True
        )
    with report_col:
        pdf_bytes = generate_report_pdf(filtered)
        st.download_button(label=" 📄오늘의 종합 보고서", data=pdf_bytes,
            file_name=f"K-ENT_보고서_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf", use_container_width=True,)
    with btn_col:
        briefing_click = st.button("🎙️ 오늘의 뉴스 브리핑 듣기", use_container_width=True)

    featured = filtered[0]
    tags = _safe_tags(featured.get("artist_tags", []))
    artist_name = tags[0] if tags else ""
    summary_text = ""
    summary = featured.get("summary", [])
    if isinstance(summary, list) and summary:
        if isinstance(summary[0], dict):
            summary_text = summary[0].get("content", "")
        else:
            summary_text = "\n".join([str(s) for s in summary])
    elif isinstance(summary, str):
        summary_text = summary
  
    if briefing_click:

        if txt_path.exists():
            from STEP2.tts import text_to_speech
            with open(txt_path, "r", encoding="utf-8") as f:
                report_text = f.read()
            text_to_speech(report_text, str(mp3_path.parent / "news_report.mp3"))
            with open(mp3_path, "rb") as f:
                audio_bytes = f.read()
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)
        else:
            st.warning("🎙️ 브리핑 파일이 아직 생성되지 않았습니다.")

    left, right = st.columns([1, 2])

    # ── 1위 featured 카드 ────────────────────────────
    with left:
        with st.container(border=True):
            st.markdown(
                f"""<div>
              {_thumb_html(featured.get("thumbnail_url", ""), featured=True)}
            </div>""",
                unsafe_allow_html=True,
            )
            st.markdown(f"""
              <div class="featured-rank">01</div>
              <div style="margin:8px 0 16px;display:flex;align-items:center;gap:8px;">
                 {_badge(featured.get("sentiment","neutral"))}
              <span style="font-size:11px;color:#8b7355;">기사 1건</span>
              </div>
              <div class="featured-artist">{artist_name}</div>
              <div class="featured-headline">{featured.get("title","")}</div>
              <div class="featured-summary">{summary_text}</div>
            """,
                unsafe_allow_html=True,
            )

            if st.button("📄 상세보기",key=f"detail_1_{featured['id']}",use_container_width=True,):
                st.session_state["detail_id"] = featured["id"]
                st.switch_page("pages/dashboard.py")

        logos_b64 = get_base64_image(LOGOS_IMG)
        st.markdown(f"""
                    <div class="section-title">🌐참조 사이트</div>
                    <div style="margin-top: 12px; padding: 12px 16px;border-radius: 12px;text-align: center;">
                        <img src="data:image/png;base64,{logos_b64}"
                             style="width:100%;height:auto;opacity:0.85;" />
                    </div>
                    """,unsafe_allow_html=True,)

    # ── 2위~10위 랭킹 카드 그리드 ────────────────────
    with right:
        rest = filtered[1:10]
        col_a, col_b = st.columns(2)

        for i, item in enumerate(rest):
            rank = i + 2
            rank_cls = "top3" if rank <= 3 else ""
            item_tags = _safe_tags(item.get("artist_tags", []))
            item_artist = item_tags[0] if item_tags else ""
            item_summary = item.get("summary", "")
            if (
                isinstance(item_summary, list)
                and item_summary
                and isinstance(item_summary[0], dict)
            ):
                item_summary_text = item_summary[0].get("content", "")
            else:
                item_summary_text = str(item_summary or "")

            col = col_a if i % 2 == 0 else col_b
            with col:
                with st.container(border=True):
                    st.markdown(
                        f"""
                    <div>
                      {_thumb_html(item.get("thumbnail_url", ""))}
                      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
                        <span class="rank-num {rank_cls}">{str(rank).zfill(2)}</span>
                        <div style="flex:1;min-width:0;">
                          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                           <span class="artist-name">{item.get("title","")}</span>
                            </div>
                            <div class="headline">{item_artist}</div>
                        </div>
                      </div>
                      <div class="summary-text">{item_summary_text}</div>
                      <div style="display:flex;align-items:center;gap:8px;margin-top:8px;margin-bottom:12px;flex-wrap:wrap;">
                    {_badge(item.get("sentiment","neutral"))}
                        <span style="font-size:11px;color:#8b7355;">기사 1건</span>
                        </div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

                    if st.button(
                        "📄 상세보기",
                        key=f"detail_{rank}_{item['id']}",
                        use_container_width=True,
                    ):
                        st.session_state["detail_id"] = item["id"]
                        st.switch_page("pages/dashboard.py")


# ── 메인 대시보드 ─────────────────────────────────────────────────────────────

def render_dashboard(
    processed: list,
    past: list,
    keyword: str,
    category: str,
    sub_category: str,
    sentiments: list[str],
):
    render_header()

    filtered_processed = [
        x for x in processed if _match(x, keyword, category, sub_category, sentiments)
    ]
    filtered_past = [
        x for x in past if _match(x, keyword, category, sub_category, sentiments)
    ]

    # 대시보드의 1~10위(DB 로드) 로직을 그대로 가져옴
    from components.news.news_pip import load_from_db

    dashboard_data = load_from_db()

    # 1. Dashboard Top 10을 가져옴
    dashboard_top_10 = dashboard_data.get("top_news_list", [])

    # 2. Main Page 처럼 화면에 맞게 _match 필터링 통과
    ranking_items = [
        x
        for x in dashboard_top_10
        if _match(x, keyword, category, sub_category, sentiments)
    ]
    render_metrics(processed, past)
    # rank.id를 이용하도록 화면에 보여주기
    render_ranking(ranking_items)
