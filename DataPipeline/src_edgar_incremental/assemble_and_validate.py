"""
Stage 5: assemble_and_validate.py

Takes the fully-featured sentence rows (Stage 4 output) and produces a
Stage-1-schema-compatible parquet, ready to be merged by the EXISTING
src_aws_etl/etl/merge_pipeline.py as the "incremental" input. This stage's
job stops at producing a clean, schema-correct file - it does not merge.

Sanity checks run before writing (per PLAN.md Stage 5 checklist): sentenceID
uniqueness, no null keys, cik_int is one of the 21 curated companies,
row_hash recomputation, and a direct dtype/column comparison against the
real production parquet's schema.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

MODULE_DIR = Path(__file__).parent
SECTIONS_DIR = MODULE_DIR / "manifests"
DIM_COMPANIES_21 = MODULE_DIR.parent / "data_cache" / "dimensions" / "finrag_dim_companies_21.parquet"
REAL_FACT_TABLE = (
    MODULE_DIR.parent.parent / "ModelPipeline" / "finrag_ml_tg1" / "data_cache"
    / "stage1_facts" / "finrag_fact_sentences.parquet"
)

SAMPLE_VERSION = "v2.2_edgartools_incremental"
LOAD_METHOD = "edgartools_incremental"

# Reused verbatim from src_legacy_bs4_scraper/extract_and_convert.py:temporal_bin
def temporal_bin(y: int) -> str:
    if 2006 <= y <= 2009:
        return "bin_2006_2009"
    elif 2010 <= y <= 2015:
        return "bin_2010_2015"
    elif 2016 <= y <= 2020:
        return "bin_2016_2020"
    elif 2021 <= y <= 2025:
        return "bin_2021_2025"
    else:
        return "bin_unknown"


TARGET_COLUMN_ORDER = [
    "cik", "cik_int", "name", "tickers", "docID", "sentenceID", "section_ID",
    "section_name", "form", "sic", "sentence", "filingDate", "report_year",
    "reportDate", "temporal_bin", "likely_kpi", "has_numbers", "has_comparison",
    "sample_created_at", "last_modified_date", "sample_version",
    "source_file_path", "load_method", "row_hash",
]


def assemble(featured_df: pl.DataFrame) -> pl.DataFrame:
    now = datetime.now(timezone.utc)

    df = featured_df.with_columns([
        pl.col("cik_int").cast(pl.Int32),
        pl.col("section_ID").cast(pl.Int64),
        pl.col("report_year").cast(pl.Int64),
        pl.col("report_year").map_elements(temporal_bin, return_dtype=pl.String).alias("temporal_bin"),
        pl.lit(now).alias("sample_created_at"),
        pl.lit(now).alias("last_modified_date"),
        pl.lit(SAMPLE_VERSION).alias("sample_version"),
        pl.lit(LOAD_METHOD).alias("load_method"),
        (pl.col("sentenceID") + pl.col("sentence"))
            .map_elements(lambda x: hashlib.md5(x.encode()).hexdigest(), return_dtype=pl.String)
            .alias("row_hash"),
    ])

    return df.select(TARGET_COLUMN_ORDER)


def validate(df: pl.DataFrame) -> list[str]:
    """Returns a list of problems found (empty = clean)."""
    problems = []

    if df["sentenceID"].n_unique() != df.height:
        dupes = df.height - df["sentenceID"].n_unique()
        problems.append(f"sentenceID has {dupes} duplicate value(s)")

    for col in ["cik_int", "docID", "sentenceID", "sentence"]:
        n_null = df[col].null_count()
        if n_null:
            problems.append(f"{col} has {n_null} null value(s)")

    dim21_ciks = set(pl.read_parquet(DIM_COMPANIES_21)["cik_int"].to_list())
    bad_ciks = set(df["cik_int"].to_list()) - dim21_ciks
    if bad_ciks:
        problems.append(f"cik_int values not in the 21 curated companies: {bad_ciks}")

    recomputed = df.with_columns(
        (pl.col("sentenceID") + pl.col("sentence"))
        .map_elements(lambda x: hashlib.md5(x.encode()).hexdigest(), return_dtype=pl.String)
        .alias("_check_hash")
    )
    n_mismatch = (recomputed["_check_hash"] != recomputed["row_hash"]).sum()
    if n_mismatch:
        problems.append(f"row_hash mismatch on {n_mismatch} row(s)")

    counts = df.group_by(["cik_int", "report_year"]).len()
    low_count = counts.filter(pl.col("len") < 20)
    if low_count.height:
        problems.append(
            f"WARNING (non-fatal): {low_count.height} (cik,year) pair(s) produced "
            f"fewer than 20 sentences - possible section-detection failure:\n{low_count}"
        )

    if REAL_FACT_TABLE.exists():
        real_schema = pl.scan_parquet(REAL_FACT_TABLE).collect_schema()
        for col in TARGET_COLUMN_ORDER:
            if col not in real_schema:
                problems.append(f"column {col} not present in real production schema")
                continue
            expected_dtype = real_schema[col]
            actual_dtype = df.schema[col]
            if str(expected_dtype) != str(actual_dtype):
                problems.append(
                    f"dtype mismatch on {col}: got {actual_dtype}, production has {expected_dtype}"
                )

    return problems


def run(featured_df: pl.DataFrame, out_name: str) -> pl.DataFrame:
    df = assemble(featured_df)
    problems = validate(df)

    fatal = [p for p in problems if not p.startswith("WARNING")]
    warnings = [p for p in problems if p.startswith("WARNING")]

    for w in warnings:
        print(w)

    if fatal:
        print("\nVALIDATION FAILED:")
        for p in fatal:
            print(f"  - {p}")
        raise ValueError(f"{len(fatal)} validation problem(s) - see above")

    out_path = SECTIONS_DIR / out_name
    df.write_parquet(out_path)
    print(f"\nValidation passed. {df.height} rows written to {out_path}")
    return df


if __name__ == "__main__":
    featured = pl.read_parquet(SECTIONS_DIR / "fy2025_featured.parquet")
    run(featured, "fy2025_final.parquet")
