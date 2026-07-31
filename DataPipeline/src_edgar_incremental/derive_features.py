"""
Stage 4: derive_features.py

Populates has_numbers / has_comparison / likely_kpi with real booleans
(final, basic implementation - per explicit user direction this is not a
stepping stone to anything fancier, and these fields are never used to
derive further fields downstream).

Note on the KPI keyword list: PLAN.md originally proposed reusing
src_metrics/gaap_aliases.py's canonical metric names as the keyword seed
list. Reviewed those this session - they're XBRL balance-sheet tag labels
(e.g. "dta_nol_domestic", "vie_liabilities_no_recourse"), built for
structured fact tagging, not narrative MD&A prose - so they don't work well
as sentence-level keyword matches. Using a small, hand-picked list of common
financial-prose KPI terms instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl

MODULE_DIR = Path(__file__).parent
SECTIONS_DIR = MODULE_DIR / "manifests"

_NUMBER_RE = re.compile(r'\d')

_COMPARISON_TERMS = [
    "increase", "increased", "decrease", "decreased", "compared to",
    "versus", "higher", "lower", "grew", "growth", "declined", "decline",
    "year-over-year", "year over year", "as compared with",
]
_COMPARISON_RE = re.compile(r'(?i)\b(' + '|'.join(re.escape(t) for t in _COMPARISON_TERMS) + r')\b')

_KPI_TERMS = [
    "revenue", "net income", "gross profit", "gross margin", "operating income",
    "operating margin", "ebitda", "earnings per share", "eps", "cash flow",
    "free cash flow", "net sales", "total assets", "operating expenses",
    "diluted earnings", "net loss", "profit margin",
]
_KPI_RE = re.compile(r'(?i)\b(' + '|'.join(re.escape(t) for t in _KPI_TERMS) + r')\b')


def has_numbers(sentence: str) -> bool:
    return bool(_NUMBER_RE.search(sentence))


def has_comparison(sentence: str) -> bool:
    return bool(_COMPARISON_RE.search(sentence))


def likely_kpi(sentence: str, sentence_has_numbers: bool) -> bool:
    return sentence_has_numbers and bool(_KPI_RE.search(sentence))


def run(sentences_df: pl.DataFrame, out_name: str) -> pl.DataFrame:
    out_df = sentences_df.with_columns([
        pl.col("sentence").map_elements(has_numbers, return_dtype=pl.Boolean).alias("has_numbers"),
        pl.col("sentence").map_elements(has_comparison, return_dtype=pl.Boolean).alias("has_comparison"),
    ]).with_columns(
        pl.struct(["sentence", "has_numbers"]).map_elements(
            lambda s: likely_kpi(s["sentence"], s["has_numbers"]), return_dtype=pl.Boolean
        ).alias("likely_kpi")
    )

    out_path = SECTIONS_DIR / out_name
    out_df.write_parquet(out_path)

    n = out_df.height
    print(f"has_numbers: {out_df['has_numbers'].sum()}/{n}")
    print(f"has_comparison: {out_df['has_comparison'].sum()}/{n}")
    print(f"likely_kpi: {out_df['likely_kpi'].sum()}/{n}")
    print(f"Written to {out_path}")
    return out_df


if __name__ == "__main__":
    sentences = pl.read_parquet(SECTIONS_DIR / "fy2025_sentences.parquet")
    run(sentences, "fy2025_featured.parquet")
