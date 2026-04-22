import streamlit as st
from pathlib import Path
from datetime import datetime
from utils.report_generator import generate_report_pdf
from components.ui_helpers import _safe_tags, _thumb_html, _badge, LOGOS_IMG, get_base64_image

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
