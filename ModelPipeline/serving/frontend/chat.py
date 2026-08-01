# ModelPipeline\serving\frontend\chat.py
"""
RESPONSIBILITIES:
✓ Render chat message bubbles (user + assistant)
✓ Display loading spinner during query processing
✓ Show error messages with retry option
✓ Handle chat input submission

UI PATTERN:
- st.chat_message("user") for questions
- st.chat_message("assistant") for answers
- st.chat_input() for new questions

"""

# frontend/chat.py
"""
Chat interface components for FinSight frontend.

Handles chat message rendering, user input, and query submission.

Usage:
    from chat import render_chat_history, handle_user_input
    
    render_chat_history()
    handle_user_input()
"""

import streamlit as st
from typing import Dict, Any

# FIXED: Relative imports (no 'frontend.' prefix)
from api_client import FinSightClient
from state import (
    add_user_message,
    add_assistant_message,
    update_metrics
)
from metrics import (
    display_query_metadata,
    display_error_message
)
from components.answer_render import render_answer


def render_chat_message(message: Dict[str, Any]) -> None:
    """
    Render a single chat message (user or assistant).
    
    Args:
        message: Message dict from session state
    """
    role = message["role"]
    content = message["content"]
    
    with st.chat_message(role):
        # Display message content
        if message.get("error", False):
            # Error message styling
            st.markdown(f"[WARNING] {content}")
        elif role == "assistant":
            # Splits the narrative from the DATA SOURCES block and renders the
            # citations as chips. Falls back to plain markdown if the answer has
            # no parseable sources section.
            render_answer(content)
        else:
            # CHANGED: Use st.write instead of st.markdown to avoid LaTeX parsing
            # st.write handles text more naturally and doesn't trigger LaTeX
            # st.write is still using regex. flaws. detects content and renders appropriately
            st.markdown(content)

        
        # Display metadata for assistant messages (if exists and not error)
        if role == "assistant" and not message.get("error", False):
            metadata = message.get("metadata")
            if metadata:
                display_query_metadata(metadata)




def render_chat_history() -> None:
    """
    Render all messages in chat history.
    
    Reads from st.session_state.messages and displays each message.
    """
    messages = st.session_state.get("messages", [])
    
    for message in messages:
        render_chat_message(message)


def handle_user_input(client: FinSightClient) -> None:
    """
    Handle user input from chat input box.
    
    Processes new user questions, calls backend API, and updates state.
    
    Args:
        client: FinSightClient instance for API calls
    """
    # Chat input at bottom of page
    prompt = st.chat_input("Ask a question about SEC 10-K filings...")
    
    if prompt:
        # Validate input length (client-side check)
        if len(prompt) < 10:
            st.error("[Hey!] Question must be at least 10 characters long.")
            return
        
        # Add user message to history
        add_user_message(prompt)
        
        # Display user message immediately
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Process query with LIVE progress (Tier 1 Change 4b, 2026-08-01).
        # Previously a static spinner for the full 25-50s+ with no feedback -
        # replaced with real pipeline-stage events plus token-by-token text as
        # they actually arrive. client.query() (non-streaming) is untouched
        # and still available - this only changes what this call site uses.
        with st.chat_message("assistant"):
            model_key = st.session_state.get("model_key")

            status = st.status("Starting...", expanded=False)
            answer_placeholder = st.empty()

            accumulated_text = ""
            final_metadata: Dict[str, Any] = {}
            error_event: Dict[str, Any] = {}

            for event in client.query_stream(
                question=prompt,
                include_kpi=True,
                include_rag=True,
                model_key=model_key
            ):
                etype = event.get("type")

                if etype == "stage":
                    ms = event.get("ms", 0)
                    status.update(label=f"{event.get('stage', '...')} ({ms:.0f} ms)")

                elif etype == "token":
                    # Raw, uncleaned deltas while streaming - see
                    # TIER1_LATENCY_DESIGN.md section 4.0. Plain markdown only;
                    # render_answer() needs the COMPLETE cleaned text (it parses
                    # a DATA SOURCES section that only exists once the answer
                    # has fully arrived), so it is called once, below, on
                    # "replace" - never on a partial stream.
                    accumulated_text += event.get("text", "")
                    answer_placeholder.markdown(accumulated_text + " ▌")

                elif etype == "replace":
                    accumulated_text = event.get("text", accumulated_text)

                elif etype == "done":
                    final_metadata = event.get("metadata", {})
                    status.update(label="Done", state="complete")

                elif etype == "error":
                    error_event = event
                    status.update(label="Error", state="error")

            if error_event:
                error_msg = error_event.get("error", "Unknown error occurred")
                error_type = error_event.get("error_type", "UnknownError")
                stage = error_event.get("stage", "unknown")

                display_error_message(error_msg, error_type, stage)

                add_assistant_message(
                    content=error_msg,
                    metadata=None,
                    error=True
                )
            else:
                # Final render, once, with the complete cleaned text - same
                # citation-chip rendering the non-streaming path always used.
                with answer_placeholder.container():
                    render_answer(accumulated_text)

                add_assistant_message(
                    content=accumulated_text,
                    metadata=final_metadata,
                    error=False
                )

                cost = final_metadata.get("llm", {}).get("cost", 0.0)
                update_metrics(cost)

                display_query_metadata(final_metadata)

        # Rerun to update UI
        st.rerun()


def render_clear_button() -> None:
    """
    Render "Clear Chat" button in sidebar.
    
    Allows users to start a new conversation.
    """
    #: Relative import
    from state import clear_chat_history
    
    if st.sidebar.button("Clear Chat History", use_container_width=True):
        clear_chat_history()
        st.rerun()