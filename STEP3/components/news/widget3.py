import streamlit as st


def score_to_pct(score: float) -> int:
    return max(0, min(100, int((1 - score) * 100)))


def score_class(pct: int) -> str:
    if pct >= 85:
        return "rag-score-high"
    if pct >= 70:
        return "rag-score-mid"
    return "rag-score-low"


def render(related: list):
    rag_html = """
    <div class='widget-card'>
        <div class='widget-title'>
            <span class='dot-purple'></span>
            관련 키워드 기사
        </div>"""

    if related:
        for r in related:
            meta = r.get("metadata", {})
            score = r.get("score", 1.0)
            pct = score_to_pct(score)
            s_class = score_class(pct)
            title = meta.get("title") or r["content"][:60]
            cat = meta.get("sub_category", "")
            artist = meta.get("artist_name", "")
            url = meta.get("url", "")
            rag_html += f"""
            <div class='rag-card'>
                <div class='rag-score {s_class}'>{pct}%</div>
                <div>
                    <div class='rag-title'>{title}</div>
                   <div class='rag-meta'>{cat} · {artist} · {f"<a href='{url}' target='_blank' style='color:#1a56db;'>기사 보기 →</a>" if url else ""}</div>
                </div>
            </div>"""
    else:
        rag_html += "<div style='font-size:0.88rem; color:#888; padding:8px 0;'>관련 과거 기사가 없습니다.</div>"

    rag_html += "</div>"
    st.markdown(rag_html, unsafe_allow_html=True)
