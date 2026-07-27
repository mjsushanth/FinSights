"""
Stage 1: fetch_filings.py

Resolves a manifest of real, fetchable 10-K filings for a set of
(cik_int, report_year) targets. "report_year" means the fiscal-period-end
year (Filing.report_date.year) - NOT the filing year - matching the
convention already used in finrag_fact_sentences.parquet (see PLAN.md).

Output is metadata only (accession_no, form, filing_date, report_date,
filing_url) - no section text yet - so this stage is fast and safely
re-runnable without re-parsing HTML on every retry.
"""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl
from edgar import Company, set_identity

EDGAR_IDENTITY = os.getenv("EDGAR_IDENTITY", "your-email@example.com")

MODULE_DIR = Path(__file__).parent
DIM_COMPANIES_21 = MODULE_DIR.parent / "data_cache" / "dimensions" / "finrag_dim_companies_21.parquet"
MANIFEST_DIR = MODULE_DIR / "manifests"

# Companies already at FY2025 in the production fact table (verified this
# session via direct read of finrag_fact_sentences.parquet) - excluded from
# the default FY2025 target set.
ALREADY_AT_FY2025 = {104169, 789019, 1045810, 1341439, 909832}  # Walmart, Microsoft, NVIDIA, Oracle, Costco


def resolve_filing_for_year(company: Company, target_report_year: int):
    """Find the single 10-K whose report_date (fiscal year end) falls in
    target_report_year. Filing date lags report_date by 1-3 months, so a
    generous filing_date window is searched, then the exact filing is
    selected by report_date.year - never by filing_date.year."""
    window = f"{target_report_year}-01-01:{target_report_year + 1}-06-30"
    candidates = company.get_filings(form="10-K", amendments=False).filter(filing_date=window)
    for f in candidates:
        # f.report_date comes back as a "YYYY-MM-DD" string, not a date object
        if f.report_date and str(f.report_date)[:4] == str(target_report_year):
            return f
    return None


def fetch_manifest(targets: list[tuple[int, int]]) -> pl.DataFrame:
    """targets: list of (cik_int, report_year) pairs to resolve."""
    rows = []
    company_cache: dict[int, Company] = {}

    for cik_int, report_year in targets:
        company = company_cache.setdefault(cik_int, Company(cik_int))
        filing = resolve_filing_for_year(company, report_year)

        base = {
            "cik_int": cik_int,
            "cik": f"{cik_int:010d}",
            "name": company.name,
            "tickers": company.tickers,
            "sic": company.sic,
            "target_report_year": report_year,
        }
        if filing is None:
            print(f"  MISSING: cik={cik_int} ({company.name}) report_year={report_year}")
            rows.append({
                **base, "found": False, "accession_no": None, "form": None,
                "filing_date": None, "report_date": None, "filing_url": None,
            })
            continue

        print(f"  found: cik={cik_int} ({company.name}) report_year={report_year} "
              f"-> {filing.accession_no}")
        rows.append({
            **base,
            "found": True,
            "accession_no": filing.accession_no,
            "form": filing.form,
            "filing_date": str(filing.filing_date),
            "report_date": str(filing.report_date),
            "filing_url": filing.filing_url,
        })

    return pl.DataFrame(rows)


def default_fy2025_targets() -> list[tuple[int, int]]:
    """The resolved default backfill scope: FY2025 for the 16 companies not
    yet at FY2025 in the production fact table (PLAN.md, decision 5)."""
    dim = pl.read_parquet(DIM_COMPANIES_21)
    return [(cik, 2025) for cik in dim["cik_int"].to_list() if cik not in ALREADY_AT_FY2025]


def run(targets: list[tuple[int, int]], out_name: str) -> pl.DataFrame:
    set_identity(EDGAR_IDENTITY)
    print(f"Resolving {len(targets)} (cik, report_year) targets...")

    manifest = fetch_manifest(targets)

    MANIFEST_DIR.mkdir(exist_ok=True)
    out_path = MANIFEST_DIR / out_name
    manifest.write_parquet(out_path)

    n_found = int(manifest["found"].sum())
    print(f"\nFound {n_found}/{len(manifest)} filings. Manifest written to {out_path}")
    return manifest


if __name__ == "__main__":
    run(default_fy2025_targets(), "fy2025_manifest.parquet")
