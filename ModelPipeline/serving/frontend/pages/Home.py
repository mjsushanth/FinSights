# frontend/pages/1_Home.py
"""
FinSight Home Page - Product landing page with features and examples.

Uses pure Streamlit components (no HTML/CSS injection):
- st.columns() for layout
- st.metric() for stats
- st.container() for sections
- st.button() for navigation
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
from sidebar import render_sidebar
from config import BACKEND_URL, API_TIMEOUT

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="FinSight - Home",
    page_icon="💹",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
# HERO SECTION
# ============================================================================

st.title("💹 FinSight")

# Two-column layout for hero
hero_left, hero_right = st.columns([3, 2], gap="large")

with hero_left:
    st.markdown("## Markets shouldn't overwhelm — **filings should explain**")
    
    st.markdown("""
    FinSight turns raw SEC 10-K filings into a question-and-answer surface for your research.
    Ask questions, surface KPIs, and trace every answer back to the underlying text in seconds.
    """)
    
    # CTA button (FIXED: No emoji in filename)
    # if st.button("🚀 Try the 10-K Chatbot", type="primary", use_container_width=True):
    #     st.switch_page("pages/2_Chatbot.py")
    
    st.caption("💡 No trading advice, just transparent, document-grounded answers.")

with hero_right:
    # Metrics grid using native st.metric()
    metric_col1, metric_col2 = st.columns(2)
    
    with metric_col1:
        st.metric(
            label="⚡ Research Speed",
            value="Faster",
            delta="vs. manual reading",
            help="From first question to key insights"
        )
        st.metric(
            label="📊 Section Coverage",
            value="Core SEC Items",
            help="Risk Factors, Business, MD&A & more"
        )
    
    with metric_col2:
        st.metric(
            label="🔍 Traceability",
            value="100%",
            delta="Citations included",
            help="Every response cites filing sections"
        )
        st.metric(
            label="📄 Filings",
            value="10-K",
            delta="10-Q & 8-K coming",
            help="Annual reports currently supported"
        )

st.markdown("---")

# ============================================================================
# FEATURES SECTION
# ============================================================================

st.markdown("## What FinSight Unlocks")
st.markdown("""
A clean, question-and-answer layer on top of SEC filings — built for analysts, 
PMs, and research teams who rely on 10-K disclosures.
""")

# Feature cards in 3-column grid
features = [
    {
        "title": "🔍 Context-Aware Filing Q&A",
        "description": "Ask questions in plain language and get answers grounded in 10-K text, not generic model memory."
    },
    {
        "title": "📑 Section-Level Insights",
        "description": "Quickly access Risk Factors, Business Overview, and MD&A, all parsed into clean sections."
    },
    {
        "title": "📊 Risk & Narrative Summarization",
        "description": "Generate concise summaries of dense sections, tied back to their source paragraphs."
    },
    {
        "title": "✅ Citation-First Answers",
        "description": "Every response includes filing-level references so you know where information came from."
    },
    {
        "title": "🏢 Multi-Company Support",
        "description": "Ask about any supported filing — Apple 2023, Google 2020, Microsoft 2022."
    },
    {
        "title": "⚖️ Compliance-Aware Design",
        "description": "Clear document references supporting internal review and transparent research."
    }
]

# Display features in rows of 3
for i in range(0, len(features), 3):
    cols = st.columns(3)
    for j, col in enumerate(cols):
        if i + j < len(features):
            feature = features[i + j]
            with col:
                with st.container(border=True):
                    st.markdown(f"### {feature['title']}")
                    st.markdown(feature['description'])

st.markdown("---")

# ============================================================================
# EXAMPLE QUESTIONS
# ============================================================================

st.markdown("## 💡 Example Questions")

example_cols = st.columns(2)

with example_cols[0]:
    st.markdown("**Quick Queries:**")
    st.markdown("""
    - "What is Google's Revenue for 2023?"
    - "What strategic priorities did Amazon outline for 2023?"
    - "Show me Apple's gross margins for 2020-2023"
    """)

with example_cols[1]:
    st.markdown("**Complex Analysis:**")
    st.markdown("""
    - "What drove Apple's revenue and margin changes in 2023?"
    - "How did Microsoft's Cloud segment perform vs. last year?"
    - "Compare Netflix and Disney's subscription risks in 2022"
    """)

st.markdown("---")

# ============================================================================
# DATASET INFO
# ============================================================================

with st.expander("📂 Dataset Coverage", expanded=False):
    info_col1, info_col2 = st.columns(2)
    
    with info_col1:
        st.markdown("**Current Coverage:**")
        st.markdown("""
        - Companies: 21 companies
        - Years: 2015-2020
        - Document Types: 10-K annual filings
        - Sentences: 469K+ indexed
        """)
    
    with info_col2:
        st.markdown("**Coming Soon:**")
        st.markdown("""
        - Expanded company coverage (S&P 500)
        - Extended timeline (2006-2024)
        - 10-Q quarterly reports
        - 8-K current reports
        """)

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
footer_col1, footer_col2, footer_col3 = st.columns([1, 2, 1])

with footer_col2:
    st.caption("FinSight v1.0 | IE7374 MLOps Capstone Project")
    st.caption("Built with Streamlit + FastAPI + AWS Bedrock")