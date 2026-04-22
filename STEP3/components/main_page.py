import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# -- 보고서

from categories import accent_color_for_row, resolve_row_categories

from components.ui_helpers import SENT_LABEL, TITLE_IMG, get_base64_image, _safe_tags
from components.ranking_widget import render_ranking





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
