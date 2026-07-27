"""
cleanup_adjacent_duplicates.py

One-off (re-runnable, idempotent) cleanup of the production fact table:
removes an exact-duplicate sentence that appears immediately after itself
within the same (docID, section_name), keeping the first occurrence.

This is "Category B" from the duplicate-sentence QA pass (see
DataPipeline/analytics/duplicate_sentence_analysis.md for the full
analysis) - confirmed via neighbor-context inspection to be a formatting/
extraction artifact (e.g. Tesla FY2024 Item 1A: the exact same sentence at
two consecutive sentence positions, nothing between them), NOT the far
more common and genuinely meaningful case of the same boilerplate sentence
appearing in two distant, unrelated parts of a filing (e.g. the same
legal/compliance sentence reused under two different litigation matters or
debt instruments) - that case is real content and is deliberately left
untouched everywhere in this codebase.

Follows the cloud-source-of-truth pattern (see
DataPipeline/CLOUD_SOURCE_OF_TRUTH.md): reads the current final table from
S3, writes the cleaned result back to S3, then syncs both local data_cache
mirrors - reusing MergePipeline.sync_local_data_cache() rather than
duplicating that logic.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import polars as pl

PROJECT_ROOT = Path(__file__).parent.parent.parent  # DataPipeline/
sys.path.insert(0, str(PROJECT_ROOT))

from src_aws_etl.etl.config_loader import ETLConfig
from src_aws_etl.etl.merge_pipeline import MergePipeline


def find_adjacent_duplicate_ids(df: pl.DataFrame) -> list[str]:
    """Returns sentenceIDs to DROP - the second-and-later occurrence of any
    sentence that repeats immediately after itself within the same
    (docID, section_name), ordered by the numeric suffix of sentenceID."""
    ordered = (
        df.select(["docID", "section_name", "sentenceID", "sentence"])
        .with_columns(pl.col("sentenceID").str.extract(r"_(\d+)$", 1).cast(pl.Int64).alias("s_idx"))
        .sort(["docID", "section_name", "s_idx"])
    )

    to_drop = []
    prev_key = None
    prev_sentence = None
    for row in ordered.iter_rows(named=True):
        key = (row["docID"], row["section_name"])
        if key == prev_key and row["sentence"] == prev_sentence:
            to_drop.append(row["sentenceID"])
        else:
            prev_sentence = row["sentence"]
        prev_key = key

    return to_drop


def main():
    config = ETLConfig()
    print(f"Reading final table from {config.s3_uri(config.final_path)} ...")
    df = pl.read_parquet(config.s3_uri(config.final_path), storage_options=config.get_storage_options())
    print(f"  {df.height:,} rows, {df['cik_int'].n_unique()} companies")

    drop_ids = find_adjacent_duplicate_ids(df)
    print(f"\nAdjacent-duplicate sentenceIDs to remove: {len(drop_ids)}")

    if not drop_ids:
        print("Nothing to clean up - table is already free of adjacent duplicates.")
        return

    cleaned = df.filter(~pl.col("sentenceID").is_in(drop_ids))

    # Sanity checks before writing
    assert cleaned.height == df.height - len(drop_ids), "row count didn't drop by the expected amount"
    assert cleaned["sentenceID"].n_unique() == cleaned.height, "sentenceID not unique after cleanup"
    for col in ["cik_int", "docID", "sentence"]:
        assert cleaned[col].null_count() == 0, f"{col} has nulls after cleanup"

    print(f"Rows before: {df.height:,} -> after: {cleaned.height:,}")

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = tmp.name
        cleaned.write_parquet(tmp_path, compression=config.compression)

    s3 = config.get_s3_client()
    s3.upload_file(tmp_path, config.bucket, config.final_path)
    print(f"\nWritten to S3: {config.final_path}")

    # Reuse the same local-sync logic merge_pipeline.py uses - not duplicated
    MergePipeline().sync_local_data_cache(tmp_path)

    Path(tmp_path).unlink()
    print("\nCleanup complete.")


if __name__ == "__main__":
    main()
