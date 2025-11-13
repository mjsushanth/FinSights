# pages/chatbot.py
from datetime import datetime

import streamlit as st

from utils.backend import query_backend


def _render_chat_history():
    for msg in st.session_state.messages:
        role = msg["role"]
        content = msg["content"]
        ts = msg.get("timestamp")
        ts_str = datetime.fromisoformat(ts).strftime("%H:%M") if ts else ""

        if role == "user":
            st.markdown(
                f'<div class="chat-meta">You · {ts_str}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="chat-bubble-user">{content}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="chat-meta">Finsights · {ts_str}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="chat-bubble-ai">{content}</div>',
                unsafe_allow_html=True,
            )


def render_chatbot():
    st.header("💬 Finsights 10-K Chatbot")
    st.caption("Ask questions in natural language and get answers grounded in SEC filings.")

    if not st.session_state.get("is_authenticated", False):
        st.warning("Please sign in first using the **Login** button in the top nav.")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        with st.expander("Best results", expanded=True):
            st.markdown(
                """
                - Mention the **company** and **filing year** whenever possible.  
                - Ask about **trends** (margins, revenue mix, leverage) instead of single numbers.  
                - Use follow-ups to drill into MD&A, Risk Factors, or specific notes.  
                """
            )
    with c2:
        with st.expander("Disclosure", expanded=False):
            st.markdown(
                """
                - Finsights is a research UX layer and does **not** provide investment advice.  
                - Always review the original SEC filings and your internal research before acting.  
                """
            )

    st.markdown("---")

    chat_container = st.container()
    input_container = st.container()

    with chat_container:
        _render_chat_history()

    with input_container:
        prompt = st.text_input(
            "Ask about a 10-K…",
            placeholder="e.g. For Apple’s 2023 10-K, how did services revenue evolve vs. last year?",
        )
        send = st.button("Ask Finsights")

    if send and prompt:
        st.session_state.messages.append(
            {
                "role": "user",
                "content": prompt,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        with st.spinner("Reading filings and generating an answer…"):
            answer = query_backend(
                prompt, session_id=st.session_state.get("user_email") or "anonymous"
            )

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": answer,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        st.experimental_rerun()
