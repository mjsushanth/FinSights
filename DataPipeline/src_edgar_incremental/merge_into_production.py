"""
merge_into_production.py

Development-stage merge of two src_edgar_incremental runs into the real
production fact table (ModelPipeline/finrag_ml_tg1/data_cache/stage1_facts/
finrag_fact_sentences.parquet):

  Run 1: FY2025 incremental for the 20 non-Google curated companies.
  Run 2: full-history rebuild (2015-2025) for Alphabet/Google.

Both runs are handled via explicit (cik_int, report_year) replacement, not
sentenceID-based dedup alone. First attempt at this script used plain
concat + unique(subset=sentenceID, keep=last) for the 20-company batch
(matching src_aws_etl/etl/merge_pipeline.py's convention) and found a real
bug: the 5 companies that already had FY2025 rows (from the older
extract_and_convert batch) kept STALE ORPHAN rows alongside the new
edgartools ones, because the old and new pipelines split sentences
differently, so old and new sentenceIDs only partially collided - e.g.
Walmart ended up with 1,453 new rows AND 145 leftover old rows for the
same report_year=2025. Fixed by removing every row matching a
(cik_int, report_year) pair that a new run is about to supply, BEFORE
concatenating - not relying on ID-level collision at all. sentenceID
dedup is kept only as a final safety-net assertion, not the primary
removal mechanism.

A backup of the pre-merge production table was uploaded to S3 under
PREDEV_BACKUPS/ before this script ran (not the real ETL archive path -
this is a predevelopment backup, not an ETL-run archive).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

MODULE_DIR = Path(__file__).parent
MANIFESTS_DIR = MODULE_DIR / "manifests"
PRODUCTION_PATH = (
    MODULE_DIR.parent.parent / "ModelPipeline" / "finrag_ml_tg1" / "data_cache"
    / "stage1_facts" / "finrag_fact_sentences.parquet"
)

GOOGLE_CIK = 1652044


def main():
    production = pl.read_parquet(PRODUCTION_PATH)
    run1 = pl.read_parquet(MANIFESTS_DIR / "run1_fy2025_20co_final.parquet")
    run2 = pl.read_parquet(MANIFESTS_DIR / "run2_google_fullhist_final.parquet")

    print(f"Production (before): {production.height:,} rows, "
          f"{production['cik_int'].n_unique()} companies")

    # Explicit (cik_int, report_year) replacement - covers every pair either
    # run is about to supply, not just Alphabet. Doing this INSTEAD of relying
    # on sentenceID collisions is what avoids the stale-orphan-row bug (see
    # module docstring).
    replace_keys = (
        run1.select(["cik_int", "report_year"]).unique()
        .vstack(run2.select(["cik_int", "report_year"]).unique())
    )
    print(f"Replacing {replace_keys.height} (cik_int, report_year) pair(s) outright:")
    print(replace_keys.sort(["cik_int", "report_year"]))

    old_replaced_rows = production.join(replace_keys, on=["cik_int", "report_year"], how="inner")
    print(f"\nOld rows being removed for these pairs: {old_replaced_rows.height:,}")

    base = production.join(replace_keys, on=["cik_int", "report_year"], how="anti")

    merged = pl.concat([base, run1, run2], how="vertical")
    before_dedup = merged.height
    merged = merged.unique(subset=["sentenceID"], keep="last")
    n_deduped = before_dedup - merged.height
    if n_deduped:
        print(f"\nWARNING: {n_deduped} sentenceID collision(s) still found after "
              f"explicit (cik,year) replacement - investigate before trusting this run.")
    print(f"Concatenated: {before_dedup:,} rows -> final {merged.height:,} rows")

    merged = merged.sort(["cik_int", "report_year", "sentenceID"])

    # --- validation before write ---
    problems = []

    if merged["sentenceID"].n_unique() != merged.height:
        problems.append("sentenceID not unique after dedup")

    for col in ["cik_int", "docID", "sentenceID", "sentence"]:
        n_null = merged[col].null_count()
        if n_null:
            problems.append(f"{col} has {n_null} null values")

    n_companies = merged["cik_int"].n_unique()
    if n_companies != 21:
        problems.append(f"expected 21 distinct companies, found {n_companies}")

    google_years_after = sorted(merged.filter(pl.col("cik_int") == GOOGLE_CIK)["report_year"].unique().to_list())
    if google_years_after != list(range(2015, 2026)):
        problems.append(f"Alphabet report_year coverage incomplete: {google_years_after}")

    real_schema = pl.scan_parquet(PRODUCTION_PATH).collect_schema()
    for col in real_schema:
        if col not in merged.columns:
            problems.append(f"missing column after merge: {col}")
        elif str(merged.schema[col]) != str(real_schema[col]):
            problems.append(f"dtype drift on {col}: {merged.schema[col]} vs {real_schema[col]}")

    if problems:
        print("\nVALIDATION FAILED - not writing:")
        for p in problems:
            print(f"  - {p}")
        raise ValueError(f"{len(problems)} problem(s), see above")

    print("\nValidation passed.")
    print(f"Production (after): {merged.height:,} rows, {n_companies} companies")
    print(f"Alphabet report_year coverage: {google_years_after}")

    merged.write_parquet(PRODUCTION_PATH)
    print(f"\nWritten to {PRODUCTION_PATH}")

    return merged


if __name__ == "__main__":
    main()
