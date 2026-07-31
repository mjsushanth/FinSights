# ModelPipeline\serving\frontend\metrics.py
"""
RESPONSIBILITIES:
✓ Display LLM metadata (tokens, cost, model)
✓ Show context metadata (length, sentence count)
✓ Render KPI/RAG flags
✓ Format processing time

DISPLAY PATTERN:
- st.expander("Query Details") for collapsible metadata
- Formatted tables or metrics for key stats
- Cost tracking (per-query and cumulative)

"""


# frontend/metrics.py
"""
Metrics display components for FinSight frontend.

Handles rendering of query metadata, cost tracking, and performance stats.

Usage:
    from frontend.metrics import display_query_metadata, display_sidebar_stats
    
    display_query_metadata(metadata)
    display_sidebar_stats()
"""

# frontend/metrics.py
"""
Metrics display components for FinSight frontend.

Handles rendering of query metadata, cost tracking, and performance stats.

Usage:
    from metrics import display_query_metadata, display_sidebar_stats
    
    display_query_metadata(metadata)
    display_sidebar_stats()
"""

import html
import re
import streamlit as st
from typing import Dict, Any, Optional

# Strips the trailing release date and version from a Bedrock model name, e.g.
# "claude-haiku-4-5-20251001-v1" -> "claude-haiku-4-5". The full id stays in the
# tooltip so nothing is actually hidden.
_MODEL_TAIL = re.compile(r"-\d{6,8}-v\d+$")


def shorten_model_id(model_id: str) -> str:
    """
    Reduce a Bedrock model id to a readable name.

    Bedrock ids look like "us.anthropic.claude-haiku-4-5-20251001-v1:0". The ":0"
    is a version and "us."/"anthropic." are routing/vendor prefixes. Splitting on
    ":" alone returns the version, which previously rendered as "Model: 0".
    """
    if not model_id:
        return "Unknown"
    name = model_id.split(":")[0].split(".")[-1] or model_id
    return _MODEL_TAIL.sub("", name) or name


def _stat_tile(label: str, value: str, tooltip: str = "", accent: str = "") -> str:
    """One compact stat tile. Values are escaped - some originate from the model."""
    title = f' title="{html.escape(tooltip)}"' if tooltip else ""
    cls = f"fs-stat fs-stat-{accent}" if accent else "fs-stat"
    return (
        f'<div class="{cls}"{title}>'
        f'<div class="fs-stat-l">{html.escape(label)}</div>'
        f'<div class="fs-stat-v">{html.escape(value)}</div>'
        "</div>"
    )


def _pill(label: str, on: bool) -> str:
    """A boolean capability pill, used for the KPI / RAG supply-line flags."""
    state = "on" if on else "off"
    mark = "active" if on else "not used"
    return (
        f'<span class="fs-pill fs-pill-{state}" title="{html.escape(label)}: {mark}">'
        f'<span class="fs-pill-dot"></span>{html.escape(label)}'
        "</span>"
    )


def display_query_metadata(metadata: Dict[str, Any]) -> None:
    """
    Display query metadata: an always-visible stat strip plus a details expander.

    The strip carries the four numbers worth glancing at (model, tokens, cost,
    latency). The expander holds the fuller breakdown - token split, supply-line
    flags, context size - so detail is available without crowding the answer.

    Args:
        metadata: Metadata dict from backend response
    """
    llm = metadata.get("llm", {}) or {}
    ctx = metadata.get("context", {}) or {}

    model_id = llm.get("model_id", "Unknown")
    input_tokens = llm.get("input_tokens", 0) or 0
    output_tokens = llm.get("output_tokens", 0) or 0
    total_tokens = llm.get("total_tokens", 0) or 0
    cost = llm.get("cost", 0.0) or 0.0
    processing_time_ms = metadata.get("processing_time_ms")

    # ---- Always-visible stat strip -------------------------------------------
    tiles = [
        _stat_tile("Model", shorten_model_id(model_id), tooltip=str(model_id), accent="model"),
        _stat_tile("Tokens", f"{total_tokens:,}",
                   tooltip=f"{input_tokens:,} in  /  {output_tokens:,} out"),
        _stat_tile("Cost", f"${cost:.4f}", tooltip="Bedrock input + output token cost",
                   accent="cost"),
    ]
    if processing_time_ms:
        tiles.append(_stat_tile("Latency", f"{processing_time_ms / 1000:.1f}s",
                                tooltip=f"{processing_time_ms:,.0f} ms end to end"))

    st.markdown(f'<div class="fs-stats">{"".join(tiles)}</div>', unsafe_allow_html=True)

    # ---- Details expander ----------------------------------------------------
    with st.expander("Query details", expanded=False):
        kpi_included = bool(ctx.get("kpi_included", False))
        rag_included = bool(ctx.get("rag_included", False))
        context_length = ctx.get("context_length", 0) or 0
        sentence_count = ctx.get("sentence_count", 0) or 0

        st.markdown(
            '<div class="fs-det-h">Supply lines</div>'
            f'<div class="fs-pills">{_pill("KPI lookup", kpi_included)}'
            f'{_pill("RAG search", rag_included)}</div>',
            unsafe_allow_html=True,
        )

        rows = [
            ("Model id", str(model_id)),
            ("Input tokens", f"{input_tokens:,}"),
            ("Output tokens", f"{output_tokens:,}"),
            ("Total tokens", f"{total_tokens:,}"),
            ("Cost", f"${cost:.4f}"),
            ("Context length", f"{context_length:,} chars"),
        ]
        if sentence_count > 0:
            rows.append(("Sentences retrieved", f"{sentence_count:,}"))
        if processing_time_ms:
            rows.append(("Processing time",
                         f"{processing_time_ms:,.0f} ms  ({processing_time_ms / 1000:.1f}s)"))

        body = "".join(
            f'<div class="fs-det-row"><span class="fs-det-k">{html.escape(k)}</span>'
            f'<span class="fs-det-v">{html.escape(v)}</span></div>'
            for k, v in rows
        )
        st.markdown(
            '<div class="fs-det-h">Run detail</div>'
            f'<div class="fs-det">{body}</div>',
            unsafe_allow_html=True,
        )


def display_sidebar_stats() -> None:
    """
    Display cumulative statistics in sidebar.
    
    Shows total queries, total cost, and backend health status.
    Uses session_state for data.
    """
    st.sidebar.markdown("### [Statistics]")
    
    # Total queries
    total_queries = st.session_state.get("total_queries", 0)
    st.sidebar.metric("Total Queries", total_queries)
    
    # Total cost
    total_cost = st.session_state.get("total_cost", 0.0)
    st.sidebar.metric("Total Cost", f"${total_cost:.4f}")
    
    # Average cost per query
    if total_queries > 0:
        avg_cost = total_cost / total_queries
        st.sidebar.metric("Avg Cost/Query", f"${avg_cost:.4f}")
    
    # Backend health indicator
    st.sidebar.markdown("---")
    st.sidebar.markdown("### [System Status]")
    
    backend_healthy = st.session_state.get("backend_healthy")
    
    if backend_healthy is True:
        st.sidebar.success("[OK] Backend: Healthy")
    elif backend_healthy is False:
        st.sidebar.error("[ERROR] Backend: Offline")
    else:
        st.sidebar.warning("[UNKNOWN] Backend: Not Checked")


def display_error_message(error: str, error_type: str, stage: str) -> None:
    """
    Display error message in a formatted error box.
    
    Args:
        error: Error message text
        error_type: Error classification
        stage: Pipeline stage where error occurred
    """
    st.error(f"**Error:** {error}")
    
    with st.expander("[+] Error Details"):
        st.text(f"Type: {error_type}")
        st.text(f"Stage: {stage}")
        
        # Helpful hints based on error type
        if error_type == "ConnectionError":
            st.info("[TIP] Make sure the backend server is running on http://localhost:8000")
        elif error_type == "TimeoutError":
            st.info("[TIP] The query is taking longer than expected. Complex queries may take 15-20 seconds.")
        elif error_type == "ValidationError":
            st.info("[TIP] Questions must be between 10-500 characters.")


def format_cost(cost: float) -> str:
    """
    Format cost for display.
    
    Args:
        cost: Cost in USD
    
    Returns:
        str: Formatted cost string
    """
    if cost < 0.01:
        return f"${cost:.6f}"  # Show more precision for very small costs
    else:
        return f"${cost:.4f}"


def format_tokens(tokens: int) -> str:
    """
    Format token count for display.
    
    Args:
        tokens: Token count
    
    Returns:
        str: Formatted token string with commas
    """
    return f"{tokens:,}"