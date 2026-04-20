# ── 감성 추이 차트 ────────────────────────────────────────────────────────────


def render_sentiment_chart(processed: list):
    st.markdown(
        '<div class="section-title">📊 오늘의 감성 추이</div>', unsafe_allow_html=True
    )

    pos = sum(1 for x in processed if x.get("sentiment") in ["positive", "긍정"])
    neg = sum(1 for x in processed if x.get("sentiment") in ["negative", "부정"])
    neu = sum(1 for x in processed if x.get("sentiment") in ["neutral", "중립"])

    sub_count: dict[str, int] = {}
    for item in processed:
        _, sub = resolve_row_categories(item)
        sub_count[sub] = sub_count.get(sub, 0) + 1

    col1, col2 = st.columns([1, 2])

    with col1:
        fig_pie = go.Figure(
            data=[
                go.Pie(
                    labels=["긍정", "부정", "중립"],
                    values=[pos, neg, neu],
                    hole=0.55,
                    marker=dict(colors=["#6aaa6a", "#cc6666", "#6699cc"]),
                )
            ]
        )
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
            df = pd.DataFrame(
                [
                    {"카테고리": k, "기사수": v}
                    for k, v in sorted(sub_count.items(), key=lambda x: -x[1])
                ]
            )
            fig_bar = go.Figure(
                go.Bar(
                    x=df["기사수"],
                    y=df["카테고리"],
                    orientation="h",
                    marker_color="#8b4513",
                    marker_opacity=0.75,
                )
            )
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
    st.markdown(
        '<div class="section-title">🗂️ 연관 과거 기사</div>', unsafe_allow_html=True
    )
    cols_p = st.columns(2)
    for i, item in enumerate(filtered_past[:10]):
        summary = item.get("summary", "")
        with cols_p[i % 2]:
            st.markdown(
                f"""
            <div class="news-card">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
                {_badge(item.get("sentiment","neutral"))}
                {_cat_badge(item)}
              </div>
              <div class="artist-name">{ (item.get("artist_tags", [])[0] if item.get("artist_tags") else item.get("artist_name", "")) or "-" }</div>
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
            """,
                unsafe_allow_html=True,
            )

## 
    render_sentiment_chart(processed)
    render_past(filtered_past)