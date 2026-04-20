import streamlit as st

def render(news: dict):
    # 제목 + 메타
    st.markdown(
        f"<div class='news-title'>{news['title']}</div>",
        unsafe_allow_html=True
    )
    st.markdown(
        f"<div class='news-meta'>{news['source_name']} · "
        f"{news['published_at'][:10] if news['published_at'] else ''}</div>",
        unsafe_allow_html=True,
    )

    # 요약 공통 헤더
    def render_summary(items: list, label_text: str):
        st.markdown(
            f"<div class='section-label'>{label_text}</div>",
            unsafe_allow_html=True
        )
        html = ""
        for item in items:
            if isinstance(item, dict):
                label = item.get("label", "")
                content = item.get("content", "")
            else:
                label, content = "", str(item)
            html += f"""
            <div style='display:grid; grid-template-columns:2fr 8fr; gap:10px;
                        margin-bottom:10px; align-items:start;'>
                <span style='background:#e8f0fe; color:#1a56db; font-size:0.75rem;
                             font-weight:700; padding:3px 9px; border-radius:20px;
                             text-align:center; word-break:keep-all; line-height:1.5;'>
                    {label}
                </span>
                <span style='font-size:0.92rem; color:#1a1a2e; line-height:1.6;'>
                    {content}
                </span>
            </div>"""
        st.markdown(html, unsafe_allow_html=True)

    render_summary(news.get("summary", []),    "요약 카드 (SUMMARY)")
    render_summary(news.get("summary_en", []), "요약 카드 (ENGLISH)")

    # 키워드
    st.markdown("<div class='section-label'>키워드</div>", unsafe_allow_html=True)
    kw_html = "<div class='keyword-wrap'>"
    for kw in news.get("keywords", []):
        kw_html += f"<span class='keyword-tag'>{kw}</span>"
    kw_html += "</div>"
    st.markdown(kw_html, unsafe_allow_html=True)
