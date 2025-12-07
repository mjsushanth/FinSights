# frontend/app.py
"""
FinSight - Financial Document Intelligence System

---------------------------------------------------------------------------

cd ModelPipeline
.\serving\frontend\venv_frontend\Scripts\Activate.ps1
cd """

import streamlit as st
from api_client import FinSightClient
from state import init_session_state
from sidebar import render_sidebar
from config import BACKEND_URL, API_TIMEOUT

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="FinSight Intelligence",
    page_icon="💹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# INITIALIZATION
# ============================================================================

# """
# Single source of truth: Only api_client.py knows about URLs
# Thought p deep about this one, what to do.
# local + cloud without app.py changes, should work. Env awareness solid goes to whom? it goes to- api_client.py
# app.py: doesn't need to understand deployment environments
# """


# Initialize session state
init_session_state()

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
# WELCOME PAGE
# ============================================================================

st.title("💹 FinSight")
st.markdown("### Financial Document Intelligence System")
st.markdown("---")

st.info("👈 **Use the sidebar to navigate between pages**")

st.markdown("""
**Available Pages:**
- **Home**: Product overview, features, and examples
- **Chatbot**: Ask questions about SEC 10-K filings

**Quick Start:**
1. Check backend status in the sidebar (click "🔄 Check Backend")
2. Use sidebar navigation to go to the **Chatbot** page
3. Ask questions about financial filings

**Example:** *"What was Apple's revenue in 2020?"*
""")

st.markdown("---")

# Quick stats preview
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="📊 Dataset",
        value="21 Companies",
        help="2015-2020 SEC 10-K filings"
    )

with col2:
    st.metric(
        label="💰 Query Cost",
        value="~$0.01",
        help="Average cost per query"
    )

with col3:
    st.metric(
        label="⚡ Response Time",
        value="10-15s",
        help="Average processing time"
    )