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
