
import streamlit as st


def render_home():
    # HERO
    st.markdown('<div class="hero">', unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown(
            """
            <div class="hero-title">
                Markets shouldn't overwhelm — <span>filings should explain</span>.
            </div>
            <div class="hero-subtitle">
                Finsights turns raw 10-K filings into a conversational surface for your research.
                Ask questions, surface KPIs, and trace every answer back to the underlying text
                in seconds.
            </div>
            """,
            unsafe_allow_html=True,
        )

        cta = st.button("Try the 10-K chatbot →", key="hero_chat_button")
        if cta:
            st.session_state.page = "Chatbot"
            st.rerun()


        st.markdown(
            """
            <div class="hero-footnote">
                No trading advice, just transparent, document-grounded answers.
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_right:
        st.markdown(
            """
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">Time saved / 10-K</div>
                    <div class="metric-value">60–80%</div>
                    <div class="metric-caption">From first question to key takeaways.</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">KPI coverage</div>
                    <div class="metric-value">50+ KPIs</div>
                    <div class="metric-caption">Margins, cash flow, leverage & more.</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Answer traceability</div>
                    <div class="metric-value">100%</div>
                    <div class="metric-caption">Every response cites filing sections.</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Filings supported</div>
                    <div class="metric-value">10-K</div>
                    <div class="metric-caption">10-Q & 8-K on the near-term roadmap.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)  # close hero

    st.markdown("---")

    # FEATURES
    st.markdown(
        """
        <div class="section-heading">What Finsights unlocks</div>
        <div class="section-sub">
            A single conversational surface on top of your SEC filing pipeline—built for analysts,
            PMs, and research teams who live in 10-Ks.
        </div>
        """,
        unsafe_allow_html=True,
    )

    features = [
        (
            "Context-aware filing Q&A",
            "Ask questions in plain language and get answers grounded in 10-K text, "
            "not a generic model memory.",
        ),
        (
            "KPI-first analytics",
            "Surface revenue, margin, capex and leverage KPIs as structured views you can "
            "export or plug into dashboards.",
        ),
        (
            "Risk & footnote summarization",
            "Summarize Risk Factors, MD&A and footnotes into precise narratives with direct "
            "links back to the original sections.",
        ),
        (
            "Citation-first answers",
            "Every answer includes filing-level references, so you always know exactly where "
            "numbers and claims come from.",
        ),
        (
            "Portfolio-ready workflows",
            "Switch between company deep dives and portfolio-wide KPI comparisons in a single interface.",
        ),
        (
            "Compliance-aware design",
            "Keep a clear audit trail of prompts, responses and document references for internal review.",
        ),
    ]

    for row in [features[:3], features[3:]]:
        cols = st.columns(3)
        for col, (title, body) in zip(cols, row):
            col.markdown(
                f"""
                <div class="feature-card">
                    <div class="feature-title">{title}</div>
                    <div class="feature-body">{body}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # Example questions only
    st.markdown("### Example questions")
    st.markdown(
        """
        - “What is Google's Revenue for 2023?”  
        - “Summarize the **top 3 risk factors** and how they evolved versus last year.”  
        - “What does management say about **free cash flow priorities**?”  
        - “How does **net leverage** today compare to three years ago?”  
        """,
        unsafe_allow_html=True,
    )
