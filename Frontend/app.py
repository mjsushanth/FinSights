# app.py
import streamlit as st

from utils.styles import inject_global_css
from pages.home import render_home
from pages.chatbot import render_chatbot

st.set_page_config(
    page_title="Finsights – 10-K Intelligence",
    page_icon="💹",
    layout="wide",
)


def init_state():
    if "page" not in st.session_state:
        st.session_state.page = "Home"
    if "messages" not in st.session_state:
        st.session_state.messages = []


init_state()
inject_global_css()


def top_nav():
    st.markdown('<div class="top-nav">', unsafe_allow_html=True)

    col_logo, col_center, col_right = st.columns([1.6, 3.0, 1.8])

    # LEFT: logo
    with col_logo:
        st.markdown(
            """
            <div class="nav-left">
                <div class="logo-dot"></div>
                <div class="logo-text">Fin<span>insights</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # CENTER: Home link (graid-style center nav)
    with col_center:
        st.markdown('<div class="nav-center">', unsafe_allow_html=True)
        if st.button("Home", key="nav_home"):
            st.session_state.page = "Home"
        st.markdown("</div>", unsafe_allow_html=True)

    # RIGHT: single Chatbot CTA (no Login anymore)
    with col_right:
        st.markdown('<div class="nav-right">', unsafe_allow_html=True)
        if st.button("Chatbot", key="nav_chat"):
            st.session_state.page = "Chatbot"
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


top_nav()

# ROUTER
if st.session_state.page == "Home":
    render_home()
elif st.session_state.page == "Chatbot":
    render_chatbot()
else:
    render_home()
