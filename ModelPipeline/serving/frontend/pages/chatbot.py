# frontend/pages/chatbot.py
"""
FinSight Chatbot Page - RAG query interface with full sidebar. 

Preserves ALL existing functionality from original app.py:
- Sidebar: System status, statistics, about, examples (via render_sidebar)
- Chat: Full message history with metadata
- API: Robust error handling via api_client.py
- State: Cost tracking via state.py
- Metrics: Detailed query metadata via metrics.py
"""

import streamlit as st
import sys
from pathlib import Path

# CRITICAL: Add parent directory to Python path
# This allows imports from frontend/ folder
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Now imports should work
from api_client import FinSightClient
from state import init_session_state
from chat import render_chat_history, handle_user_input
from sidebar import render_sidebar
from config import BACKEND_URL, API_TIMEOUT
from components.styles import inject_global_css

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="FinSight Chatbot",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Streamlit runs each page in pages/ as its own script, so app.py's body - and
# therefore its inject_global_css() call - never executes on this page. Without
# this line the chat page falls back to unstyled Streamlit defaults: no source
# chips, no stat tiles, no chat-bubble accents. Must follow set_page_config.
inject_global_css()

# ============================================================================
# INITIALIZATION
# ============================================================================

# Initialize session state
init_session_state()

# Initialize API client (cached)
@st.cache_resource
def get_api_client():
    """Get API client instance (singleton)."""
    return FinSightClient(base_url=BACKEND_URL, timeout=API_TIMEOUT)

client = get_api_client()

# ============================================================================
# SIDEBAR (SHARED ACROSS ALL PAGES)
# ============================================================================

render_sidebar(client)

# ============================================================================
# MAIN CONTENT
# ============================================================================

# Header
st.title("💬 FinSight Assistant")
st.markdown("Ask questions. Expand sidebar (to left) for examples, status, live-costs and more.")

# Best practices banner
with st.expander("💡 Best Results", expanded=True):
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **For Best Results:**
        - Mention the **company** and **filing year**
        - Ask about **trends** (margins, revenue, leverage)
        - Phrase questions clearly
        """)
    
    with col2:
        st.markdown("""
        **Disclosure:**
        - FinSight is a **research tool**, not investment advice
        - Always review original SEC filings
        - Verify critical information independently
        """)

st.markdown("---")

# Check backend status warning
if st.session_state.get("backend_healthy") is None:
    st.warning("⚠️ Backend status unknown. Click '🔄 Check Backend' in the sidebar to verify connection.")

# Render chat history
render_chat_history()

# Handle user input (chat input box at bottom)
handle_user_input(client)

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")

col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.caption("FinSight v1.0 | IE7374 MLOps Capstone Project")
    st.caption("Built with Streamlit + FastAPI + AWS Bedrock")