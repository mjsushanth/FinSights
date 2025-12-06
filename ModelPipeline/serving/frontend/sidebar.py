# frontend/sidebar.py
"""
Shared sidebar component for FinSight.

Renders consistent sidebar across all pages:
- System health check
- Statistics (queries, cost)
- About section
- Example questions
- Clear chat button

Usage:
    from sidebar import render_sidebar
    render_sidebar(client)
"""

import streamlit as st
from api_client import FinSightClient
from state import set_backend_health, clear_chat_history
from metrics import display_sidebar_stats


def render_sidebar(client: FinSightClient) -> None:
    """
    Render complete sidebar with all sections.
    
    Args:
        client: FinSightClient instance for health checks
    """
    print("🔍 DEBUG: render_sidebar() called!")

    with st.sidebar:
        st.write("🔍 DEBUG: Inside st.sidebar block")
        
        st.title("💹 FinSight")
        st.markdown("**Financial Document Intelligence**")
        st.markdown("---")
        
        # ====================================================================
        # SYSTEM STATUS
        # ====================================================================
        st.markdown("### 🔧 System Status")
        
        if st.button("🔄 Check Backend", use_container_width=True):
            with st.spinner("Checking backend..."):
                health = client.health_check()
                
                if health.get("status") == "healthy":
                    set_backend_health(True)
                    st.success("✅ Backend: Healthy")
                else:
                    set_backend_health(False)
                    st.error(f"❌ Backend: {health.get('error', 'Offline')}")
        
        # Display current status
        backend_healthy = st.session_state.get("backend_healthy")
        if backend_healthy is True:
            st.success("✅ Backend: Online")
        elif backend_healthy is False:
            st.error("❌ Backend: Offline")
        else:
            st.info("⚠️ Status: Unknown")
        
        st.markdown("---")
        
        # ====================================================================
        # STATISTICS
        # ====================================================================
        display_sidebar_stats()
        
        st.markdown("---")
        
        # ====================================================================
        # CLEAR CHAT BUTTON
        # ====================================================================
        if st.button("🗑️ Clear Chat History", use_container_width=True):
            clear_chat_history()
            st.rerun()
        
        st.markdown("---")
        
        # ====================================================================
        # ABOUT SECTION
        # ====================================================================
        with st.expander("ℹ️ About", expanded=False):
            st.markdown("""
            **FinSight** - Financial Document Intelligence System
            
            Analyzes SEC 10-K filings using hybrid retrieval architecture.
            
            **Core Capabilities:**
            - **Data**: SEC Edgar 10-K filings (sentence-level)
            - **RAG Search**: Semantic retrieval via AWS S3 Vectors
            - **Entity/Metadata/KPI**: Financial metrics from EdgarTools
            - **LLM Synthesis**: Powered by Claude (AWS Bedrock)
            - **Embeddings**: Cohere v4
            - **Storage**: Parquet-based (99% cost savings vs. managed DBs)
            - **Query Cost**: ~$0.01 per query
            
            **Dataset Coverage:**
            - Companies: 21 companies (2015-2020)
            - Document Types: 10-K annual filings
            - Sentences: 469K+ indexed
            
            **Project:** IE7374 MLOps Capstone | Northeastern University
            """)
        
        st.markdown("---")
        
        # ====================================================================
        # EXAMPLE QUESTIONS
        # ====================================================================
        with st.expander("💡 Example Questions", expanded=False):
            st.markdown("""
            **Complex Analysis:**
            
            *"Across its fiscal 2018-2020 10-K filings, how does Walmart Inc. explain the main drivers behind changes in its long-term debt and related cash flows from financing activities?"*
            
            *"In their 2020 Form 10-K risk-factor disclosures, how do Radian Group, Netflix and Mastercard each describe their exposure to data protection, information security and customer privacy risks?"*
            
            **Comparative Metrics:**
            
            *"How does MICROSOFT CORP describe the change in its Intelligent Cloud revenue in 2017, including both the direction and magnitude of the change?"*
            
            *"Show me Apple, Microsoft, Amazon, Alphabet, Google, and Tesla's financial performance from 2018 to 2022. I need their total sales, bottom line profits, operating cash flows, gross margins, total debt levels, shareholder equity, cost of goods sold, tax expenses, return on assets, and earnings per share."*
            
            **Quick Queries:**
            
            *"What is Google's Revenue for 2023?"*
            
            *"What strategic priorities did Amazon outline for 2023?"*
            
            *"Show me Apple's gross margins for 2020-2023"*
            
            **Guidelines:**
            - 10-500 characters
            - Takes 10-15 seconds
            - Cost: ~$0.017/query
            """)