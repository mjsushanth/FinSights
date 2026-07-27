"""
Stage 6: push_to_etl_incremental.py

Uploads the Stage 5 output to the EXACT S3 key src_aws_etl's ETLConfig
expects for the incremental staging file - the standard, single-slot path
merge_pipeline.py reads from by default, not a custom dev-stage location.

This closes a real integration gap found this session: earlier dev-stage
merges worked by manually uploading to a custom S3 prefix and temporarily
editing etl_config.yaml to point at it. That proved the merge LOGIC works,
but never proved the two modules are actually wired together - that
src_edgar_incremental's output lands where src_aws_etl looks for it with
zero manual intervention. This module is that wiring.

Deliberately reads path/bucket from ETLConfig itself (the same config
class merge_pipeline.py uses) rather than hardcoding a duplicate path
string - the two modules can never drift apart on where "the standard
incremental file" lives, since there's only one definition of it.

The incremental slot is single-file / latest-wins by design (matching
etl_config.yaml's input.incremental being one fixed filename, not a
timestamped history) - each push OVERWRITES whatever was there. That's
intentional: the ETL merge already has its own archive step for the FINAL
table; the incremental staging slot is just a handoff point, not a log.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

MODULE_DIR = Path(__file__).parent
PROJECT_ROOT = MODULE_DIR.parent  # DataPipeline/
sys.path.insert(0, str(PROJECT_ROOT))

from src_aws_etl.etl.config_loader import ETLConfig


def push(df: pl.DataFrame) -> str:
    """Uploads df to the standard incremental S3 path. Returns the S3 URI
    written to, for logging/confirmation."""
    config = ETLConfig()

    uri = config.s3_uri(config.incr_path)
    print(f"Pushing {df.height:,} rows to standard incremental path: {uri}")

    tmp_path = MODULE_DIR / "manifests" / "_push_staging_tmp.parquet"
    tmp_path.parent.mkdir(exist_ok=True)
    df.write_parquet(tmp_path, compression=config.compression)

    s3 = config.get_s3_client()
    s3.upload_file(str(tmp_path), config.bucket, config.incr_path)
    tmp_path.unlink()

    print(f"  Pushed. {config.bucket}/{config.incr_path}")
    return uri


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("parquet_path", help="local parquet file to push")
    args = parser.parse_args()

    push(pl.read_parquet(args.parquet_path))
