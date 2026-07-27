"""
Stage 3: clean_and_split.py

Turns Stage 2's raw section text into one row per sentence, matching the
target schema's grain. Reuses the item-header-period fix from the legacy
scraper (Gotcha 4) and adds a generalized footer-boilerplate strip
(Gotcha 3) - verified this session to vary by filer (Apple has it, Amazon/
Exxon/Tesla do not), so the regex is written to be a no-op where absent
rather than assuming every filer's footer looks the same.
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl

MODULE_DIR = Path(__file__).parent
SECTIONS_DIR = MODULE_DIR / "manifests"

# Reused verbatim (same regex) from
# src_legacy_bs4_scraper/extract_and_convert.py:_normalize_item_token -
# prevents "Item 1A." from being treated as its own sentence.
_ITEM_PERIOD_RE = re.compile(r'(?i)\bItem\s+(\d+[A-Za-z]?)\.')

# Generalized page-footer pattern: "<anything short> | <year> Form 10-K | <page#>".
# Verified live: present in Apple's filings, absent in Amazon/Exxon/Tesla's -
# the exact company name isn't hardcoded so this is a no-op where the
# footer format differs.
_FOOTER_RE = re.compile(r'[^|\n]{1,60}\|\s*\d{4}\s*Form\s*10-K\s*\|\s*\d+')

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z(])')

# Drop fragments that are just leftover item headers or too short to be a
# real sentence (e.g. "ITEM 1A. RISK FACTORS" after cleaning).
_BARE_HEADER_RE = re.compile(r'(?i)^item\s+\d+[a-z]?\.?\s*[a-z ,&/-]*$')
MIN_SENTENCE_TOKENS = 4


def normalize_item_periods(text: str) -> str:
    return _ITEM_PERIOD_RE.sub(r'Item \1', text)


def strip_footer_boilerplate(text: str) -> str:
    return _FOOTER_RE.sub(' ', text)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def is_degenerate(sentence: str) -> bool:
    if _BARE_HEADER_RE.match(sentence):
        return True
    if len(sentence.split()) < MIN_SENTENCE_TOKENS:
        return True
    return False


def clean_and_split_section(raw_text: str) -> list[str]:
    text = normalize_item_periods(raw_text)
    text = strip_footer_boilerplate(text)
    sentences = split_sentences(text)
    return [s for s in sentences if not is_degenerate(s)]


def run(sections_df: pl.DataFrame, out_name: str) -> pl.DataFrame:
    rows = []
    for row in sections_df.iter_rows(named=True):
        item_token = row["section_name"].replace("ITEM_", "")
        sentences = clean_and_split_section(row["raw_text"])

        for s_idx, sentence in enumerate(sentences, start=1):
            rows.append({
                "cik": row["cik"],
                "cik_int": row["cik_int"],
                "name": row["name"],
                "tickers": row["tickers"],
                "sic": row["sic"],
                "docID": row["docID"],
                "sentenceID": f"{row['docID']}_section_{item_token}_{s_idx}",
                "section_ID": row["section_ID"],
                "section_name": row["section_name"],
                "form": row["form"],
                "sentence": sentence,
                "filingDate": row["filing_date"],
                "report_year": row["report_year"],
                "reportDate": row["report_date"],
                "source_file_path": row["filing_url"],
            })
        print(f"  {row['docID']} {row['section_name']}: {len(sentences)} sentences")

    out_df = pl.DataFrame(rows)
    out_path = SECTIONS_DIR / out_name
    out_df.write_parquet(out_path)
    print(f"\n{len(out_df)} sentences from {sections_df.height} sections. Written to {out_path}")
    return out_df


if __name__ == "__main__":
    sections = pl.read_parquet(SECTIONS_DIR / "fy2025_sections.parquet")
    run(sections, "fy2025_sentences.parquet")
