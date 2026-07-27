"""
xbrl_facts.py - fetches raw SEC XBRL facts for a company via edgartools'
EntityFacts.query(), and the numeric/label-normalization helpers shared
with derived_kpis.py.

Ported from src_metrics_legacy/analytical_layer.py. The extraction logic
itself (numeric cleaning, year-column parsing) is unchanged - what changed
is that every function takes its inputs as parameters (gaap_registry,
concepts, year range) instead of reaching for a module-level hardcoded
constant, so this module has no company-specific or environment-specific
state baked into it at all.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from edgar import Company

from models import GaapTagInfo


def pad_cik(cik) -> str:
    s = "".join(ch for ch in str(cik) if ch.isdigit())
    return s.zfill(10)


def raw_cik(cik) -> str:
    s = "".join(ch for ch in str(cik) if ch.isdigit())
    return s.lstrip("0") or "0"


def strip_namespace(metric: str) -> str | None:
    if not isinstance(metric, str):
        return None
    if ":" in metric:
        return metric.split(":", 1)[1]
    return metric


def normalize_metric_key(raw_metric: str, gaap_registry: dict[str, GaapTagInfo]) -> str | None:
    """raw_metric e.g. 'us-gaap:NetIncomeLoss' -> canonical_key via the registry."""
    code = strip_namespace(raw_metric)
    if not code:
        return None
    info = gaap_registry.get(code)
    return info.canonical_key if info else None


def normalize_metric_label(raw_metric: str, gaap_registry: dict[str, GaapTagInfo]) -> str:
    """raw_metric e.g. 'us-gaap:NetIncomeLoss' -> 'Net Income' or a
    CamelCase-split fallback if the tag isn't in the registry."""
    code = strip_namespace(raw_metric)
    if not code:
        return ""
    info = gaap_registry.get(code)
    if info:
        return info.human_label
    s = re.sub(r"(?<!^)(?=[A-Z])", " ", code)
    return " ".join(s.split())


def cols_to_year_index(cols):
    yrs = pd.to_datetime(cols, errors="coerce", format="%Y-%m-%d").year
    yrs = [
        y if not pd.isna(y)
        else (int(re.search(r"(20\d{2})", str(c)).group(1)) if re.search(r"(20\d{2})", str(c)) else np.nan)
        for c, y in zip(cols, yrs)
    ]
    return pd.Index(yrs, dtype="float64")


def clean_numeric_series(s: pd.Series) -> pd.Series:
    """Handles SEC's common numeric formatting quirks: thousands
    separators, parenthetical negatives, em/en dashes for blank, $ signs."""
    s = (
        s.astype(str)
         .str.replace(",", "", regex=False)
         .str.replace(r"\((.*)\)", r"-\1", regex=True)
         .str.replace("—", "", regex=False)
         .str.replace("–", "", regex=False)
         .str.replace("$", "", regex=False)
         .str.strip()
    )
    return pd.to_numeric(s, errors="coerce")


def fetch_10k_facts(
    cik: str,
    gaap_registry: dict[str, GaapTagInfo],
    start_year: int,
    end_year: int,
    forms: set[str] = frozenset({"10-K", "10-K/A"}),
) -> pd.DataFrame:
    """Builds a long-format GAAP facts table for one company:
    cik, ticker, year, metric_gaap, metric_code, metric_key, metric_label,
    metric_type="gaap", value, unit, form, filed_date, accession_no."""
    cik10 = pad_cik(cik)
    co = Company(raw_cik(cik))
    facts = co.facts
    ticker = co.get_ticker()

    concepts = list(gaap_registry.keys())
    rows = []

    for concept in concepts:
        for year in range(start_year, end_year + 1):
            q = (
                facts.query()
                     .by_concept(concept)
                     .by_form_type(forms)
                     .by_fiscal_year(year)
                     .sort_by("filing_date", ascending=True)
            )
            dfp = q.to_dataframe(
                "concept", "numeric_value", "unit",
                "fiscal_year", "fiscal_period",
                "filing_date", "form_type", "accession",
            )
            if dfp is None or dfp.empty:
                continue

            dfp = dfp.sort_values(["fiscal_year", "filing_date"]).tail(1)

            for _, r in dfp.iterrows():
                val = r.get("numeric_value", r.get("value"))
                if val is None:
                    continue

                metric_gaap = r["concept"]
                rows.append({
                    "cik": cik10,
                    "ticker": ticker,
                    "year": int(r["fiscal_year"]),
                    "metric_gaap": metric_gaap,
                    "metric_code": metric_gaap,
                    "metric_key": normalize_metric_key(metric_gaap, gaap_registry),
                    "metric_label": normalize_metric_label(metric_gaap, gaap_registry),
                    "metric_type": "gaap",
                    "value": float(val),
                    "unit": r.get("unit"),
                    "form": r.get("form_type"),
                    "filed_date": str(r.get("filing_date")),
                    "accession_no": r.get("accession"),
                })

    columns = [
        "cik", "ticker", "year", "metric_gaap", "metric_code", "metric_key",
        "metric_label", "metric_type", "value", "unit", "form", "filed_date", "accession_no",
    ]
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)
