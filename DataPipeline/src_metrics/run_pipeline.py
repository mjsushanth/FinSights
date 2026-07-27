"""
run_pipeline.py - CLI/CI entrypoint. Replaces run_pipeline_gh.py.

Usage:
    python run_pipeline.py                       # all companies in the dimension table
    python run_pipeline.py --cik 320193 --cik 1141391   # just these companies (e.g. for testing)
"""

from __future__ import annotations

import argparse
import sys

from pipeline import MetricsPipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cik", action="append", type=int, default=None,
                         help="restrict to specific CIK(s) (int, repeatable); default: all companies in the dimension table")
    args = parser.parse_args()

    pipeline = MetricsPipeline()

    companies = None
    if args.cik:
        wanted = set(args.cik)
        companies = [c for c in pipeline.companies if c.cik_int in wanted]
        missing = wanted - {c.cik_int for c in companies}
        if missing:
            print(f"Warning: CIK(s) not found in the dimension table: {missing}")

    try:
        pipeline.run(companies=companies)
    except Exception as e:
        print(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
