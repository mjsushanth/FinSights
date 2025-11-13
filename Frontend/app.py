# app.py
import streamlit as st

from utils.styles import inject_global_css
from pages.home import render_home
from pages.auth import render_auth
from pages.chatbot import render_chatbot

# st.markdown(
#     """
#     <style>
#     .stButton > button {
#         background: transparent !important;
#         border: none !important;
#         outline: none !important;
#         box-shadow: none !important;
#         color: #94a3b8 !important;
#         padding: 0.15rem 0.6rem !important;
#         border-radius: 0 !important;
#         font-size: 0.9rem !important;
#     }
#     .stButton > button:hover {
#         color: #e5e7eb !important;
#         background: rgba(15,23,42,0.7) !important;
#     }
#     </style>
#     """,
#     unsafe_allow_html=True,
# )

st.set_page_config(
    page_title="Finsights – 10-K Intelligence",
    page_icon="💹",
    layout="wide",
)


def init_state():
    if "page" not in st.session_state:
        st.session_state.page = "Home"
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False
    if "user_email" not in st.session_state:
        st.session_state.user_email = None
    if "messages" not in st.session_state:
        st.session_state.messages = []


init_state()
inject_global_css()


def top_nav():
    st.markdown('<div class="top-nav">', unsafe_allow_html=True)

    col_logo, col_spacer, col_home, col_login, col_chat = st.columns(
        [1.6, 3.0, 0.7, 0.8, 1.0]
    )

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

    with col_spacer:
        st.write("")

    with col_home:
        st.markdown('<div class="top-nav-btn">', unsafe_allow_html=True)
        if st.button("Home", key="nav_home"):
            st.session_state.page = "Home"
        st.markdown('</div>', unsafe_allow_html=True)

    with col_login:
        st.markdown('<div class="top-nav-btn">', unsafe_allow_html=True)
        if st.button("Login", key="nav_login"):
            st.session_state.page = "Auth"
        st.markdown('</div>', unsafe_allow_html=True)

    with col_chat:
        st.markdown('<div class="top-nav-btn">', unsafe_allow_html=True)
        if st.button("Chatbot", key="nav_chat"):
            st.session_state.page = "Chatbot"
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


top_nav()

# ROUTER
if st.session_state.page == "Home":
    render_home()
elif st.session_state.page == "Auth":
    render_auth()
elif st.session_state.page == "Chatbot":
    render_chatbot()
else:
    render_home()
