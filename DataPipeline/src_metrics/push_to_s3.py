"""
push_to_s3.py - writes the final KPI fact table to S3 first, then syncs
both local data_cache mirrors. Same "cloud is the source of truth, local
is a synced mirror" pattern documented in
DataPipeline/CLOUD_SOURCE_OF_TRUTH.md and implemented by
src_aws_etl/etl/merge_pipeline.py's sync_local_data_cache() for the
sentence table - the mechanism is reused in spirit (S3 write happens
before any local file is touched), not literally imported, since the
local mirror paths differ (metrics_fact/ vs stage1_facts/).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import polars as pl

from config import MetricsConfig
from src_aws_etl.etl.config_loader import ETLConfig


def push_kpi_facts(df: pl.DataFrame, config: MetricsConfig, etl: ETLConfig) -> None:
    print(f"Pushing {df.height:,} rows to s3://{config.bucket}/{config.kpi_facts_key}")

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        df.write_parquet(tmp_path)

    s3 = etl.get_s3_client()
    s3.upload_file(str(tmp_path), config.bucket, config.kpi_facts_key)
    print(f"  Written: {config.kpi_facts_key}")

    for mirror in config.local_mirrors:
        mirror.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp_path, mirror)
        print(f"  Synced: {mirror}")

    tmp_path.unlink()


def read_current_kpi_facts(config: MetricsConfig, etl: ETLConfig) -> pl.DataFrame | None:
    """Reads the current production KPI table from S3 - the source of
    truth to compare a new run's coverage against. Returns None if it
    doesn't exist yet (first-ever run)."""
    uri = etl.s3_uri(config.kpi_facts_key)
    try:
        return pl.read_parquet(uri, storage_options=etl.get_storage_options())
    except Exception as e:
        print(f"No existing KPI table found at {uri} ({e}) - treating as a first run.")
        return None
