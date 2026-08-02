# ModelPipeline\serving\frontend\components\styles.py
import streamlit as st

from components.answer_render import palette_css


def inject_global_css():
    """Inject global CSS for FinSight / FinSights UI."""

    # Font Awesome
    st.markdown(
        """
        <link rel="stylesheet"
              href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
        """,
        unsafe_allow_html=True,
    )

    # Per-company chip colours and entrance delays, generated from the single
    # palette definition in answer_render.py. Kept in its own <style> block so the
    # large literal stylesheet below stays a plain (non-f) string.
    st.markdown(f"<style>{palette_css()}</style>", unsafe_allow_html=True)

    st.markdown(
        """
        <style>
        /* =======================================================================
           BASE THEME & LAYOUT
           ======================================================================= */

        #MainMenu { visibility: hidden; }
        footer   { visibility: hidden; }
        header   { visibility: hidden; }

        [data-testid="stSidebar"],
        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        .stApp {
            background-color: #040008 !important; /* deep blue-violet */
        }

        .main .block-container {
            max-width: 1200px;
            margin: 0 auto;
            padding-left: 2rem;
            padding-right: 2rem;
        }

        /* Text colours */
        .stMarkdown, .stText, p, span, div, li {
            color: #e5e7eb !important; /* slate-200 */
        }

        h1, h2, h3, h4, h5, h6 {
            color: #f8fafc !important; /* slate-50 */
        }

        /* =======================================================================
           HERO & GRADIENT TEXT
           ======================================================================= */

        .hero-headline {
            font-size: 2.8rem;
            line-height: 1.15;
            margin-bottom: 1.5rem;
            font-weight: 700;
        }

        .gradient-text {
            background: linear-gradient(
                90deg,
                #22c55e 0%,
                #0ea5e9 25%,
                #38bdf8 50%,
                #22c55e 75%,
                #0ea5e9 100%
            );
            background-size: 400% 400%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: gradientFlow 22s linear infinite;
            font-weight: 700;
            display: inline-block;
        }

        @keyframes gradientFlow {
            0%   { background-position:   0% 50%; }
            100% { background-position: 400% 50%; }
        }

        /* =======================================================================
           HERO METRICS (right-hand column)
           ======================================================================= */

        [data-testid="stMetric"] {
            background: rgba(4, 0, 8, 0.9) !important;
            padding: 1.3rem !important;
            border-radius: 24px !important;
            border: 1.5px solid rgba(59, 130, 246, 0.4) !important;
            box-shadow:
                0 8px 32px rgba(0, 0, 0, 0.7),
                0 0 24px rgba(59, 130, 246, 0.3) !important;
            transition: all 0.3s ease !important;
        }

        [data-testid="stMetric"]:hover {
            transform: translateY(-5px) scale(1.03) !important;
            box-shadow:
                0 16px 48px rgba(0, 0, 0, 0.8),
                0 0 32px rgba(34, 197, 94, 0.35) !important;
            border-color: rgba(34, 197, 94, 0.5) !important;
        }

        [data-testid="stMetricLabel"] {
            color: #94a3b8 !important;
            font-size: 0.75rem !important;
            text-transform: uppercase !important;
            letter-spacing: 0.08em !important;
            font-weight: 600 !important;
        }

        [data-testid="stMetricValue"] {
            color: #f8fafc !important;
            font-size: 1.5rem !important;
            font-weight: 700 !important;
        }

        /* =======================================================================
           BUTTONS
           ======================================================================= */

        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #22c55e, #0ea5e9) !important;
            color: #020617 !important;
            font-weight: 700 !important;
            border: none !important;
            padding: 0.65rem 2rem !important;
            border-radius: 12px !important;
            box-shadow: 0 8px 24px rgba(34, 197, 94, 0.35) !important;
            transition: all 0.3s ease !important;
            font-size: 1rem !important;
        }

        .stButton > button[kind="primary"]:hover {
            transform: translateY(-3px) scale(1.02) !important;
            box-shadow: 0 12px 32px rgba(34, 197, 94, 0.5) !important;
            filter: brightness(1.08) !important;
        }

        .stButton > button[kind="secondary"] {
            background: rgba(4, 0, 8, 0.6) !important;
            color: #e5e7eb !important;
            border: 1px solid rgba(148, 163, 184, 0.3) !important;
            border-radius: 10px !important;
            transition: all 0.3s ease !important;
        }

        .stButton > button[kind="secondary"]:hover {
            border-color: rgba(34, 197, 94, 0.6) !important;
            transform: translateY(-2px) !important;
        }

        /* =======================================================================
           NAVIGATION (logo)
           ======================================================================= */

        .nav-logo {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            margin-bottom: 1rem;
        }

        .logo-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: linear-gradient(135deg, #22c55e, #0ea5e9);
            box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.2);
        }

        .logo-text {
            font-size: 1.4rem;
            font-weight: 700;
            color: #e2e8f0;
            letter-spacing: 0.02em;
        }

        .logo-text .highlight {
            color: #22c55e;
        }

        /* =======================================================================
           ICONS (Font Awesome for metrics & cards)
           ======================================================================= */

        .feature-icon {
            font-size: 2.2rem;
            color: #22c55e;
            margin-bottom: 0.8rem;
            display: block;
            filter: drop-shadow(0 0 12px rgba(34, 197, 94, 0.5));
        }

        /* =======================================================================
        FEATURE CARDS – 6 cards in a responsive flexbox grid
        ======================================================================= */

        .feature-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 2rem;
            margin-top: 2.5rem;
        }

        /* 3 per row on desktop, wrap as needed */
        .feature-card {
            flex: 1 1 calc(33.333% - 2rem);
            min-width: 260px;

            background: rgba(4, 0, 8, 0.9);
            border: 1.5px solid rgba(59, 130, 246, 0.5);
            border-radius: 40px;
            padding: 1.8rem 1.6rem;

            box-shadow:
                0 10px 40px rgba(0, 0, 0, 0.8),
                0 0 30px rgba(59, 130, 246, 0.4),
                0 0 60px rgba(59, 130, 246, 0.2),
                inset 0 1px 0 rgba(255, 255, 255, 0.05);
            transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .feature-card:hover {
            transform: translateY(-10px) scale(1.04);
            box-shadow:
                0 24px 60px rgba(0, 0, 0, 0.9),
                0 0 40px rgba(34, 197, 94, 0.5),
                0 0 80px rgba(34, 197, 94, 0.25),
                inset 0 1px 0 rgba(255, 255, 255, 0.1);
            border-color: rgba(34, 197, 94, 0.7);
        }

        /* Icon + heading row inside card */
        .feature-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }

        .feature-card-header h4 {
            margin: 0;
            font-size: 1.05rem;
        }

        /* Inline icon inside card header */
        .feature-icon-inline {
            font-size: 1.6rem;
            color: #22c55e;
            flex-shrink: 0;
            filter: drop-shadow(0 0 10px rgba(34, 197, 94, 0.5));
        }

        /* Body text inside cards */
        .feature-card p {
            margin: 0;
            font-size: 0.95rem;
            line-height: 1.5;
        }

        /* Responsive tweaks: 2 per row on medium, 1 per row on small */
        @media (max-width: 960px) {
            .feature-card {
                flex: 1 1 calc(50% - 2rem);
            }
        }

        @media (max-width: 640px) {
            .feature-card {
                flex: 1 1 100%;
            }
        }


        /* =======================================================================
           DIVIDERS & CAPTIONS
           ======================================================================= */

        hr {
            border-color: rgba(148, 163, 184, 0.1) !important;
            margin: 3rem 0 !important;
        }

        .stCaption {
            color: #64748b !important;
            text-align: center !important;
        }
        
        /* =======================================================================
           CHATBOT PAGE STYLING - ChatGPT-style narrow interface
           ======================================================================= */
        
        /* Chat container for chatbot page - wide enough to lose the dead
           margins on large monitors, capped short of a full-width sprawl
           so long financial paragraphs stay comfortable to read. */
        body:has([data-testid="stChatInput"]) .main .block-container {
            max-width: 900px !important;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
        }
        
        /* Chat message bubbles with distinct colors */
        [data-testid="stChatMessage"] {
            padding: 1rem 1.2rem !important;
            border-radius: 16px !important;
            margin-bottom: 1rem !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
            border: 1px solid transparent !important;
        }
        
        /* User messages - green accent */
        [data-testid="stChatMessage"]:has([aria-label="user"]) {
            background: rgba(34, 197, 94, 0.08) !important;
            border-color: rgba(34, 197, 94, 0.3) !important;
        }
        
        /* Assistant messages - blue accent */
        [data-testid="stChatMessage"]:has([aria-label="assistant"]) {
            background: rgba(59, 130, 246, 0.08) !important;
            border-color: rgba(59, 130, 246, 0.3) !important;
        }
        
        /* Chat input bar */
        [data-testid="stChatInput"] {
            border-radius: 12px !important;
            border: 1px solid rgba(148, 163, 184, 0.3) !important;
            background: rgba(4, 0, 8, 0.6) !important;
        }
        
        [data-testid="stChatInput"]:focus-within {
            border-color: rgba(34, 197, 94, 0.5) !important;
            box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.1) !important;
        }
        
        /* Sidebar visibility for chatbot */
        body:has([data-testid="stChatInput"]) [data-testid="stSidebar"] {
            display: block !important;
        }
        
        /* Sidebar styling */
        [data-testid="stSidebar"] {
            background: rgba(4, 0, 8, 0.95) !important;
            border-right: 1px solid rgba(148, 163, 184, 0.1) !important;
        }
        
        /* Sidebar content */
        [data-testid="stSidebar"] .stMarkdown h3 {
            font-size: 1.1rem !important;
            margin-bottom: 0.8rem !important;
            margin-top: 1rem !important;
        }
        
        /* Sidebar expanders */
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            background: rgba(4, 0, 8, 0.6) !important;
            border: 1px solid rgba(148, 163, 184, 0.2) !important;
            border-radius: 8px !important;
            margin-bottom: 0.5rem !important;
        }

        /* =======================================================================
           ANSWER TYPOGRAPHY
           Long-form financial prose - the answers run 500-2000 words, so reading
           comfort matters more here than density.
           ======================================================================= */

        [data-testid="stChatMessage"] .stMarkdown p {
            line-height: 1.72 !important;
            margin-bottom: 0.85rem !important;
        }

        [data-testid="stChatMessage"] .stMarkdown strong {
            color: #f8fafc !important;
            font-weight: 650 !important;
        }

        /* =======================================================================
           SOURCE CHIPS  (components/answer_render.py)
           Each chip carries ticker / fiscal year / 10-K item. Per-chip colour is
           injected inline as --fs-bg / --fs-bd / --fs-fg so one rule serves all
           companies.
           ======================================================================= */

        @keyframes fsFadeUp {
            from { opacity: 0; transform: translateY(7px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        @keyframes fsSheen {
            0%   { background-position: 0% 50%; }
            100% { background-position: 200% 50%; }
        }

        @keyframes fsPulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50%      { opacity: 0.55; transform: scale(0.82); }
        }

        .fs-sources {
            margin: 1.1rem 0 0.2rem 0;
            padding-top: 0.95rem;
            position: relative;
            animation: fsFadeUp 0.42s cubic-bezier(0.22, 1, 0.36, 1) both;
        }

        /* Gradient hairline instead of a flat grey rule - green bleeding into blue,
           the same two-stop identity used by the logo and primary buttons. */
        .fs-sources::before {
            content: "";
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 1px;
            background: linear-gradient(90deg,
                rgba(34, 197, 94, 0.55) 0%,
                rgba(14, 165, 233, 0.45) 45%,
                rgba(148, 163, 184, 0.06) 100%);
        }

        .fs-sources-head {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
            margin-bottom: 0.7rem;
        }

        .fs-sources-title {
            font-size: 0.72rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            color: #94a3b8 !important;
        }

        .fs-sources-meta {
            font-size: 0.72rem !important;
            color: #64748b !important;
            font-variant-numeric: tabular-nums;
        }

        .fs-group {
            margin-bottom: 0.75rem;
            animation: fsFadeUp 0.44s cubic-bezier(0.22, 1, 0.36, 1) both;
            animation-delay: var(--fs-delay, 0ms);
        }

        .fs-group-topic {
            display: flex;
            align-items: flex-start;
            gap: 0.45rem;
            margin-bottom: 0.4rem;
        }

        .fs-group-num {
            flex: 0 0 auto;
            min-width: 1.15rem;
            height: 1.15rem;
            padding: 0 0.25rem;
            border-radius: 5px;
            background: linear-gradient(140deg,
                rgba(34, 197, 94, 0.22) 0%,
                rgba(14, 165, 233, 0.20) 100%) !important;
            border: 1px solid rgba(34, 197, 94, 0.22);
            color: #e2e8f0 !important;
            font-size: 0.66rem !important;
            font-weight: 700 !important;
            line-height: 1.05rem !important;
            text-align: center;
            font-variant-numeric: tabular-nums;
            transition: box-shadow 0.2s ease, transform 0.2s ease;
        }

        .fs-group:hover .fs-group-num {
            transform: scale(1.08);
            box-shadow: 0 0 12px -1px rgba(34, 197, 94, 0.55);
        }

        .fs-group-topic { transition: transform 0.2s ease; }

        .fs-group-label {
            font-size: 0.82rem !important;
            font-weight: 600 !important;
            color: #cbd5e1 !important;
            line-height: 1.3 !important;
        }

        .fs-group-extra {
            font-size: 0.75rem !important;
            color: #64748b !important;
            margin: 0.15rem 0 0 1.6rem;
        }

        .fs-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 0.32rem;
            margin-left: 1.6rem;
        }

        .fs-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            padding: 0.18rem 0.55rem;
            border-radius: 999px;
            background: var(--fs-bg) !important;
            border: 1px solid var(--fs-bd) !important;
            font-size: 0.7rem !important;
            line-height: 1.35 !important;
            white-space: nowrap;
            cursor: default;
            will-change: transform;
            transition: transform 0.2s cubic-bezier(0.22, 1, 0.36, 1),
                        box-shadow 0.2s ease,
                        border-color 0.2s ease,
                        filter 0.2s ease;
        }

        /* Hover zoom + coloured bloom, so the chip lifts off the page rather than
           just brightening. The glow colour is the company's own hue. */
        .fs-chip:hover {
            transform: translateY(-2px) scale(1.055);
            box-shadow: 0 4px 16px -2px var(--fs-glow, rgba(34, 197, 94, 0.35)),
                        0 0 0 1px var(--fs-glow, rgba(34, 197, 94, 0.35));
            border-color: var(--fs-fg) !important;
            filter: brightness(1.13) saturate(1.1);
            z-index: 2;
        }

        /* Small leading dot in the company colour - a visual anchor that makes a
           row of chips scannable by hue before the text is even read. */
        .fs-chip .fs-chip-dot {
            width: 5px;
            height: 5px;
            border-radius: 50%;
            flex: 0 0 auto;
            background: var(--fs-fg);
            box-shadow: 0 0 6px var(--fs-glow, transparent);
            transition: box-shadow 0.2s ease;
        }

        .fs-chip:hover .fs-chip-dot {
            box-shadow: 0 0 10px 1px var(--fs-fg);
        }

        .fs-chip .fs-chip-t {
            color: var(--fs-fg) !important;
            font-weight: 700 !important;
            letter-spacing: 0.02em;
            font-size: 0.7rem !important;
        }

        .fs-chip .fs-chip-y,
        .fs-chip .fs-chip-s {
            color: #cbd5e1 !important;
            font-weight: 500 !important;
            font-size: 0.7rem !important;
        }

        .fs-chip .fs-chip-y { font-variant-numeric: tabular-nums; }

        .fs-chip .fs-chip-sep {
            color: rgba(148, 163, 184, 0.5) !important;
            font-size: 0.7rem !important;
        }

        .fs-chip-kpi .fs-chip-t {
            font-weight: 600 !important;
            letter-spacing: 0.04em;
        }

        /* =======================================================================
           STAT STRIP + DETAIL ROWS  (metrics.py)
           ======================================================================= */

        .fs-stats {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.9rem 0 0.15rem 0;
            animation: fsFadeUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.12s both;
        }

        .fs-stat {
            flex: 1 1 auto;
            min-width: 92px;
            padding: 0.45rem 0.7rem;
            border-radius: 10px;
            position: relative;
            overflow: hidden;
            background: linear-gradient(160deg,
                rgba(148, 163, 184, 0.10) 0%,
                rgba(148, 163, 184, 0.045) 100%) !important;
            border: 1px solid rgba(148, 163, 184, 0.16) !important;
            cursor: default;
            will-change: transform;
            transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1),
                        border-color 0.22s ease,
                        box-shadow 0.22s ease,
                        background 0.22s ease;
        }

        .fs-stat:hover {
            transform: translateY(-3px);
            background: linear-gradient(160deg,
                rgba(148, 163, 184, 0.16) 0%,
                rgba(148, 163, 184, 0.07) 100%) !important;
            border-color: rgba(148, 163, 184, 0.34) !important;
            box-shadow: 0 8px 22px -8px rgba(2, 6, 23, 0.9);
        }

        /* Light sweeps across the tile on hover - the "fluid" cue, not a loop, so
           it never becomes visual noise while reading. */
        .fs-stat::after {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(105deg,
                transparent 35%,
                rgba(255, 255, 255, 0.07) 50%,
                transparent 65%);
            background-size: 200% 100%;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.22s ease;
        }

        .fs-stat:hover::after {
            opacity: 1;
            animation: fsSheen 0.85s ease-out;
        }

        .fs-stat-l {
            font-size: 0.62rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.085em;
            text-transform: uppercase;
            color: #64748b !important;
            margin-bottom: 0.12rem;
        }

        .fs-stat-v {
            font-size: 0.83rem !important;
            font-weight: 650 !important;
            color: #e2e8f0 !important;
            font-variant-numeric: tabular-nums;
            overflow-wrap: anywhere;
        }

        /* The two tiles worth colouring: which model answered, and what it cost.
           Blue for model, green for cost - the same two identity stops. */
        .fs-stat-model {
            border-color: rgba(14, 165, 233, 0.32) !important;
            background: linear-gradient(160deg,
                rgba(14, 165, 233, 0.13) 0%,
                rgba(14, 165, 233, 0.045) 100%) !important;
        }
        .fs-stat-model .fs-stat-v {
            color: #38bdf8 !important;
            text-shadow: 0 0 14px rgba(56, 189, 248, 0.4);
        }
        .fs-stat-model:hover {
            border-color: rgba(56, 189, 248, 0.75) !important;
            box-shadow: 0 8px 24px -8px rgba(14, 165, 233, 0.5);
        }

        .fs-stat-cost {
            border-color: rgba(34, 197, 94, 0.32) !important;
            background: linear-gradient(160deg,
                rgba(34, 197, 94, 0.13) 0%,
                rgba(34, 197, 94, 0.045) 100%) !important;
        }
        .fs-stat-cost .fs-stat-v {
            color: #22c55e !important;
            text-shadow: 0 0 14px rgba(34, 197, 94, 0.4);
        }
        .fs-stat-cost:hover {
            border-color: rgba(34, 197, 94, 0.75) !important;
            box-shadow: 0 8px 24px -8px rgba(34, 197, 94, 0.5);
        }

        .fs-pills {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            margin-bottom: 0.85rem;
        }

        .fs-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.2rem 0.55rem;
            border-radius: 999px;
            font-size: 0.72rem !important;
            font-weight: 600 !important;
            cursor: default;
        }

        .fs-pill-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            flex: 0 0 auto;
        }

        .fs-pill {
            transition: transform 0.2s cubic-bezier(0.22, 1, 0.36, 1),
                        box-shadow 0.2s ease, border-color 0.2s ease;
        }

        .fs-pill:hover { transform: translateY(-1px) scale(1.04); }

        .fs-pill-on {
            background: rgba(34, 197, 94, 0.12) !important;
            border: 1px solid rgba(34, 197, 94, 0.4) !important;
            color: #22c55e !important;
        }

        .fs-pill-on:hover {
            border-color: rgba(34, 197, 94, 0.85) !important;
            box-shadow: 0 4px 14px -3px rgba(34, 197, 94, 0.5);
        }

        /* Slow pulse on the active dot - reads as "this supply line fired", the one
           place a looping animation earns its keep. */
        .fs-pill-on .fs-pill-dot {
            background: #22c55e;
            box-shadow: 0 0 7px rgba(34, 197, 94, 0.9);
            animation: fsPulse 2.4s ease-in-out infinite;
        }

        .fs-pill-off {
            background: rgba(148, 163, 184, 0.08) !important;
            border: 1px solid rgba(148, 163, 184, 0.22) !important;
            color: #64748b !important;
        }
        .fs-pill-off .fs-pill-dot { background: #475569; }

        .fs-det-h {
            font-size: 0.66rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            color: #64748b !important;
            margin: 0.2rem 0 0.45rem 0;
        }

        .fs-det-row {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.32rem 0.4rem;
            border-radius: 6px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.09);
            transition: background 0.18s ease, padding-left 0.18s ease;
        }

        .fs-det-row:hover {
            background: rgba(34, 197, 94, 0.06);
            padding-left: 0.62rem;
        }

        .fs-det-row:last-child { border-bottom: none; }

        .fs-det-k {
            font-size: 0.75rem !important;
            color: #94a3b8 !important;
        }

        .fs-det-v {
            font-size: 0.75rem !important;
            color: #e2e8f0 !important;
            font-variant-numeric: tabular-nums;
            text-align: right;
            overflow-wrap: anywhere;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )