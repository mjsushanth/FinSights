import pandas as pd

from derived_kpis import _roe_avg_equity


def test_roe_suppressed_when_equity_negative():
    net = pd.Series({2020: 100.0, 2021: 100.0, 2022: 100.0})
    eq = pd.Series({2020: 1000.0, 2021: -50.0, 2022: 1000.0})  # 2021 negative equity
    roe = _roe_avg_equity(net, eq)
    assert pd.isna(roe.get(2021))  # this year's equity negative -> suppressed
    assert pd.isna(roe.get(2022))  # prior year negative -> average unreliable -> suppressed


def test_roe_computed_when_equity_positive():
    net = pd.Series({2020: 100.0, 2021: 100.0})
    eq = pd.Series({2020: 1000.0, 2021: 1000.0})
    roe = _roe_avg_equity(net, eq)
    assert round(roe.get(2021), 4) == 10.0  # 100 / ((1000 + 1000) / 2) * 100
