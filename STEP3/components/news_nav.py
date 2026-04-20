import streamlit as st

def render(idx: int, top_news_list: list):
    col1, col2, col3 = st.columns([1, 4, 1])
    with col1:
        if idx > 0:
            if st.button("← 이전"):
                st.session_state["detail_id"] = top_news_list[idx - 1]["id"]
                st.rerun()
    with col2:
        st.markdown(
            f"<div style='text-align:center; font-weight:700;'>"
            f"{idx+1}위 / {len(top_news_list)}위</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if idx < len(top_news_list) - 1:
            if st.button("다음 →"):
                st.session_state["detail_id"] = top_news_list[idx + 1]["id"]
                st.rerun()
