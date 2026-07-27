"""
run_pipeline.py - orchestrator chaining Stages 1-5.

Usage:
    python run_pipeline.py                     # default: FY2025 for the 16
                                                # companies not yet at FY2025
    python run_pipeline.py --run-name my_batch --targets 320193:2025,34088:2025
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

MODULE_DIR = Path(__file__).parent


def parse_targets(spec: str) -> list[tuple[int, int]]:
    """'320193:2025,34088:2025' -> [(320193, 2025), (34088, 2025)]"""
    pairs = []
    for chunk in spec.split(","):
        cik_str, year_str = chunk.split(":")
        pairs.append((int(cik_str), int(year_str)))
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", default="fy2025")
    parser.add_argument("--targets", default=None, help="cik:year,cik:year,...")
    args = parser.parse_args()

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
