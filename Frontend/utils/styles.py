import streamlit as st


def inject_global_css():
    st.markdown(
        """
        <style>
        /* Hide default Streamlit sidebar completely */
        [data-testid="stSidebar"], [data-testid="stSidebarNav"] {
            display: none !important;
        }
        [data-testid="stAppViewContainer"] > .main {
            margin-left: 0 !important;
        }

        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Inter", system-ui, sans-serif;
            background-color: #020617 !important;
        }

        .block-container {
            padding-top: 0rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }

        /* ---------------- TOP NAV ---------------- */
        .top-nav {
            position: sticky;
            top: 0;
            z-index: 999;
            padding: 0.9rem 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: radial-gradient(circle at top left, #020617 0, #020617 50%, #020617 100%);
            border-bottom: 1px solid rgba(15,23,42,0.9);
            backdrop-filter: blur(18px);
        }

        .nav-left {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            margin-top: 0.7rem;
        }
        .logo-dot {
            width: 11px;
            height: 11px;
            border-radius: 999px;
            background: linear-gradient(135deg,#22c55e,#0ea5e9);
            box-shadow: 0 0 0 6px rgba(34,197,94,0.2);
        }
        .logo-text {
            font-size: 1.2rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            color: #e2e8f0;
        }
        .logo-text span {
            color: #22c55e;
        }

        }
        /* Make nav buttons look like simple text links */
        .top-nav-btn .stButton > button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #94a3b8 !important;
        padding: 0.15rem 0.6rem !important;
        border-radius: 0 !important;
        font-size: 0.9rem !important;
    }

    .top-nav-btn .stButton > button:hover {
        color: #e5e7eb !important;
        background: rgba(15,23,42,0.7) !important;
    }

        /* ---------------- HERO ---------------- */
        @keyframes heroGradient {
          0% {background-position: 0% 50%;}
          50% {background-position: 100% 50%;}
          100% {background-position: 0% 50%;}
        }

        .hero {
        margin-top: 1.5rem;
        padding: 2.4rem 0;
        /* Make this a full-width strip, not a pill */
        border-radius: 0;          /* 🔑 no rounded pill */
        border: none;              /* 🔑 no card border */
        box-shadow: none;          /* 🔑 no raised card shadow */
        }


        .hero-title {
            margin-top: 0.2rem;
            font-size: 2.5rem;
            line-height: 1.12;
            font-weight: 750;
            letter-spacing: 0.01em;
            color: #e5e7eb;
        }
        .hero-title span {
          background: linear-gradient(120deg,#22c55e,#0ea5e9,#38bdf8);
          background-size: 220% 220%;
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
          animation: heroGradient 16s ease infinite;
        }

        .hero-subtitle {
            margin-top: 0.8rem;
            color: #cbd5f5;
            font-size: 1.0rem;
            max-width: 32rem;
            margin-bottom: 1.2rem;
        }

        .hero-footnote {
            margin-top: 0.9rem;
            font-size: 0.78rem;
            color: #94a3b8;
        }

        /* CTA button ONLY inside hero */
        .hero .stButton>button {
            padding: 0.55rem 1.3rem;
            border-radius: 999px;
            border: 0;
            background: linear-gradient(135deg,#22c55e,#0ea5e9);
            color: #020617;
            font-weight: 600;
            font-size: 0.9rem;
            box-shadow: 0 18px 40px rgba(8,47,73,0.5);
            margin-top: 1.3rem;
        }
        .hero .stButton>button:hover {
            filter: brightness(1.06);
            box-shadow: 0 22px 52px rgba(8,47,73,0.9);
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(2,minmax(0,1fr));
            gap: 0.9rem;
        }
        .metric-card {
            border-radius: 1.1rem;
            padding: 0.9rem 1.0rem;
            border: 1px solid rgba(148,163,184,0.65);
            background: radial-gradient(circle at top,#020617 0,#020617 40%,#020617 100%);
            color: #e5e7eb;
            box-shadow: 0 10px 28px rgba(15,23,42,0.9);
        }
        .metric-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: #94a3b8;
        }
        .metric-value {
            margin-top: 0.15rem;
            font-size: 1.35rem;
            font-weight: 600;
        }
        .metric-caption {
            margin-top: 0.3rem;
            font-size: 0.78rem;
            color: #9ca3af;
        }

        .section-heading {
            font-size: 1.3rem;
            font-weight: 600;
            color: #e5e7eb;
            margin-bottom: 0.4rem;
        }
        .section-sub {
            font-size: 0.9rem;
            color: #94a3b8;
            max-width: 46rem;
            margin-bottom: 1.2rem;
        }

        /* Feature bubbles */
        .feature-card {
                border-radius: 999px;
                padding: 1.5rem 1.3rem;
                margin: 1.0rem 1.0rem;
                border: 1px solid rgba(30,64,175,0.6);
                background: radial-gradient(circle at top,#020617 0,#020617 40%,#020617 100%);
                color: #e5e7eb;
                box-shadow: 0 18px 40px rgba(15,23,42,0.9);
                transition: transform 150ms ease-out, box-shadow 150ms ease-out, border-color 150ms ease-out;

                /* Centering fix */
                text-align: center;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
        }
        .feature-card:hover {
            transform: translateY(-2px) translateX(1px);
            box-shadow: 0 22px 58px rgba(8,47,73,0.95);
            border-color: rgba(34,197,94,0.8);
        }
        .feature-title {
            font-size: 0.96rem;
            font-weight: 600;
            margin-bottom: 0.2rem;
        }
        .feature-body {
            font-size: 0.86rem;
            color: #9ca3af;
        }

        /* Chat bubbles */
        .chat-bubble-user {
          background: #020617;
          color: #e5e7eb;
          padding: 0.75rem 1rem;
          border-radius: 1rem 1rem 0.25rem 1rem;
          margin-bottom: 0.4rem;
          border: 1px solid rgba(45,212,191,0.55);
        }
        .chat-bubble-ai {
          background: #020617;
          color: #e5e7eb;
          padding: 0.75rem 1rem;
          border-radius: 1rem 1rem 1rem 0.25rem;
          margin-bottom: 0.4rem;
          border: 1px solid rgba(59,130,246,0.6);
        }
        .chat-meta {
          font-size: 0.7rem;
          color: #94a3b8;
          margin-bottom: 0.08rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
