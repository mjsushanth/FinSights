import pandas as pd

from derived_kpis import compute_operating_income


def _df(rows: dict[str, str]):
    """rows: {label: value_for_2023}"""
    return pd.DataFrame([{"label": label, "2023-12-31": value} for label, value in rows.items()])


def test_tier1_exact_operating_income_tag():
    df = _df({"Operating Income": "500", "Gross Profit": "9999"})  # tier 3 data present but should be ignored
    s = compute_operating_income(df)
    assert s[2023.0] == 500.0


def test_tier2_income_before_tax_fallback():
    df = _df({"Income Before Tax": "400"})
    s = compute_operating_income(df)
    assert s[2023.0] == 400.0


def test_tier3_manual_reconstruction_fallback():
    df = _df({
        "Gross Profit": "1000",
        "Selling, General and Administrative Expense": "300",
        "Research and development expense": "200",
    })
    s = compute_operating_income(df)
    assert s[2023.0] == 1000.0 - 300.0 - 200.0


def test_no_data_returns_empty_series():
    df = _df({"Unrelated Row": "1"})
    s = compute_operating_income(df)
    assert s.empty


def test_none_input_returns_empty_series():
    assert compute_operating_income(None).empty
