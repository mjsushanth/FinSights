"""
derived_kpis.py - computes the 10 derived KPI ratios (Current Ratio,
Debt-to-Equity, Free Cash Flow, ...) from a company's MultiFinancials
statements.

Ported from src_metrics_legacy/analytical_layer.py. The extraction/
derivation logic (multi-alias label matching across SEC's inconsistent
statement-row naming, the 3-tier operating-income fallback) is unchanged -
this is the part of the legacy module that was genuinely well-built. What
changed: every function takes a `cik` and returns/consumes plain
DataFrames, with no module-level company list or config reached for.

STATEMENT_LABEL_ALIASES stays a Python constant (not YAML) - unlike the
GAAP tag registry or the per-company domain rules, this is a fixed,
small, code-adjacent lookup table of statement-row label synonyms, not
data that grows with the company roster or has previously had a
structural bug. Promoting it to YAML wouldn't fix anything real.
"""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd
from edgar import Company, MultiFinancials

from xbrl_facts import pad_cik, raw_cik, clean_numeric_series, cols_to_year_index

STATEMENT_LABEL_ALIASES: dict[str, list[str]] = {
    # Aliases below marked "2026-07-27" were added after a real-data domain
    # review of the 4 newly-added companies (UnitedHealth, Northrop Grumman,
    # Caterpillar, T-Mobile) - see analytics/03_kpi_domain_review_new_companies.ipynb.
    # Confirmed via direct inspection of each company's actual statement row
    # labels that these were genuine label-coverage gaps (this company just
    # uses different wording for the same line item), not a sign the metric
    # is inapplicable to the company.
    "Revenue": [
        "Revenue", "Revenues", "Sales Revenue, Net", "SalesRevenueNet", "SalesRevenueServicesNet",
        "Product Revenue", "Contract Revenue", "Sales and other operating revenue",
        "Total revenues and other income", "Sales and Operating Revenue", "Sales and Operating Revenues",
        "Total revenues", "Total sales and revenues",  # 2026-07-27: UnitedHealth, Caterpillar
    ],
    "OperatingIncome": [
        "Operating Income", "Operating Income (Loss)", "OperatingIncomeLoss",
        "Income Before Tax from Continuing Operations", "Income Before Tax",
        "Earnings from operations", "Operating profit",  # 2026-07-27: UnitedHealth, Caterpillar
        "Total income before income taxes",  # 2026-07-27: UnitedHealth (tier-2 fallback wording)
    ],
    "NetIncome": [
        "Net Income", "Net Income (Loss)", "NetIncomeLoss", "Net Income from Continuing Operations",
        "Net earnings", "Profit (loss)",  # 2026-07-27: UnitedHealth/Northrop Grumman, Caterpillar
    ],
    "TotalAssets": ["Total Assets", "Assets"],
    "TotalLiabilities": ["Total Liabilities", "Liabilities", "Total Liabilities and Stockholders' Equity"],
    "Equity": [
        "Stockholders’ Equity", "Stockholders' Equity", "Total equity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity", "Total Stockholders' Equity", "Stockholders' Equity before Treasury Stock",
        "Total shareholders’ equity", "Total shareholders' equity",  # 2026-07-27: Northrop Grumman ("shareholders" not "stockholders")
    ],
    "CurrentAssets": ["Current Assets", "Assets, Current", "AssetsCurrent", "Total Current Assets"],
    "CurrentLiabilities": ["Current Liabilities", "Liabilities, Current", "LiabilitiesCurrent", "Total Current Liabilities"],
    "Inventory": [
        "Inventory, Net", "InventoryNet", "Inventory", "Crude oil, products and merchandise",
        "Materials and supplies",
        "Inventoried costs, net",  # 2026-07-27: Northrop Grumman (contract-cost inventory, not goods inventory)
    ],
    "CFO": [
        "Net Cash from Operating Activities", "Net Cash Provided by (Used in) Operating Activities",
        "Net Cash Provided by Operating Activities", "NetCashProvidedByUsedInOperatingActivities",
        "Cash flows from operating activities",  # 2026-07-27: UnitedHealth (verified this is the real total, not a header - confirmed non-null values)
        "Net cash provided by (used for) operating activities",  # 2026-07-27: Caterpillar
    ],
    "CapEx": [
        "Payments to Acquire Property, Plant and Equipment", "Purchases of property and equipment",
        "Capital Expenditures", "PaymentsToAcquirePropertyPlantAndEquipment",
        "Payments for Property, Plant and Equipment", "Purchases of property, equipment and technology",
        "Purchases of property, equipment, technology and intangible assets",
        "Purchases of property, equipment and capitalized software",  # 2026-07-27: UnitedHealth
        "Capital expenditures – excluding equipment leased to others",  # 2026-07-27: Caterpillar
    ],
}

DERIVED_METRIC_METADATA: dict[str, dict[str, str]] = {
    "Current Ratio": {"canonical_key": "current_ratio", "unit": "ratio"},
    "Quick Ratio": {"canonical_key": "quick_ratio", "unit": "ratio"},
    "Debt-to-Assets": {"canonical_key": "debt_to_assets", "unit": "ratio"},
    "Debt-to-Equity": {"canonical_key": "debt_to_equity", "unit": "ratio"},
    "Free Cash Flow": {"canonical_key": "free_cash_flow", "unit": "USD"},
    "Operating Cash Flow Ratio": {"canonical_key": "operating_cf_ratio", "unit": "ratio"},
    "Operating Margin %": {"canonical_key": "operating_margin", "unit": "percent"},
    "Net Profit Margin %": {"canonical_key": "net_profit_margin", "unit": "percent"},
    "ROA % (Avg Assets)": {"canonical_key": "roa", "unit": "percent"},
    "ROE % (Avg Equity)": {"canonical_key": "roe", "unit": "percent"},
}

EXPECTED_DERIVED_LABELS: set[str] = set(DERIVED_METRIC_METADATA.keys())


def _avg_series(s: pd.Series) -> pd.Series:
    return (s + s.shift(1)) / 2


def _sdiv(a: pd.Series | None, b: pd.Series | None) -> pd.Series:
    if a is None or b is None:
        return pd.Series(dtype="float64")
    out = a.astype("float64") / b.astype("float64")
    return out.replace([np.inf, -np.inf], np.nan)


def _normalize_stmt_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return df
    if "label" not in df.columns:
        if "Label" in df.columns:
            df = df.rename(columns={"Label": "label"})
        elif df.index.name == "label":
            df = df.reset_index()
    return df


def _row_to_year_series(stmt_df: pd.DataFrame | None, label_aliases: List[str]) -> pd.Series:
    if stmt_df is None or stmt_df.empty:
        return pd.Series(dtype="float64")

    labels_norm = stmt_df["label"].astype(str).str.strip().str.lower()
    for alias in label_aliases:
        row = stmt_df.loc[labels_norm == alias.strip().lower()]
        if not row.empty:
            s = row.iloc[0].drop(labels=["label"])
            s.index = cols_to_year_index(s.index)
            s = clean_numeric_series(s)
            s = s[s.index.notna()]
            return s.groupby(level=0).last()

    return pd.Series(dtype="float64")


def _sum_rows_to_year_series(stmt_df: pd.DataFrame | None, label_aliases: List[str]) -> pd.Series:
    if stmt_df is None or stmt_df.empty:
        return pd.Series(dtype="float64")

    labels_norm = stmt_df["label"].astype(str).str.strip().str.lower()
    pieces = []
    for alias in label_aliases:
        row = stmt_df.loc[labels_norm == alias.strip().lower()]
        if not row.empty:
            s = row.iloc[0].drop(labels=["label"])
            s.index = cols_to_year_index(s.index)
            s = clean_numeric_series(s)
            s = s[s.index.notna()]
            pieces.append(s.groupby(level=0).last())

    if not pieces:
        return pd.Series(dtype="float64")
    return pd.concat(pieces, axis=1).sum(axis=1, min_count=1)


def _get_stmt_df(mf: MultiFinancials, candidates: List[str]) -> pd.DataFrame | None:
    for name in candidates:
        if hasattr(mf, name):
            stmt = getattr(mf, name)()
            if hasattr(stmt, "to_dataframe"):
                return stmt.to_dataframe()
    return None


def compute_operating_income(inc_df: pd.DataFrame | None) -> pd.Series:
    """3-tier fallback: exact Operating Income tag -> Income Before Tax
    proxy -> manual Gross Profit - SG&A - R&D reconstruction."""
    op = _row_to_year_series(inc_df, ["Operating Income", "Operating Income (Loss)", "OperatingIncomeLoss"])
    if not op.empty:
        return op

    op = _row_to_year_series(inc_df, [
        "Income Before Tax from Continuing Operations", "Income Before Tax",
        "Earnings before provision for taxes on income",
    ])
    if not op.empty:
        return op

    gross_profit = _row_to_year_series(inc_df, ["Gross Profit"])
    sga = _row_to_year_series(inc_df, ["Selling, General and Administrative Expense"])
    rnd = _row_to_year_series(inc_df, ["Research and development expense", "Research and Development Expense"])

    manual = pd.concat([gross_profit, sga, rnd], axis=1)
    manual.columns = ["gp", "sga", "rnd"]
    manual = manual.dropna()
    if not manual.empty:
        return manual["gp"] - manual["sga"] - manual["rnd"]

    return pd.Series(dtype="float64")


def get_total_liabilities_series(bs_df: pd.DataFrame | None) -> pd.Series:
    """Prefers a direct total-liabilities row; falls back to summing
    current + noncurrent liabilities so it works across reporting styles."""
    liab_total = _row_to_year_series(bs_df, ["Total Liabilities", "Liabilities", "Total liabilities"])
    if not liab_total.empty and liab_total.notna().any():
        return liab_total

    return _sum_rows_to_year_series(bs_df, [
        "Total Current Liabilities", "Total Non Current Liabilities", "Total Noncurrent Liabilities",
        "Total current liabilities", "Total non current liabilities", "Total noncurrent liabilities",
    ])


def compute_core_kpis_for_company(cik: str, n_years: int = 8) -> pd.DataFrame:
    """Uses MultiFinancials to compute the 10 derived KPIs for the last
    n_years 10-Ks. Output matches the GAAP-facts schema (metric_type='derived',
    metric_gaap/metric_code/form/filed_date/accession_no all None)."""
    cik10 = pad_cik(cik)
    co = Company(raw_cik(cik))
    ticker = co.get_ticker()

    filings = co.get_filings(form="10-K").head(n_years)
    columns = [
        "cik", "ticker", "year", "metric_gaap", "metric_code", "metric_key",
        "metric_label", "metric_type", "value", "unit", "form", "filed_date", "accession_no",
    ]
    if filings.empty:
        return pd.DataFrame(columns=columns)

    mf = MultiFinancials.extract(filings)
    inc = _normalize_stmt_df(_get_stmt_df(mf, ["income_statement", "income"]))
    bs = _normalize_stmt_df(_get_stmt_df(mf, ["balance_sheet", "balance"]))
    cf = _normalize_stmt_df(_get_stmt_df(mf, ["cashflow_statement", "cash_flow", "cashflow"]))

    rev = _sum_rows_to_year_series(inc, STATEMENT_LABEL_ALIASES["Revenue"])
    opinc = compute_operating_income(inc)
    net = _row_to_year_series(inc, STATEMENT_LABEL_ALIASES["NetIncome"])

    assets = _row_to_year_series(bs, STATEMENT_LABEL_ALIASES["TotalAssets"])
    eq = _row_to_year_series(bs, STATEMENT_LABEL_ALIASES["Equity"])
    liab = get_total_liabilities_series(bs)
    if (liab is None or liab.empty) and bs is not None and not bs.empty:
        tlse = _row_to_year_series(bs, ["Total Liabilities and Stockholders' Equity"])
        if tlse is not None and not tlse.empty and eq is not None and not eq.empty:
            liab = tlse - eq
        else:
            liab = pd.Series(dtype="float64")
    ca = _row_to_year_series(bs, STATEMENT_LABEL_ALIASES["CurrentAssets"])
    cl = _row_to_year_series(bs, STATEMENT_LABEL_ALIASES["CurrentLiabilities"])
    inv = _row_to_year_series(bs, STATEMENT_LABEL_ALIASES["Inventory"])

    cfo = _row_to_year_series(cf, STATEMENT_LABEL_ALIASES["CFO"])
    capex = _row_to_year_series(cf, STATEMENT_LABEL_ALIASES["CapEx"]).abs()

    avg_assets = _avg_series(assets)
    avg_equity = _avg_series(eq)

    idx = rev.index.union(assets.index).union(eq.index).union(cl.index).union(cfo.index)
    metrics = pd.DataFrame(index=idx)
    metrics["Net Profit Margin %"] = _sdiv(net, rev) * 100
    metrics["Operating Margin %"] = _sdiv(opinc, rev) * 100
    metrics["ROA % (Avg Assets)"] = _sdiv(net, avg_assets) * 100
    metrics["ROE % (Avg Equity)"] = _sdiv(net, avg_equity) * 100
    metrics["Current Ratio"] = _sdiv(ca, cl)
    metrics["Quick Ratio"] = _sdiv(ca - inv, cl)
    metrics["Debt-to-Equity"] = _sdiv(liab, eq)
    metrics["Debt-to-Assets"] = _sdiv(liab, assets)
    metrics["Free Cash Flow"] = cfo - capex
    metrics["Operating Cash Flow Ratio"] = _sdiv(cfo, cl)

    long_kpi = (
        metrics.reset_index()
               .rename(columns={"index": "year"})
               .melt(id_vars=["year"], var_name="metric_label", value_name="value")
               .dropna(subset=["value"], how="all")
               .sort_values(["year", "metric_label"])
               .reset_index(drop=True)
    )
    # year comes out of the statement column index as float64 (see
    # cols_to_year_index) - cast to int so it matches the GAAP-facts
    # table's integer year and the production schema (both must agree for
    # a clean merge - a float/int dtype mismatch on the join key broke the
    # first real merge attempt this session).
    long_kpi["year"] = long_kpi["year"].astype(int)

    long_kpi["cik"] = cik10
    long_kpi["ticker"] = ticker
    long_kpi["metric_key"] = long_kpi["metric_label"].apply(
        lambda lbl: DERIVED_METRIC_METADATA.get(lbl, {}).get("canonical_key")
    )
    long_kpi["unit"] = long_kpi["metric_label"].apply(
        lambda lbl: DERIVED_METRIC_METADATA.get(lbl, {}).get("unit")
    )
    long_kpi["metric_gaap"] = None
    long_kpi["metric_code"] = None
    long_kpi["metric_type"] = "derived"
    long_kpi["form"] = None
    long_kpi["filed_date"] = None
    long_kpi["accession_no"] = None

    return long_kpi[columns]
