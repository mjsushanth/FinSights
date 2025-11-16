from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List


@dataclass(frozen=True)
class CompanyInfo:
    """
    Canonical representation of a single company row from the dimension table.
    """
    company_id: int
    cik_int: int          # integer CIK, primary for filters
    cik_str: str          # zero-padded string "0000320193"
    ticker: Optional[str]
    name: str


@dataclass
class CompanyMatches:
    """
    Result of running company extraction on a natural-language query.

    - ciks_int:   distinct integer CIKs matched in the query
    - ciks_str:   distinct zero-padded CIK strings matched
    - tickers:    distinct tickers matched (uppercased)
    - names:      distinct canonical company names matched
    """
    ciks_int: List[int]
    ciks_str: List[str]
    tickers: List[str]
    names: List[str]

    def is_empty(self) -> bool:
        return not (self.ciks_int or self.ciks_str or self.tickers or self.names)


@dataclass
class YearMatches:
    """
    Result of running year extraction on a natural-language query.

    Attributes
    ----------
    years:
        All distinct years found in the query (sorted ascending).
        Includes past, current, and future years.
    past_years:
        Years strictly less than the current calendar year.
    current_years:
        Either [] or [current_year], depending on whether it was mentioned.
    future_years:
        Years strictly greater than the current calendar year.
    warning:
        Optional human-readable message about current/future years that
        the caller can log or surface to the user.

    Notes
    -----
    This adapter does *not* block or drop current/future years. It
    reports everything and leaves the decision about filtering (to avoid
    S3 cost, etc.) to the caller.
    """
    years: List[int]
    past_years: List[int]
    current_years: List[int]
    future_years: List[int]
    warning: Optional[str] = None

    @property
    def has_any(self) -> bool:
        return bool(self.years)

    @property
    def has_past(self) -> bool:
        return bool(self.past_years)

    @property
    def has_current(self) -> bool:
        return bool(self.current_years)

    @property
    def has_future(self) -> bool:
        return bool(self.future_years)


@dataclass
class MetricMatches:
    """
    Result of running metric extraction on a natural-language query.

    For now we only need the canonical metric IDs; there is no notion of
    past/current/future like years, so this stays simple.

    Example:
        metrics = ["income_stmt_Revenue", "income_stmt_Net Income"]
    """
    metrics: List[str]

    @property
    def has_any(self) -> bool:
        return bool(self.metrics)



@dataclass
class SectionMatches:
    """
    Result of running section extraction on a natural-language query.

    Attributes
    ----------
    items:
        Distinct sec_item_canonical values (e.g. "ITEM_7", "ITEM_1A").
    primary:
        Optional "best guess" primary section to use for strict filters.
        If None, the caller may apply defaults (e.g. fallback to ITEM_7).
    """
    items: List[str]
    primary: Optional[str] = None

    @property
    def has_any(self) -> bool:
        return bool(self.items)


@dataclass
class RiskMatches:
    """
    Result of running risk-topic extraction on a natural-language query.

    Attributes
    ----------
    topics:
        List of topic labels from RISK_TOPIC_KEYWORDS, e.g.
        ["liquidity_credit", "regulatory", ...]
    """
    topics: List[str]

    @property
    def has_any(self) -> bool:
        return bool(self.topics)



