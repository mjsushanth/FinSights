"""
run_dev_merges.py - development-stage driver that reuses the EXISTING
src_aws_etl merge machinery (ETLConfig + PreflightChecker + MergePipeline)
instead of writing a second, parallel merge implementation.

Runs two sequential incremental merges against the real S3 final fact
table ("the old table" - untouched 2024-cutoff production data):

  Merge 1: old table + incremental_batch_A (FY2025 for 20 companies +
           Alphabet's full rebuilt history) -> new final
  Merge 2: new final (from Merge 1) + incremental_batch_B (UNH/NOC/CAT/
           TMUS full 2006-2025 history) -> final final (25 companies)

Each MergePipeline.run() call is the real, unmodified merge/dedupe/
validate/archive flow (src_aws_etl/etl/merge_pipeline.py) - only the
incremental input path is overridden per call. This has to happen at the
YAML file level, not by mutating an already-constructed ETLConfig
instance's dict: MergePipeline.run() internally constructs its OWN fresh
PreflightChecker(), which loads a brand new ETLConfig() from disk - so an
in-memory override on one instance never reaches the other. The config
file is edited in place for the duration of each call and restored
immediately after (success or failure), via a context manager below.

Two small compatibility fixes were needed in the shared merge code itself
(not duplicated here - see their docstrings/comments for why):
  - preflight_check.py: the historical-file check is now skipped once a
    final file already exists (it was blocking legitimate incremental-only
    runs that never touch the historical bootstrap file at all).
  - merge_pipeline.py: the has_numbers/has_comparison/likely_kpi/tickers
    placeholder injection now only fires for incremental sources that don't
    already provide real values - it was unconditionally nulling out data
    that src_edgar_incremental had already computed for real.
"""

from __future__ import annotations

import sys
import yaml
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent  # DataPipeline/
sys.path.insert(0, str(PROJECT_ROOT))

from src_aws_etl.etl.merge_pipeline import MergePipeline

ETL_CONFIG_PATH = PROJECT_ROOT / "src_aws_etl" / ".aws_config" / "etl_config.yaml"
DEV_INCREMENTAL_PREFIX = "DEV_INCREMENTAL_BATCHES/2026-07-27_edgartools_expansion"

BATCHES = [
    ("incremental_batch_A_fy2025_20co_plus_google_fullhist.parquet",
     "Merge 1: FY2025 (20 companies) + Alphabet full history"),
    ("incremental_batch_B_new4companies_fullhist.parquet",
     "Merge 2: UNH/NOC/CAT/TMUS full 2006-2025 history"),
]


@contextmanager
def temporary_incremental_path(path: str, filename: str):
    """Temporarily point etl_config.yaml's input.incremental at a different
    file, restoring the original content afterward regardless of outcome."""
    original_text = ETL_CONFIG_PATH.read_text()
    cfg = yaml.safe_load(original_text)
    cfg['input']['incremental']['path'] = path
    cfg['input']['incremental']['filename'] = filename
    ETL_CONFIG_PATH.write_text(yaml.safe_dump(cfg, sort_keys=False))
    try:
        yield
    finally:
        ETL_CONFIG_PATH.write_text(original_text)


def run_merge(incr_filename: str, label: str) -> bool:
    print("\n" + "#" * 70)
    print(f"# {label}")
    print("#" * 70)

    with temporary_incremental_path(DEV_INCREMENTAL_PREFIX, incr_filename):
        pipeline = MergePipeline()
        return pipeline.run()


def main():
    for incr_filename, label in BATCHES:
        success = run_merge(incr_filename, label)
        if not success:
            print(f"\nABORTING - merge failed: {label}")
            sys.exit(1)

    print("\n" + "#" * 70)
    print("# BOTH MERGES COMPLETE")
    print("#" * 70)


if __name__ == "__main__":
    main()
