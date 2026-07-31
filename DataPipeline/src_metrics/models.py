"""
models.py - typed dataclasses for the real entities this module works
with. Plain data containers, no behavior beyond what's trivial to inline -
these represent things (a company, a GAAP tag, a domain rule), they don't
drive a process. The one place a real class belongs (MetricsPipeline,
which drives a multi-step stateful workflow) lives in pipeline.py instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl


@dataclass(frozen=True)
class Company:
    cik_int: int
    cik: str
    name: str
    ticker: str

    @property
    def cik_padded(self) -> str:
        return f"{self.cik_int:010d}"


@dataclass(frozen=True)
class GaapTagInfo:
    canonical_key: str
    human_label: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainRule:
    cik: str
    company: str
    reason: str
    excluded_metrics: tuple[str, ...]


def load_companies(dimension_path: Path) -> list[Company]:
    """Reads the company dimension parquet - the single source of the
    company universe. Growing the roster is changing which file this path
    points at (metrics_config.yaml), never editing this function."""
    df = pl.read_parquet(dimension_path)
    return [
        Company(
            cik_int=row["cik_int"],
            cik=row["cik"],
            name=row["company_name"],
            ticker=row["ticker"],
        )
        for row in df.iter_rows(named=True)
    ]
