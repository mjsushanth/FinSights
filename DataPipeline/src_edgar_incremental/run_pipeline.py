"""
run_pipeline.py - orchestrator chaining Stages 1-6.

Usage:
    python run_pipeline.py                     # default: FY2025 for the 16
                                                # companies not yet at FY2025
    python run_pipeline.py --run-name my_batch --targets 320193:2025,34088:2025
    python run_pipeline.py --targets 1045810:2025 --no-push   # local only, skip S3

Stage 6 (push_to_etl_incremental) runs by default at the end of every
orchestrated run - the whole point of this pipeline is to hand off a file
at the exact spot src_aws_etl's merge_pipeline.py looks for it, with no
manual upload/config-editing step in between. Use --no-push for a purely
local test run that shouldn't touch the shared S3 incremental slot.

Architecture note: the cloud (S3) is the source of truth and the durable
handoff point between this pipeline and src_aws_etl - manifests/ is a
disposable scratch area, not a data store. It's cleared at the start of
every run (see clear_manifests() below) rather than accumulating a new
set of files per run-name forever.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from assemble_and_validate import run as assemble_and_validate
from clean_and_split import run as clean_and_split
from derive_features import run as derive_features
from extract_sections import run as extract_sections
from fetch_filings import default_fy2025_targets, run as fetch_filings
from push_to_etl_incremental import push as push_to_etl_incremental

MODULE_DIR = Path(__file__).parent
MANIFESTS_DIR = MODULE_DIR / "manifests"


def parse_targets(spec: str) -> list[tuple[int, int]]:
    """'320193:2025,34088:2025' -> [(320193, 2025), (34088, 2025)]"""
    pairs = []
    for chunk in spec.split(","):
        cik_str, year_str = chunk.split(":")
        pairs.append((int(cik_str), int(year_str)))
    return pairs


def clear_manifests():
    """manifests/ is scratch space for the CURRENT run only - cloud (via
    Stage 6) is the durable handoff, so nothing here needs to survive past
    one run. Clearing at the start (not the end) means a failed run's
    intermediates are still on disk to inspect until the next run starts."""
    if not MANIFESTS_DIR.exists():
        return
    for f in MANIFESTS_DIR.glob("*.parquet"):
        f.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", default="fy2025")
    parser.add_argument("--targets", default=None, help="cik:year,cik:year,...")
    parser.add_argument("--no-push", action="store_true",
                         help="skip Stage 6 (S3 push to the standard ETL incremental path)")
    parser.add_argument("--keep-manifests", action="store_true",
                         help="skip the manifests/ auto-clear (debugging multiple runs side by side)")
    args = parser.parse_args()

    if not args.keep_manifests:
        clear_manifests()

    targets = parse_targets(args.targets) if args.targets else default_fy2025_targets()

    print("=" * 70)
    print(f"STAGE 1: fetch_filings ({len(targets)} targets)")
    print("=" * 70)
    manifest = fetch_filings(targets, f"{args.run_name}_manifest.parquet")

    print("\n" + "=" * 70)
    print("STAGE 2: extract_sections")
    print("=" * 70)
    sections = extract_sections(manifest, f"{args.run_name}_sections.parquet")

    print("\n" + "=" * 70)
    print("STAGE 3: clean_and_split")
    print("=" * 70)
    sentences = clean_and_split(sections, f"{args.run_name}_sentences.parquet")

    print("\n" + "=" * 70)
    print("STAGE 4: derive_features")
    print("=" * 70)
    featured = derive_features(sentences, f"{args.run_name}_featured.parquet")

    print("\n" + "=" * 70)
    print("STAGE 5: assemble_and_validate")
    print("=" * 70)
    final = assemble_and_validate(featured, f"{args.run_name}_final.parquet")

    if args.no_push:
        print("\n(--no-push set: skipping Stage 6, standard S3 incremental path untouched)")
    else:
        print("\n" + "=" * 70)
        print("STAGE 6: push_to_etl_incremental")
        print("=" * 70)
        push_to_etl_incremental(final)

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print(f"  Filings resolved: {int(manifest['found'].sum())}/{manifest.height}")
    print(f"  Sentences produced: {final.height}")
    print(f"  Companies: {final['cik_int'].n_unique()}")
    print(f"  Report years: {sorted(final['report_year'].unique().to_list())}")

    return final


if __name__ == "__main__":
    main()
