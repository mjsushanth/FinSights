import pandas as pd

from coverage import compute_total_missing_derived
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
