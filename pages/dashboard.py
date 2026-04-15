"""
pages/dashboard.py — 기사 상세 + 보고서 페이지
"""

import sys
import sqlite3
import json
import asyncio
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import edge_tts
import streamlit as st
import streamlit.components.v1 as components
from components.styles import apply_styles
from categories import accent_color_for_row, resolve_row_categories

DB_PATH = Path("k_enter_news.db")

st.set_page_config(
    page_title="상세보기 | K-ENT Now",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

apply_styles()

# 이 페이지에서는 사이드바 완전히 숨김
st.markdown("""
<style>
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

SENT_LABEL  = {"positive": "긍정", "neutral": "중립", "negative": "부정"}
SENT_COLOR  = {"positive": "#155724", "neutral": "#0c5460", "negative": "#721c24"}
SENT_BG     = {"positive": "#d4edda", "neutral": "#d1ecf1",  "negative": "#f8d7da"}
CAT_COLOR   = {"음악/차트":"#1D9E75","앨범/신곡":"#BA7517","콘서트/투어":"#0F6E56",
               "드라마/방송":"#D4537E","예능/방송":"#993556","공연/전시":"#0E7490",
               "영화/OTT":"#C2410C","팬덤/SNS":"#5F5E5A","스캔들/논란":"#D85A30",
               "인사/동정":"#6366F1","미담/기부":"#059669","연애/결혼":"#EC4899",
               "입대/군복무":"#64748B","산업/기획사":"#7F77DD","해외반응":"#378ADD",
               "마케팅/브랜드":"#CA8A04","행사/이벤트":"#9333EA","기타":"#888780"}


# ── DB ───────────────────────────────────────────────────────────────────────

def _open():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con

def _j(v):
    if v is None: return []
    if isinstance(v, (list, dict)): return v
    try: return json.loads(v)
    except: return []

def load_article(article_id: int) -> dict | None:
    if not DB_PATH.exists(): return None
    con = _open()
    cur = con.cursor()
    cur.execute("""
        SELECT p.id, r.title, p.url, p.category, p.summary,
               p.keywords, p.artist_tags, p.sentiment, p.sentiment_score,
               p.source_name, p.tts_text, p.processed_at, p.thumbnail_url
        FROM processed_news p
        JOIN raw_news r ON r.id = p.raw_news_id
        WHERE p.id = ?
    """, (article_id,))
    row = cur.fetchone()
    con.close()
    if not row: return None
    return {
        "id": row["id"], "title": row["title"] or "",
        "url": row["url"] or "", "category": row["category"] or "기타",
        "summary": _j(row["summary"]), "keywords": _j(row["keywords"]),
        "artist_tags": _j(row["artist_tags"]), "sentiment": row["sentiment"] or "neutral",
        "sentiment_score": row["sentiment_score"] if row["sentiment_score"] is not None else 0.0,
        "source_name": row["source_name"] or "", "tts_text": row["tts_text"] or "",
        "processed_at": row["processed_at"] or "", "thumbnail_url": row["thumbnail_url"] or "",
    }

def load_related_past(article_id: int) -> list[dict]:
    if not DB_PATH.exists(): return []
    con = _open()
    cur = con.cursor()
    cur.execute("""
        SELECT id, artist_name, title, url, summary,
               relation_type, relevance_score, sentiment,
               category, source_name, published_at
        FROM past_news WHERE processed_news_id = ?
        ORDER BY relevance_score DESC LIMIT 10
    """, (article_id,))
    rows = cur.fetchall()
    con.close()
    return [{
        "id": r["id"], "artist_name": r["artist_name"] or "",
        "title": r["title"] or "", "url": r["url"] or "",
        "summary": r["summary"] or "", "relation_type": r["relation_type"] or "",
        "relevance_score": r["relevance_score"] if r["relevance_score"] is not None else 0.0,
        "sentiment": r["sentiment"] or "neutral", "category": r["category"] or "기타",
        "source_name": r["source_name"] or "", "published_at": r["published_at"] or "",
    } for r in rows]

def load_all_processed() -> list[dict]:
    if not DB_PATH.exists(): return []
    con = _open()
    cur = con.cursor()
    cur.execute("""
        SELECT p.id, r.title, p.url, p.category, p.summary,
               p.keywords, p.artist_tags, p.sentiment, p.sentiment_score,
               p.source_name, p.processed_at, p.thumbnail_url
        FROM processed_news p
        JOIN raw_news r ON r.id = p.raw_news_id
        ORDER BY p.id DESC LIMIT 50
    """)
    rows = cur.fetchall()
    con.close()
    return [{
        "id": r["id"], "title": r["title"] or "", "url": r["url"] or "",
        "category": r["category"] or "기타", "summary": _j(r["summary"]),
        "keywords": _j(r["keywords"]), "artist_tags": _j(r["artist_tags"]),
        "sentiment": r["sentiment"] or "neutral",
        "sentiment_score": r["sentiment_score"] if r["sentiment_score"] is not None else 0.0,
        "source_name": r["source_name"] or "", "processed_at": r["processed_at"] or "",
        "thumbnail_url": r["thumbnail_url"] or "",
    } for r in rows]


# ── TTS ──────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def tts_to_bytes(text: str) -> bytes:
    async def _gen():
        communicate = edge_tts.Communicate(text=text, voice="ko-KR-SunHiNeural", rate="+20%")
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio": buf.write(chunk["data"])
        return buf.getvalue()
    return asyncio.run(_gen())


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _sent_badge(sentiment: str) -> str:
    ko = SENT_LABEL.get(sentiment, "중립")
    c  = SENT_COLOR.get(sentiment, "#0c5460")
    bg = SENT_BG.get(sentiment, "#d1ecf1")
    return f'<span style="background:{bg};color:{c};padding:2px 8px;border-radius:20px;font-size:12px;font-weight:700;">● {ko}</span>'

def _cat_badge_html(cat: str) -> str:
    c = CAT_COLOR.get(cat, "#888780")
    return f'<span style="background:{c}18;color:{c};border:1px solid {c}55;padding:2px 8px;border-radius:20px;font-size:12px;font-weight:700;">{cat}</span>'

def _imp(score: float) -> int:
    return int(score * 10) if score <= 1.0 else int(score)


# ── 뒤로가기 ─────────────────────────────────────────────────────────────────

def _back_btn():
    if st.button("← 대시보드로 돌아가기"):
        st.switch_page("app.py")


# ══════════════════════════════════════════════════════════════════════════════
# 상세보기 페이지
# ══════════════════════════════════════════════════════════════════════════════

def render_detail(article: dict, past_list: list):
    major, sub = resolve_row_categories(article)
    color      = accent_color_for_row(article)
    sentiment  = article.get("sentiment", "neutral")
    score      = float(article.get("sentiment_score", 0))
    score_int  = _imp(score)
    score_disp = f"{score * 100:.0f}점" if score <= 1.0 else f"{score:.0f}점"

    # 상단 태그
    st.markdown(f"""
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;">
        {_cat_badge_html(sub)}
        {_sent_badge(sentiment)}
        <span style="background:#f5f0e8;color:#5c4a3a;border:1px solid #d4c4a8;
            padding:2px 10px;border-radius:20px;font-size:12px;">중요도 {score_int}/10</span>
    </div>
    """, unsafe_allow_html=True)

    # 제목
    st.markdown(f"""
    <div style="font-size:22px;font-weight:900;color:#2c1810;
        font-family:'Noto Serif KR',serif;line-height:1.5;margin-bottom:10px;">
        {article.get("title","")}
    </div>
    <div style="font-size:13px;color:#8b7355;margin-bottom:20px;
        padding-bottom:12px;border-bottom:1px solid #d4c4a8;">
        {article.get("source_name") or "-"} · {article.get("processed_at","")[:10]}
    </div>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns([6, 4])

    with col_left:
        with st.container(border=True):
            # 썸네일
            if article.get("thumbnail_url"):
                st.image(article["thumbnail_url"], use_container_width=True)

            # 핵심 요약
            summary = article.get("summary", "")
            if summary:
                st.markdown('<div style="font-size:14px;font-weight:700;color:#2c1810;margin:12px 0 8px;">핵심 요약</div>', unsafe_allow_html=True)
                if isinstance(summary, list):
                    for idx, line in enumerate(summary, 1):
                        st.markdown(f"""
                        <div style="display:flex;gap:10px;margin-bottom:8px;">
                            <span style="color:#8b4513;font-weight:700;min-width:18px;">{idx}.</span>
                            <span style="color:#2c1810;font-size:14px;line-height:1.7;">{line}</span>
                        </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f'<div style="color:#2c1810;font-size:14px;line-height:1.8;">{summary}</div>', unsafe_allow_html=True)

            # 3줄 브리핑
            keywords = article.get("keywords", [])
            tts_text = article.get("tts_text", "")
            if keywords and tts_text:
                st.markdown('<div style="font-size:14px;font-weight:700;color:#2c1810;margin:16px 0 8px;">3줄 브리핑</div>', unsafe_allow_html=True)
                sentences = [s.strip() for s in tts_text.split(". ") if s.strip()]
                kw_colors = ["#1a5c3a","#0c4a6e","#4a1942","#7c2d12","#1e3a5f"]
                for idx, kw in enumerate(keywords[:3]):
                    sent = sentences[idx] if idx < len(sentences) else tts_text[:80]
                    kc = kw_colors[idx % len(kw_colors)]
                    st.markdown(f"""
                    <div style="display:flex;gap:10px;margin-bottom:10px;align-items:flex-start;">
                        <span style="background:{kc};color:#fff;padding:2px 8px;border-radius:6px;
                            font-size:11px;font-weight:700;white-space:nowrap;margin-top:2px;">{kw}</span>
                        <span style="color:#2c1810;font-size:14px;line-height:1.7;">{sent}</span>
                    </div>""", unsafe_allow_html=True)

            # 키워드
            if keywords:
                st.markdown('<div style="font-size:14px;font-weight:700;color:#2c1810;margin:16px 0 8px;">키워드</div>', unsafe_allow_html=True)
                kw_html = " ".join([f'<span style="background:#f5f0e8;color:#2c1810;border:1px solid #c9b99a;padding:3px 12px;border-radius:20px;font-size:12px;font-weight:600;">{k}</span>' for k in keywords])
                st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:6px;">{kw_html}</div>', unsafe_allow_html=True)

            # TTS 박스
            if tts_text:
                st.markdown('<div style="font-size:14px;font-weight:700;color:#2c1810;margin:16px 0 8px;">TTS 브리핑</div>', unsafe_allow_html=True)
                st.markdown(f"""
                <div style="background:#f0faf4;border:1px solid #b7dfc8;border-radius:10px;
                    padding:16px 20px;color:#1a3d2b;font-size:14px;line-height:1.9;">
                    {tts_text}
                </div>""", unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔊 음성으로 듣기", use_container_width=False):
                    with st.spinner("음성 생성 중..."):
                        audio = tts_to_bytes(tts_text[:500])
                        st.audio(audio, format="audio/mp3", autoplay=True)

            if article.get("url"):
                st.link_button("🔗 원문 기사 보기", article["url"])

    with col_right:
        # 위젯 1 — So What? 인사이트
        insight = f"{sub} 분야에서 주목할 만한 이슈로, " + (
            summary[0] if isinstance(summary, list) and summary else (summary[:60] if summary else "관련 동향을 주시할 필요가 있습니다.")
        )
        st.markdown(f"""
        <div style="background:#fff;border:1px solid #d4c4a8;border-radius:12px;padding:18px 20px;margin-bottom:14px;">
            <div style="font-size:11px;color:#8b7355;margin-bottom:10px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;">위젯 1 · SO WHAT? 인사이트</div>
            <div style="border-left:3px solid {color};border-radius:0 8px 8px 0;padding:10px 14px;background:#f0fdf8;">
                <div style="font-size:10px;font-weight:700;color:{color};margin-bottom:4px;letter-spacing:.06em;">{sub} 시사점</div>
                <div style="font-size:13px;color:#2c1810;line-height:1.8;">{insight}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 위젯 2 — 타임라인
        timeline = sorted([p for p in past_list if p.get("published_at")], key=lambda x: x.get("published_at",""))
        if timeline:
            artist = (article.get("artist_tags") or ["아티스트"])[0]
            items_html = ""
            for i, item in enumerate(timeline[:5]):
                sent = item.get("sentiment","neutral")
                sc   = SENT_COLOR.get(sent, "#0c5460")
                sbg  = SENT_BG.get(sent, "#d1ecf1")
                dot  = sc
                is_last = i == len(timeline[:5]) - 1
                items_html += f"""
                <div style="display:flex;gap:12px;margin-bottom:{'4px' if not is_last else '0'};">
                    <div style="display:flex;flex-direction:column;align-items:center;width:16px;flex-shrink:0;">
                        <div style="width:10px;height:10px;border-radius:50%;background:{dot};margin-top:4px;flex-shrink:0;"></div>
                        {"<div style='width:2px;flex:1;background:#d4c4a8;margin-top:2px;min-height:30px;'></div>" if not is_last else ""}
                    </div>
                    <div style="padding-bottom:14px;">
                        <div style="font-size:11px;color:#8b7355;margin-bottom:2px;">{item.get("published_at","")[:7]}</div>
                        <div style="font-size:13px;font-weight:700;color:#2c1810;line-height:1.5;margin-bottom:4px;">{item.get("title","")[:28]}</div>
                        <span style="background:{sbg};color:{sc};padding:1px 8px;border-radius:20px;font-size:11px;font-weight:700;">{SENT_LABEL.get(sent,"중립")}</span>
                    </div>
                </div>"""
            st.markdown(f"""
            <div style="background:#fff;border:1px solid #d4c4a8;border-radius:12px;padding:18px 20px;margin-bottom:14px;">
                <div style="font-size:11px;color:#8b7355;margin-bottom:14px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;">위젯 2 · {artist} 타임라인</div>
                {items_html}
            </div>""", unsafe_allow_html=True)

        # 위젯 3 — 과거 유사 사례 RAG
        top_past = sorted(past_list, key=lambda x: -float(x.get("relevance_score",0)))[:4]
        if top_past:
            items_html = ""
            for item in top_past:
                pct = int(float(item.get("relevance_score",0)) * 100)
                _, psub = resolve_row_categories(item)
                imp = int(float(item.get("relevance_score",0)) * 10)
                url = item.get("url","")
                if pct >= 80: sc2, sbg2 = "#3C3489","#EEEDFE"
                elif pct >= 60: sc2, sbg2 = "#0C447C","#E6F1FB"
                else: sc2, sbg2 = "#27500A","#EAF3DE"
                link = f'<a href="{url}" target="_blank" style="font-size:11px;color:#8b4513;">인사이트 보기 →</a>' if url else ""
                items_html += f"""
                <div style="display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-bottom:0.5px solid #f0e8dc;">
                    <div style="min-width:40px;height:40px;border-radius:8px;background:{sbg2};color:{sc2};
                        display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0;">{pct}%</div>
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:13px;font-weight:700;color:#2c1810;line-height:1.5;margin-bottom:3px;">{item.get("title","")[:30]}</div>
                        <div style="font-size:11px;color:#8b7355;margin-bottom:4px;">{psub} · imp {imp}</div>
                        {link}
                    </div>
                </div>"""
            st.markdown(f"""
            <div style="background:#fff;border:1px solid #d4c4a8;border-radius:12px;padding:18px 20px;">
                <div style="font-size:11px;color:#8b7355;margin-bottom:4px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;">위젯 3 · 과거 유사 사례 RAG</div>
                {items_html}
            </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# 보고서 페이지
# ══════════════════════════════════════════════════════════════════════════════

def render_report(all_processed: list):
    st.markdown('<div class="section-title">📋 뉴스 보고서</div>', unsafe_allow_html=True)

    if not all_processed:
        st.warning("데이터가 없습니다.")
        return

    total     = len(all_processed)
    pos_count = sum(1 for x in all_processed if x.get("sentiment") == "positive")
    neg_count = sum(1 for x in all_processed if x.get("sentiment") == "negative")
    neu_count = total - pos_count - neg_count
    pos_pct   = round(pos_count / total * 100, 1) if total else 0
    neg_pct   = round(neg_count / total * 100, 1) if total else 0

    # 상단 메트릭
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">수집 기사</div><div class="metric-value">{total}건</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">긍정 비율</div><div class="metric-value" style="color:#155724">{pos_pct}%</div><div class="metric-delta" style="color:#155724">{pos_count}건</div></div>', unsafe_allow_html=True)
    with m3:
        st.markdown(f'<div class="metric-card"><div class="metric-label">부정 비율</div><div class="metric-value" style="color:#721c24">{neg_pct}%</div><div class="metric-delta" style="color:#721c24">{neg_count}건 · 리스크 감지</div></div>', unsafe_allow_html=True)

    # 감성 바
    st.markdown("<br>", unsafe_allow_html=True)
    pos_w = round(pos_count / total * 100) if total else 0
    neg_w = round(neg_count / total * 100) if total else 0
    neu_w = 100 - pos_w - neg_w
    st.markdown(f"""
    <div style="display:flex;height:10px;border-radius:5px;overflow:hidden;margin-bottom:20px;">
        <div style="width:{pos_w}%;background:#1D9E75;"></div>
        <div style="width:{neg_w}%;background:#D85A30;"></div>
        <div style="width:{neu_w}%;background:#D3D1C7;"></div>
    </div>""", unsafe_allow_html=True)

    # 대표 기사 3개
    st.markdown('<div class="section-title">📰 대표 기사</div>', unsafe_allow_html=True)
    top3 = sorted(all_processed, key=lambda x: -float(x.get("sentiment_score",0)))[:3]
    cols = st.columns(3)
    for i, item in enumerate(top3):
        _, sub = resolve_row_categories(item)
        color  = accent_color_for_row(item)
        sent   = item.get("sentiment","neutral")
        summary = item.get("summary","")
        s_text = summary[0] if isinstance(summary, list) and summary else (summary[:80] if summary else "")
        insight = f"{sub} 분야에서 주목할 이슈입니다. {s_text[:60]}"
        with cols[i]:
            with st.container(border=True):
                st.markdown(f"""
                <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
                    {_cat_badge_html(sub)}
                    {_sent_badge(sent)}
                    <span style="font-size:11px;color:#8b7355;">imp {_imp(float(item.get("sentiment_score",0)))}</span>
                </div>
                <div style="font-size:13px;font-weight:700;color:#2c1810;line-height:1.5;margin-bottom:8px;
                    overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">
                    {item.get("title","")}
                </div>
                <div style="border-left:3px solid {color};padding:8px 12px;background:#f0fdf8;border-radius:0 8px 8px 0;margin-bottom:8px;">
                    <div style="font-size:10px;font-weight:700;color:{color};margin-bottom:3px;">So What? 인사이트</div>
                    <div style="font-size:12px;color:#2c1810;line-height:1.6;">{insight}</div>
                </div>
                <div style="font-size:11px;color:#8b7355;">{item.get("source_name","-")}</div>
                """, unsafe_allow_html=True)
                if st.button("📄 상세보기", key=f"rep_detail_{item['id']}", use_container_width=True):
                    st.session_state["detail_id"] = item["id"]
                    st.rerun()

    # 전체 기사 목록
    st.markdown('<div class="section-title">🗂️ 전체 기사 목록</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    for i, item in enumerate(all_processed):
        _, sub = resolve_row_categories(item)
        sent   = item.get("sentiment","neutral")
        col    = col_a if i % 2 == 0 else col_b
        with col:
            with st.container(border=True):
                st.markdown(f"""
                <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px;">
                    {_cat_badge_html(sub)}
                    {_sent_badge(sent)}
                </div>
                <div style="font-size:13px;font-weight:700;color:#2c1810;line-height:1.5;margin-bottom:4px;">
                    {item.get("title","")[:45]}
                </div>
                <div style="font-size:11px;color:#8b7355;">
                    📰 {item.get("source_name","-")} · {item.get("processed_at","")[:10]}
                </div>
                """, unsafe_allow_html=True)
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("📄 상세보기", key=f"list_detail_{item['id']}", use_container_width=True):
                        st.session_state["detail_id"] = item["id"]
                        st.rerun()
                with b2:
                    if item.get("url"):
                        st.link_button("🔗 원문", item["url"], use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════

def main():
    _back_btn()

    article_id  = st.session_state.get("detail_id")
    view_mode   = st.session_state.get("view_mode", "report")

    # 탭
    tab1, tab2 = st.tabs(["📋 보고서", "📄 상세보기"])

    with tab1:
        all_processed = load_all_processed()
        render_report(all_processed)

    with tab2:
        if not article_id:
            st.info("대시보드에서 상세보기 버튼을 눌러주세요.")
        else:
            article   = load_article(article_id)
            past_list = load_related_past(article_id)
            if article:
                render_detail(article, past_list)
            else:
                st.error(f"ID {article_id} 기사를 찾을 수 없습니다.")

main()