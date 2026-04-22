import streamlit as st


def render(timeline: list, artist_tags: list):
    artist_name = artist_tags[0] if artist_tags else ""

    timeline_html = """
    <div class='widget-card'>
        <div class='widget-title'>
            <span class='dot-blue'></span>
            최근 6개월 관련 기사
        </div>
        <div class='timeline-wrap'>"""

    for i, item in enumerate(timeline):
        is_last = i == 0
        sentiment = item.get("sentiment", "neutral")

        dot_class = {
            "positive": "timeline-dot-active",
            "negative": "timeline-dot-negative",
        }.get(sentiment, "timeline-dot-neutral")

        badge_cls = {
            "positive": "badge-current",
            "negative": "badge-negative",
        }.get(sentiment, "badge-neutral")

        badge_txt = {
            "positive": "긍정",
            "negative": "부정",
        }.get(sentiment, "중립")

        if is_last:
            badge_txt += " · 현재"

        url = item.get("url", "")
        url_html = (
            f"<a href='{url}' target='_blank' style='font-size:0.75rem; color:#1a56db;'>기사 보기 →</a>"
            if url
            else ""
        )

        timeline_html += f"""
        <div class='timeline-item'>
            <div class='timeline-dot {dot_class}'></div>
            <div>
                <div class='timeline-date'>{item.get('date', '')}</div>
                <div class='timeline-event'>{item.get('event', '')}</div>
                <span class='sentiment-badge {badge_cls}'>{badge_txt}</span>
                {url_html}
            </div>
        </div>"""

    timeline_html += "</div></div>"
    st.markdown(timeline_html, unsafe_allow_html=True)
