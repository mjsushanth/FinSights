import pandas as pd

from coverage import compute_total_missing_derived, find_regressed_keys
from models import DomainRule

EXPECTED = {"Current Ratio", "Quick Ratio", "Free Cash Flow"}


def _derived_rows(cik: str, year: int, labels: list[str]) -> list[dict]:
    return [{"cik": cik, "year": year, "metric_type": "derived", "metric_label": label} for label in labels]


def test_full_coverage_has_zero_missing():
    df = pd.DataFrame(_derived_rows("0000000001", 2023, list(EXPECTED)))
    missing = compute_total_missing_derived(df, {2023}, ["0000000001"], {}, EXPECTED)
    assert missing == 0


def test_missing_one_metric_counts_as_one():
    df = pd.DataFrame(_derived_rows("0000000001", 2023, ["Current Ratio", "Quick Ratio"]))  # missing FCF
    missing = compute_total_missing_derived(df, {2023}, ["0000000001"], {}, EXPECTED)
    assert missing == 1


def test_domain_rule_exclusion_is_not_counted_as_missing():
    df = pd.DataFrame(_derived_rows("0000000001", 2023, ["Current Ratio"]))  # missing Quick Ratio + FCF
    rules = {"0000000001": DomainRule("0000000001", "Test Co", "no inventory",
                                       ("Quick Ratio", "Free Cash Flow"))}
    missing = compute_total_missing_derived(df, {2023}, ["0000000001"], rules, EXPECTED)
    assert missing == 0  # both gaps are excluded, so nothing is "missing"


def test_no_rows_at_all_counts_full_expected_set_as_missing():
    df = pd.DataFrame(columns=["cik", "year", "metric_type", "metric_label"])
    missing = compute_total_missing_derived(df, {2023}, ["0000000001"], {}, EXPECTED)
    assert missing == len(EXPECTED)


def test_regression_detected_between_two_runs():
    """The actual non-regression-guard scenario: old run had full coverage,
    new run lost a metric - the caller (MetricsPipeline.merge_and_validate)
    compares these two counts and should refuse to merge."""
    old_df = pd.DataFrame(_derived_rows("0000000001", 2023, list(EXPECTED)))
    new_df = pd.DataFrame(_derived_rows("0000000001", 2023, ["Current Ratio"]))

    old_missing = compute_total_missing_derived(old_df, {2023}, ["0000000001"], {}, EXPECTED)
    new_missing = compute_total_missing_derived(new_df, {2023}, ["0000000001"], {}, EXPECTED)

    assert old_missing == 0
    assert new_missing == 2
    assert new_missing > old_missing  # this is the condition that should block a merge


def test_new_partial_year_is_not_counted_as_regression_when_scoped_correctly():
    """Found live during the real production run: adding a genuinely new
    year (e.g. a just-filed FY2025) that's only partially covered (5/10
    metrics) looked like a regression when compared over an ever-expanding
    all-years grid, even though not a single existing (cik,year) row
    actually got worse - confirmed by direct inspection of the real merge.
    MetricsPipeline.merge_and_validate now scopes its comparison to only
    the years the OLD table already had - this test proves that scoping
    is what makes the new-partial-year case correctly NOT look like a
    regression, while test_regression_detected_between_two_runs above
    proves a genuine regression on an EXISTING year is still caught."""
    old_df = pd.DataFrame(_derived_rows("0000000001", 2023, list(EXPECTED)))  # full coverage, 2023 only
    # merged now also has a brand-new 2024 row with partial coverage
    new_row_2023 = _derived_rows("0000000001", 2023, list(EXPECTED))
    new_row_2024_partial = _derived_rows("0000000001", 2024, ["Current Ratio"])
    merged_df = pd.DataFrame(new_row_2023 + new_row_2024_partial)

    # Correct: compare only over years the old table had (2023) - matches
    # MetricsPipeline.merge_and_validate's `comparison_years` scoping.
    old_missing_scoped = compute_total_missing_derived(old_df, {2023}, ["0000000001"], {}, EXPECTED)
    new_missing_scoped = compute_total_missing_derived(merged_df, {2023}, ["0000000001"], {}, EXPECTED)
    assert new_missing_scoped == old_missing_scoped == 0  # no regression - 2023 is untouched

    # For contrast: the OLD (buggy) approach of scoping to the FULL merged
    # year range would have flagged this as a regression, confirming the
    # fix actually changes the outcome, not just the code path.
    all_years_unscoped = {2023, 2024}
    old_missing_unscoped = compute_total_missing_derived(old_df, all_years_unscoped, ["0000000001"], {}, EXPECTED)
    new_missing_unscoped = compute_total_missing_derived(merged_df, all_years_unscoped, ["0000000001"], {}, EXPECTED)
    assert new_missing_unscoped > old_missing_unscoped  # this is the false-positive the fix avoids


# --- find_regressed_keys: the actual function MetricsPipeline.merge_and_validate uses ---

def test_find_regressed_keys_ignores_brand_new_company():
    """A company with zero rows in `current` (e.g. this session's 4 newly
    added companies) can't regress - there's nothing to compare against."""
    current = pd.DataFrame(_derived_rows("0000000001", 2023, list(EXPECTED)))
    merged = pd.DataFrame(
        _derived_rows("0000000001", 2023, list(EXPECTED))
        + _derived_rows("0000000002", 2023, ["Current Ratio"])  # brand new company, partial coverage
    )
    regressions = find_regressed_keys(current, merged, {}, EXPECTED)
    assert regressions == []


def test_find_regressed_keys_ignores_brand_new_partial_year():
    """The exact real scenario found during the production run: a new,
    naturally-partial year (e.g. a just-filed FY2025) is not a regression."""
    current = pd.DataFrame(_derived_rows("0000000001", 2023, list(EXPECTED)))
    merged = pd.DataFrame(
        _derived_rows("0000000001", 2023, list(EXPECTED))
        + _derived_rows("0000000001", 2024, ["Current Ratio"])  # new year, only 1/3 metrics
    )
    regressions = find_regressed_keys(current, merged, {}, EXPECTED)
    assert regressions == []


def test_find_regressed_keys_catches_a_real_regression():
    """An EXISTING (cik, year) that had full coverage and loses a metric
    in the new data - the one thing this guard must actually catch."""
    current = pd.DataFrame(_derived_rows("0000000001", 2023, list(EXPECTED)))
    merged = pd.DataFrame(_derived_rows("0000000001", 2023, ["Current Ratio"]))  # lost 2 of 3
    regressions = find_regressed_keys(current, merged, {}, EXPECTED)
    assert len(regressions) == 1
    assert regressions[0]["cik"] == "0000000001"
    assert regressions[0]["year"] == 2023
    assert set(regressions[0]["lost_metrics"]) == {"Quick Ratio", "Free Cash Flow"}


def test_find_regressed_keys_respects_domain_exclusions():
    """A metric that's excluded via a domain rule should never count as a
    regression even if it's absent in both current and merged."""
    rules = {"0000000001": DomainRule("0000000001", "Test Co", "no inventory", ("Quick Ratio",))}
    current = pd.DataFrame(_derived_rows("0000000001", 2023, ["Current Ratio", "Free Cash Flow"]))
    merged = pd.DataFrame(_derived_rows("0000000001", 2023, ["Current Ratio", "Free Cash Flow"]))
    regressions = find_regressed_keys(current, merged, rules, EXPECTED)
    assert regressions == []
