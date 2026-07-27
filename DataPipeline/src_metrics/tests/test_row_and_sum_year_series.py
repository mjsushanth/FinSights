import pandas as pd

from derived_kpis import _row_to_year_series, _sum_rows_to_year_series


def _stmt_df(label, values_by_col):
    row = {"label": label, **values_by_col}
    return pd.DataFrame([row])


def test_row_to_year_series_matches_alias_case_insensitively():
    df = _stmt_df("net income", {"2023-12-31": "1,000", "2022-12-31": "900"})
    s = _row_to_year_series(df, ["Net Income"])
    assert s[2023.0] == 1000.0
    assert s[2022.0] == 900.0


def test_row_to_year_series_no_match_returns_empty():
    df = _stmt_df("Some Other Row", {"2023-12-31": "1,000"})
    s = _row_to_year_series(df, ["Net Income"])
    assert s.empty


def test_row_to_year_series_none_input_returns_empty():
    assert _row_to_year_series(None, ["Net Income"]).empty


def test_row_to_year_series_keeps_last_per_year_on_duplicate_columns():
    # two columns that resolve to the same year - later column should win
    df = pd.DataFrame([{"label": "Net Income", "2023-12-31": "100", "2023-06-30": "999"}])
    s = _row_to_year_series(df, ["Net Income"])
    assert s[2023.0] == 999.0  # last column in iteration order wins


def test_sum_rows_to_year_series_sums_multiple_matching_rows():
    df = pd.DataFrame([
        {"label": "Total Current Liabilities", "2023-12-31": "100"},
        {"label": "Total Non Current Liabilities", "2023-12-31": "50"},
    ])
    s = _sum_rows_to_year_series(df, ["Total Current Liabilities", "Total Non Current Liabilities"])
    assert s[2023.0] == 150.0


def test_sum_rows_to_year_series_no_matches_returns_empty():
    df = _stmt_df("Unrelated", {"2023-12-31": "1"})
    assert _sum_rows_to_year_series(df, ["Total Current Liabilities"]).empty
