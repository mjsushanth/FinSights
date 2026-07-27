import math

import pandas as pd
import pytest

from xbrl_facts import clean_numeric_series


@pytest.mark.parametrize("raw,expected", [
    ("1,234", 1234.0),
    ("1,234,567", 1234567.0),
    ("(123)", -123.0),
    ("(1,234)", -1234.0),
    ("$1,000", 1000.0),
    ("42", 42.0),
])
def test_clean_numeric_series_parses_common_formats(raw, expected):
    result = clean_numeric_series(pd.Series([raw]))
    assert result.iloc[0] == expected


@pytest.mark.parametrize("raw", ["—", "–", "", "  "])
def test_clean_numeric_series_blank_markers_become_nan(raw):
    result = clean_numeric_series(pd.Series([raw]))
    assert math.isnan(result.iloc[0])
