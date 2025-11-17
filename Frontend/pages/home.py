
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
                Finsights turns raw 10-K filings into a question and answer surface for your research.
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
                    <div class="metric-value">Faster Research</div>
                    <div class="metric-caption">From first question to key insights.</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Section coverage</div>
                    <div class="metric-value">Core SEC Items</div>
                    <div class="metric-caption">Risk Factors, Business Overview, MD&A & more.</div>
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
            A clean, question-and-answer layer on top of SEC filings — built for analysts, PMs, and research teams who rely on 10-K disclosures.
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
            "Section-level Insights",
            "Quickly access the most important parts of a filing, including Risk Factors, Business Overview, and MD&A, all parsed into clean sections.",
        ),
        (
            "Risk & narrative summarization",
            "Generate concise summaries of dense sections like Risk Factors or MD&A, tied back to their source paragraphs.",
        ),
        (
            "Citation-first answers",
            "Every response includes filing-level references so you always know exactly where the information came from.",
        ),
        (
            "Multi-company support",
            "Ask about any supported filing — Apple 2023, Google 2020, Microsoft 2022 — and get a section-grounded answer each time.",
        ),
        (
            "Compliance-aware design",
            "Each answer provides clear document references, supporting internal review and transparent research documentation.",
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
        - “What drove Apple's revenue and margin changes in its 2023 annual report?”  
        - “How did Microsoft's Cloud and Productivity segments perform compared to last year?”  
        - “What strategic priorities did Amazon outline for the coming year in its annual filing?”  
        """,
        unsafe_allow_html=True,
    )
