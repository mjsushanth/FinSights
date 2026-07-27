"""
coverage.py - the non-regression guard for incremental KPI merges: only
accept a new run's output if derived-metric coverage is provably no worse
than what's already there. Preserved from src_metrics_legacy/analytical_layer.py
(compute_total_missing_derived) - this was already a genuinely good idea,
it just had zero test coverage and one real bug (fixed below).

Bug fixed: the legacy compute_total_missing_derived called
diagnose_derived_coverage_from_df(df, cik, verbose=False) without passing
its own not_applicable_by_cik argument through - so exclusions were only
applied in the "company has zero rows at all" branch, not in the normal
per-year missing-metric count. A company's excluded metrics (e.g.
Mastercard's Quick Ratio) were silently still counted as "missing" in the
common case. Fixed by threading not_applicable_by_cik through both paths.
"""

from __future__ import annotations

import pandas as pd

from models import DomainRule


def diagnose_derived_coverage_from_df(
    df: pd.DataFrame,
    cik: str,
    expected_labels: set[str],
    excluded_metrics: set[str],
    verbose: bool = True,
) -> dict[int, dict[str, list[str]]]:
    """For one CIK, returns {year: {present, not_applicable, missing}}."""
    df_cik = df[df["cik"] == cik].copy()
    if df_cik.empty:
        if verbose:
            print(f"No rows found for CIK {cik}")
        return {}

    df_cik["year"] = df_cik["year"].astype(int)

    metrics_by_year = (
        df_cik[df_cik["metric_type"] == "derived"]
        .groupby("year")["metric_label"]
        .apply(set)
        .to_dict()
    )

    results = {}
    if verbose:
        print("============ DERIVED COVERAGE DIAG ============")

    for year, have in sorted(metrics_by_year.items()):
        effective_expected = expected_labels - excluded_metrics
        missing = sorted(effective_expected - have)

        results[year] = {
            "present": sorted(have),
            "not_applicable": sorted(excluded_metrics),
            "missing": missing,
        }

        if verbose:
            print(f"\nYear {year}")
            print(f"  present        ({len(have)}): {sorted(have)}")
            print(f"  not_applicable ({len(excluded_metrics)}): {sorted(excluded_metrics)}")
            print(f"  missing        ({len(missing)}): {missing}")

    return results


def compute_total_missing_derived(
    df: pd.DataFrame,
    years: set[int],
    ciks: list[str],
    domain_rules: dict[str, DomainRule],
    expected_labels: set[str],
) -> int:
    """Total missing derived metrics across `ciks` for `years`. Lower is
    better coverage - used to gate whether a new run's output is accepted."""
    total_missing = 0
    df = df.copy()
    df["year"] = df["year"].astype(int)

    for cik in ciks:
        rule = domain_rules.get(cik)
        excluded = set(rule.excluded_metrics) if rule else set()

        df_cik = df[
            (df["cik"] == cik) & (df["metric_type"] == "derived") & (df["year"].isin(years))
        ]

        if df_cik.empty:
            applicable = expected_labels - excluded
            total_missing += len(applicable) * len(years)
            continue

        missing_by_year = diagnose_derived_coverage_from_df(
            df, cik, expected_labels, excluded, verbose=False
        )
        for year, info in missing_by_year.items():
            if int(year) in years:
                total_missing += len(info["missing"])

    return total_missing


def find_regressed_keys(
    current_df: pd.DataFrame,
    merged_df: pd.DataFrame,
    domain_rules: dict[str, DomainRule],
    expected_labels: set[str],
) -> list[dict]:
    """Precise non-regression check: for every (cik, year) pair that
    already had at least one derived metric in `current_df`, compare its
    missing-metric count against the same (cik, year) in `merged_df`.
    Returns only the pairs that got WORSE.

    This exists instead of a global "total missing across all years"
    comparison (compute_total_missing_derived's original use) because that
    approach has a real false-positive: adding a genuinely NEW year (e.g.
    a just-filed FY2025, naturally partial - real ratios take a few years
    of filings to all become computable) looks identical to "existing data
    got worse" once you're just comparing two grand totals. A brand-new
    (cik, year) pair can't have regressed, since there was nothing there
    before to regress from - so it's simply excluded from this comparison,
    rather than relying on a `years` parameter to approximate the same
    thing at the wrong granularity (a year that's new for one company can
    already exist in the table for a different company, defeating a
    global year-set filter)."""
    current_df = current_df.copy()
    merged_df = merged_df.copy()
    current_df["year"] = current_df["year"].astype(int)
    merged_df["year"] = merged_df["year"].astype(int)

    old_derived = current_df[current_df["metric_type"] == "derived"]
    existing_keys = old_derived[["cik", "year"]].drop_duplicates()

    regressions = []
    for _, row in existing_keys.iterrows():
        cik, year = row["cik"], int(row["year"])
        rule = domain_rules.get(cik)
        excluded = set(rule.excluded_metrics) if rule else set()
        effective_expected = expected_labels - excluded

        old_present = set(
            old_derived[(old_derived["cik"] == cik) & (old_derived["year"] == year)]["metric_label"]
        )
        new_present = set(
            merged_df[
                (merged_df["cik"] == cik) & (merged_df["year"] == year) & (merged_df["metric_type"] == "derived")
            ]["metric_label"]
        )

        old_missing = len(effective_expected - old_present)
        new_missing = len(effective_expected - new_present)
        if new_missing > old_missing:
            regressions.append({
                "cik": cik, "year": year, "old_missing": old_missing, "new_missing": new_missing,
                "lost_metrics": sorted(old_present - new_present),
            })

    return regressions
