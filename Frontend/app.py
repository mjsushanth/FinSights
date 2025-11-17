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
    
    col_logo, col_spacer, col_nav = st.columns([1.6, 4.0, 2.0])

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

    # MIDDLE: just empty
    with col_spacer:
        st.write("")

    # RIGHT: Home + Chatbot side by side
    with col_nav:
        st.markdown('<div class="nav-right">', unsafe_allow_html=True)

        home_col, chat_col = st.columns([1, 1])

        with home_col:
            st.markdown('<div class="nav-home-btn">', unsafe_allow_html=True)
            btn_home = st.button("Home", key="nav_home")
            st.markdown('</div>', unsafe_allow_html=True)

        with chat_col:
            st.markdown('<div class="nav-chat-btn">', unsafe_allow_html=True)
            btn_chat = st.button("Chatbot", key="nav_chat")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # routing triggers
    if btn_home:
        st.session_state.page = "Home"
        st.rerun()
    if btn_chat:
        st.session_state.page = "Chatbot"
        st.rerun()



top_nav()

# ROUTER
if st.session_state.page == "Home":
    render_home()
elif st.session_state.page == "Chatbot":
    render_chatbot()
else:
    render_home()
