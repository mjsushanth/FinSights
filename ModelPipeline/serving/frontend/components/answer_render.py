# ModelPipeline/serving/frontend/components/answer_render.py
"""
Answer rendering for FinSight: narrative prose plus structured source chips.

The backend's system prompt (prompts/system_financial_rag_v1.yaml) instructs the
LLM to end every answer with a DATA SOURCES section in a fixed shape:

    DATA SOURCES:

    [1] Financial Metrics (Revenue, Net Income, ...)
        KPI Snapshot

    [2] Supply Chain Risks and Manufacturing Model
        NVDA, FY 2018, Item 1A: Risk Factors, Doc: 0001045810_10-K_2018

Rendered as raw markdown that block is a wall of monospace-ish text. This module
parses it and renders each source as a compact chip carrying the three facts a
financial researcher actually scans for - which company, which fiscal year, which
10-K item - with the full section name and document ID available on hover.

Design constraint: the LLM produces this text, so every parsed value is treated as
untrusted and HTML-escaped before it reaches an unsafe_allow_html sink. If parsing
fails for any reason, render_answer falls back to plain markdown so a formatting
change in the model's output can never blank out an answer.

Usage:
    from components.answer_render import render_answer
    render_answer(answer_text)
"""

import html
import re
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# Matches the "DATA SOURCES:" divider, tolerating markdown bold, heading marks and
# leading horizontal rules that the response cleaner may introduce.
_SOURCES_HEADER = re.compile(
    r"^[ \t]*(?:[-*_]{3,}[ \t]*\n)?[ \t]*[#>*_ \t]*DATA\s+SOURCES[ \t]*:?[ \t]*[*_]*[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# "[2] Supply Chain Risks and Manufacturing Model"
_GROUP_LINE = re.compile(r"^[ \t]*\[(\d+)\][ \t]*(.*)$")

# "NVDA, FY 2018, Item 1A: Risk Factors, Doc: 0001045810_10-K_2018"
_SOURCE_LINE = re.compile(
    r"^[ \t]*([A-Z][A-Z0-9.\-]{0,9}),[ \t]*FY[ \t]*(\d{4}),[ \t]*(.+?),[ \t]*Doc:[ \t]*(\S+)[ \t]*$"
)

# "KPI Snapshot" - the structured Supply Line 1 source, which has no ticker/year.
_KPI_LINE = re.compile(r"^[ \t]*KPI\s+Snapshot[ \t]*\.?[ \t]*$", re.IGNORECASE)

# "Item 1A: Risk Factors" -> "Item 1A"
_ITEM_CODE = re.compile(r"\bItem[ \t]+(\d+[A-Za-z]?)\b", re.IGNORECASE)

# Per-company hues, deliberately confined to the FinSights identity: a cool ramp
# running neon green -> emerald -> teal -> cyan -> sky -> blue. Warm or purple
# accents are avoided on purpose - they read as a different product. Ten steps is
# enough to separate companies within one answer while still looking like one
# palette rather than a chart legend. Assignment is by sorted ticker position so
# colours stay stable within an answer.
PALETTE = [
    "#22c55e",  # neon green - the FinSights primary
    "#38bdf8",  # sky
    "#2dd4bf",  # teal
    "#4ade80",  # light green
    "#0ea5e9",  # blue - the FinSights secondary
    "#34d399",  # emerald
    "#22d3ee",  # cyan
    "#86efac",  # pale green
    "#60a5fa",  # soft blue
    "#10b981",  # deep emerald
]

KPI_COLOR = "#94a3b8"  # slate - deliberately neutral, KPI is not a filing section


def rgba(hex_color: str, alpha: float) -> str:
    """Convert #rrggbb to an rgba() string. Avoids relying on CSS color-mix()."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def _short_section(section: str) -> str:
    """'Item 1A: Risk Factors' -> 'Item 1A'. Falls back to a clipped label."""
    m = _ITEM_CODE.search(section)
    if m:
        return f"Item {m.group(1).upper()}"
    cleaned = section.strip().rstrip(".,;")
    return cleaned if len(cleaned) <= 22 else cleaned[:21] + "…"


def split_data_sources(content: str) -> Tuple[str, Optional[str]]:
    """
    Split an answer into (narrative_body, data_sources_block).

    Returns (content, None) when no DATA SOURCES header is present.
    """
    if not content:
        return "", None
    match = _SOURCES_HEADER.search(content)
    if not match:
        return content, None
    body = content[:match.start()]
    # Drop a trailing markdown horizontal rule left behind by the split.
    body = re.sub(r"(?:\n[ \t]*[-*_]{3,}[ \t]*)+\s*$", "", body).rstrip()
    return body, content[match.end():]


def parse_source_groups(block: str) -> List[Dict[str, Any]]:
    """
    Parse a DATA SOURCES block into ordered topic groups.

    Each group is {"num": str, "label": str, "sources": [...], "kpi": bool} where a
    source is {"ticker", "fy", "section", "doc"}. Lines that match nothing are kept
    as "extra" text so unexpected model output is surfaced rather than silently lost.
    """
    groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for raw_line in (block or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        group_match = _GROUP_LINE.match(line)
        if group_match:
            current = {
                "num": group_match.group(1),
                "label": group_match.group(2).strip(),
                "sources": [],
                "kpi": False,
                "extra": [],
            }
            groups.append(current)
            continue

        if current is None:
            continue

        source_match = _SOURCE_LINE.match(line)
        if source_match:
            current["sources"].append({
                "ticker": source_match.group(1).strip(),
                "fy": source_match.group(2).strip(),
                "section": source_match.group(3).strip(),
                "doc": source_match.group(4).strip(),
            })
            continue

        if _KPI_LINE.match(line):
            current["kpi"] = True
            continue

        stripped = line.strip().lstrip("-*• ").strip()
        if stripped:
            current["extra"].append(stripped)

    return groups


MAX_STAGGER_STEPS = 8  # number of .fs-d* entrance-delay classes generated


def _colour_map(groups: List[Dict[str, Any]]) -> Dict[str, int]:
    """Assign a stable palette index per ticker, ordered for determinism."""
    tickers = sorted({s["ticker"] for g in groups for s in g["sources"]})
    return {t: i % len(PALETTE) for i, t in enumerate(tickers)}


def palette_css() -> str:
    """
    Generate the per-company colour classes and entrance-delay classes.

    These MUST be real CSS classes rather than inline style attributes: Streamlit's
    markdown sanitiser strips the style attribute (verified on streamlit 1.31 in the
    container, where chips rendered completely unstyled while class and title
    survived). Custom properties are declared per class and consumed by the static
    .fs-chip rules in styles.py.
    """
    rules: List[str] = []
    for i, colour in enumerate(PALETTE):
        rules.append(
            f".fs-c{i}{{--fs-fg:{colour};"
            f"--fs-bg:{rgba(colour, 0.13)};"
            f"--fs-bd:{rgba(colour, 0.42)};"
            f"--fs-glow:{rgba(colour, 0.38)};}}"
        )
    rules.append(
        f".fs-ckpi{{--fs-fg:{KPI_COLOR};"
        f"--fs-bg:{rgba(KPI_COLOR, 0.14)};"
        f"--fs-bd:{rgba(KPI_COLOR, 0.45)};"
        f"--fs-glow:{rgba(KPI_COLOR, 0.30)};}}"
    )
    for j in range(MAX_STAGGER_STEPS):
        rules.append(f".fs-d{j}{{--fs-delay:{j * 55}ms;}}")
    return "".join(rules)


def _coverage_line(groups: List[Dict[str, Any]]) -> str:
    """Build a one-line scan summary: companies, fiscal-year span, reference count."""
    sources = [s for g in groups for s in g["sources"]]
    tickers = sorted({s["ticker"] for s in sources})
    years = sorted({s["fy"] for s in sources})
    parts: List[str] = []

    if tickers:
        parts.append(f"{len(tickers)} compan{'y' if len(tickers) == 1 else 'ies'}")
    if years:
        parts.append(years[0] if len(years) == 1 else f"FY{years[0]}–FY{years[-1]}")
    if sources:
        parts.append(f"{len(sources)} reference{'' if len(sources) == 1 else 's'}")
    if any(g["kpi"] for g in groups):
        parts.append("KPI snapshot")

    return "  ·  ".join(parts)


def build_sources_html(groups: List[Dict[str, Any]]) -> str:
    """Render parsed groups as chip HTML. All interpolated values are escaped."""
    colours = _colour_map(groups)
    out: List[str] = ['<div class="fs-sources">']

    coverage = _coverage_line(groups)
    out.append(
        '<div class="fs-sources-head">'
        '<span class="fs-sources-title">Sources</span>'
        f'<span class="fs-sources-meta">{html.escape(coverage)}</span>'
        "</div>"
    )

    for idx, group in enumerate(groups):
        # Stagger the entrance so groups cascade in rather than snapping on at once.
        out.append(f'<div class="fs-group fs-d{min(idx, MAX_STAGGER_STEPS - 1)}">')
        out.append(
            '<div class="fs-group-topic">'
            f'<span class="fs-group-num">{html.escape(group["num"])}</span>'
            f'<span class="fs-group-label">{html.escape(group["label"])}</span>'
            "</div>"
        )
        out.append('<div class="fs-chips">')

        if group["kpi"]:
            out.append(
                '<span class="fs-chip fs-chip-kpi fs-ckpi" '
                'title="Structured KPI fact table (Supply Line 1)">'
                '<span class="fs-chip-dot"></span>'
                '<span class="fs-chip-t">KPI Snapshot</span>'
                "</span>"
            )

        for src in group["sources"]:
            cidx = colours.get(src["ticker"], 0)
            tooltip = f'{src["ticker"]}  ·  FY {src["fy"]}  ·  {src["section"]}  ·  Doc {src["doc"]}'
            fy_short = src["fy"][-2:] if len(src["fy"]) == 4 else src["fy"]
            out.append(
                f'<span class="fs-chip fs-c{cidx}" '
                f'title="{html.escape(tooltip)}">'
                f'<span class="fs-chip-dot"></span>'
                f'<span class="fs-chip-t">{html.escape(src["ticker"])}</span>'
                f'<span class="fs-chip-sep">·</span>'
                f'<span class="fs-chip-y">FY{html.escape(fy_short)}</span>'
                f'<span class="fs-chip-sep">·</span>'
                f'<span class="fs-chip-s">{html.escape(_short_section(src["section"]))}</span>'
                "</span>"
            )

        out.append("</div>")

        for extra in group["extra"]:
            out.append(f'<div class="fs-group-extra">{html.escape(extra)}</div>')

        out.append("</div>")

    out.append("</div>")
    return "".join(out)


def render_answer(content: str) -> None:
    """
    Render an assistant answer: narrative prose, then structured source chips.

    Degrades to plain markdown whenever the DATA SOURCES section is absent or
    cannot be parsed, so an unexpected answer shape still displays in full.
    """
    body, sources_block = split_data_sources(content or "")

    if sources_block is None:
        st.markdown(content or "")
        return

    groups = parse_source_groups(sources_block)
    if not groups or not any(g["sources"] or g["kpi"] for g in groups):
        # Header present but nothing parseable - show the original text verbatim
        # rather than dropping the citations.
        st.markdown(content or "")
        return

    if body:
        st.markdown(body)
    st.markdown(build_sources_html(groups), unsafe_allow_html=True)
