"""
Real-network integration tests, opt-in (marked `integration`, excluded by
`-m "not integration"`). Deliberately test compute_core_kpis_for_company
only (fetches a handful of real filings via MultiFinancials) rather than
the full fetch_10k_facts sweep (91 GAAP concepts x 20 years - correct for
a real production run, far too slow for a test to exercise on every push).

Requires EDGAR_IDENTITY to be set and real network access.

Run with: pytest -m integration src_metrics/tests/test_integration_single_company.py
"""

from __future__ import annotations

import os

import pytest
from edgar import set_identity

from derived_kpis import EXPECTED_DERIVED_LABELS, compute_core_kpis_for_company

pytestmark = pytest.mark.integration

APPLE_CIK = "0000320193"
MASTERCARD_CIK = "0001141391"

_SANITY_RANGES = {
    "Current Ratio": (0, 20),
    "Net Profit Margin %": (-200, 100),
    "Operating Margin %": (-200, 100),
}


@pytest.fixture(scope="module", autouse=True)
def _set_edgar_identity():
    identity = os.getenv("EDGAR_IDENTITY")
    if not identity:
        pytest.skip("EDGAR_IDENTITY not set - skipping real-network integration tests")
    set_identity(identity)


def test_apple_derived_kpis_are_populated_and_sane():
    df = compute_core_kpis_for_company(APPLE_CIK, n_years=2)
    assert not df.empty, "expected at least some derived KPI rows for Apple"

    present_labels = set(df["metric_label"].unique())
    assert present_labels & EXPECTED_DERIVED_LABELS, "no expected derived metrics found at all"

    for label, (lo, hi) in _SANITY_RANGES.items():
        rows = df[df["metric_label"] == label]
        if rows.empty:
            continue  # not every metric is guaranteed present every year - only check what's there
        assert rows["value"].between(lo, hi).all(), f"{label} value out of sane range: {rows['value'].tolist()}"


def test_mastercard_quick_ratio_correctly_absent():
    """Proves the domain-exclusion wiring end to end: Mastercard holds no
    inventory, so Quick Ratio should never be computable/present - this is
    a real data characteristic, not just a config assertion."""
    df = compute_core_kpis_for_company(MASTERCARD_CIK, n_years=2)
    present_labels = set(df["metric_label"].unique()) if not df.empty else set()
    assert "Quick Ratio" not in present_labels
