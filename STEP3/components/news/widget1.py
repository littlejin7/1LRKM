import streamlit as st

def render(trend_insight: str):
    st.markdown(
        f"""
        <div class='widget-card'>
            <div class='widget-title'>
                <span class='dot-green'></span>
                트렌드 인사이트
            </div>
            <div class='so-what-text'>{trend_insight}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
