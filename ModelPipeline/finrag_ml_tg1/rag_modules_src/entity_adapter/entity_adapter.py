
"""
Entity adapter: top-level NL → {company, year, metric, section, risk_topic} extraction.

## Usage example: !

from rag_modules_src.entity_adapter.entity_adapter import EntityAdapter

adapter = EntityAdapter()
queries = [ ... ]

for q in queries:
    res = adapter.extract(q)
    EntityAdapter.debug_print(res)

"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

from .company_universe import CompanyUniverse
from .company_extractor import CompanyExtractor
from .year_extractor import YearExtractor
from .metric_adapter import MetricAdapter
from .section_universe import SectionUniverse
from .section_extractor import SectionExtractor
from .models import CompanyMatches, YearMatches, MetricMatches

logger = logging.getLogger(__name__)


@dataclass
class EntityExtractionResult:
    """
    Unified view of everything we can extract from a user query.

    This is what the RAG orchestrator / metric pipeline should see:

    - companies:   all company-level signals (CIKs, tickers, names)
    - years:       all year signals (past/current/future + warning)
    - metrics:     canonical metric IDs (income_stmt_Revenue, etc.)
    - sections:    all section candidates in canonical SEC form (ITEM_7, ITEM_1A, …)
    - primary_section: single best guess for routing / default filter
    - risk_topics: high-level semantic risk buckets (liquidity_credit, regulatory, …)
    """

    query: str

    companies: CompanyMatches
    years: YearMatches
    metrics: MetricMatches

    sections: List[str]
    primary_section: Optional[str]

    risk_topics: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """
        Lightweight dict view for logging / JSON / passing to other layers.
        Keeps structure but avoids dataclass objects.

        NOTE: does not attempt to be a full schema for external APIs,
        just a convenient, explicit snapshot.
        """
        return {
            "query": self.query,
            "companies": {
                "ciks_int": self.companies.ciks_int,
                "ciks_str": self.companies.ciks_str,
                "tickers": self.companies.tickers,
                "names": self.companies.names,
            },
            "years": {
                "years": self.years.years,
                "past_years": self.years.past_years,
                "current_years": self.years.current_years,
                "future_years": self.years.future_years,
                "warning": self.years.warning,
            },
            "metrics": {
                "metrics": self.metrics.metrics,
            },
            "sections": {
                "items": self.sections,
                "primary": self.primary_section,
            },
            "risk_topics": self.risk_topics,
        }


class EntityAdapter:
    """
    Top-level NL → {company, year, metric, section, risk_topic} adapter.

    Responsibilities:
      - Hide all the individual extractors behind a single .extract() call.
      - Own the default dimension paths (companies, sections).
      - Return a clean, typed EntityExtractionResult that downstream code
        can consume without knowing about fuzzy matching, alias maps, etc.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        company_dim_path: Optional[Path] = None,
        sections_dim_path: Optional[Path] = None,
        *,
        # Allow dependency injection for advanced/testing use
        company_universe: CompanyUniverse | None = None,
        section_universe: SectionUniverse | None = None,
        company_extractor: CompanyExtractor | None = None,
        year_extractor: YearExtractor | None = None,
        metric_adapter: MetricAdapter | None = None,
        section_extractor: SectionExtractor | None = None,
    ) -> None:
        """
        Create a full-featured entity adapter.

        Args
        ----
        project_root:
            Root path of the finrag_ml_tg1 project. If not given, inferred
            from this file location (two levels up).
        company_dim_path:
            Path to finrag_dim_companies_*.parquet. If None, defaults to
            `<project_root>/data_cache/dimensions/finrag_dim_companies_21.parquet`.
        sections_dim_path:
            Path to finrag_dim_sec_sections.parquet. If None, defaults to
            `<project_root>/data_cache/dimensions/finrag_dim_sec_sections.parquet`.
        """

        self.company_table_name = "finrag_dim_companies_21.parquet"
        self.sections_table_name = "finrag_dim_sec_sections.parquet"    

        # ----------------------------
        # 1) Resolve paths / universes
        # ----------------------------
        if project_root is None:
            # .../finrag_ml_tg1/rag_modules_src/entity_adapter/entity_adapter.py
            # parents[0] = entity_adapter
            # parents[1] = entity_adapter/
            # parents[2] = rag_modules_src/
            # parents[3] = finrag_ml_tg1/
            project_root = Path(__file__).resolve().parents[2]

        self.project_root = project_root

        if company_dim_path is None:
            company_dim_path = (
                project_root / "data_cache" / "dimensions" / self.company_table_name
            )
        if sections_dim_path is None:
            sections_dim_path = (
                project_root / "data_cache" / "dimensions" / self.sections_table_name
            )

        # Company universe / extractor
        if company_universe is None:
            company_universe = CompanyUniverse(dim_path=company_dim_path)
        if company_extractor is None:
            company_extractor = CompanyExtractor(company_universe)

        # Section universe / extractor
        if section_universe is None:
            section_universe = SectionUniverse(dim_path=sections_dim_path)
        if section_extractor is None:
            section_extractor = SectionExtractor(section_universe)

        # Year + metric adapters
        if year_extractor is None:
            year_extractor = YearExtractor()
        if metric_adapter is None:
            metric_adapter = MetricAdapter()

        self.company_universe = company_universe
        self.section_universe = section_universe

        self.company_extractor = company_extractor
        self.year_extractor = year_extractor
        self.metric_adapter = metric_adapter
        self.section_extractor = section_extractor


        logger.info("EntityAdapter initialized successfully")

    # -------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------
    def extract(self, query: str) -> EntityExtractionResult:
        """
        Run the full NL → entity extraction stack for a single user query.

        This is the primary call that the RAG orchestrator / metric pipeline
        should use.

        Steps:
          1) Companies (CIKs, tickers, names)
          2) Years (past/current/future + warning)
          3) Metrics (canonical metric IDs via v2 mappings)
          4) Sections (sec_item_canonical like 'ITEM_7', 'ITEM_1A', ...)
          5) Risk topics (liquidity_credit, regulatory, etc.)
        """

        logger.info("EntityAdapter.extract: starting for query=%r", query)

        companies: CompanyMatches = self.company_extractor.extract(query)
        years: YearMatches = self.year_extractor.extract(query)
        metrics: MetricMatches = self.metric_adapter.extract(query)

        section_matches = self.section_extractor.extract_sections(query)
        risk_matches = self.section_extractor.extract_risk_topics(query)

        sections: List[str]
        primary_section: Optional[str]
        risk_topics: List[str]

        if section_matches is None:
            sections = []
            primary_section = None
        else:
            # normalize to a plain list[str] for the result
            sections = list(section_matches.items)
            primary_section = section_matches.primary

        if risk_matches is None:
            risk_topics = []
        else:
            risk_topics = list(risk_matches.topics)

        result = EntityExtractionResult(
            query=query,
            companies=companies,
            years=years,
            metrics=metrics,
            sections=sections,
            primary_section=primary_section,
            risk_topics=risk_topics,
        )

        logger.info(
            "EntityAdapter.extract: done. companies=%d, years=%d, metrics=%d, "
            "sections=%d, risk_topics=%d",
            len(companies.ciks_int),
            len(years.years),
            len(metrics.metrics),
            len(sections),
            len(risk_topics),
        )

        return result

    # -------------------------------------------------------------
    # Convenience for notebooks / dev mode
    # -------------------------------------------------------------
    @staticmethod
    def debug_print(result: EntityExtractionResult) -> None:
        """
        Pretty-print an EntityExtractionResult in the style
        you've been using in notebooks.
        """
        print("Query:", result.query)
        print("  CIKs int:     ", result.companies.ciks_int)
        print("  CIKs str:     ", result.companies.ciks_str)
        print("  Tickers:      ", result.companies.tickers)
        print("  Names:        ", result.companies.names)
        print("  Years:        ", result.years.years)
        print("  Metrics:      ", result.metrics.metrics)
        print("  Sections:     ", result.sections)
        print("  Primary sec:  ", result.primary_section)
        print("  Risk topics:  ", result.risk_topics)
        print("  Year warning: ", result.years.warning)
        print()



"""
Usage Example: Once more. From testfile.

from pathlib import Path
from rag_modules_src.entity_adapter.entity_adapter import EntityAdapter

adapter = EntityAdapter()
print("project_root:", adapter.project_root)
print("company_dim:", adapter.company_universe.dim_path)
print("sections_dim:", adapter.section_universe.dim_path)

queries = [
    "What was Nvidia's, Apple's and Amazon's revenue and net income in 2021, 2022, and 2023?",
    "Between Nvidia's gaming business, Apple's services, Teslsa, and MSFT, "
    "compare revenue, net income, operating cash flow, total assets and gross "
    "profit margin for 2019, 2020, 2023 and 2026.",
    
    "In Item 1A and Item 7, what liquidity and market risks did Tesla highlight in 2020?",
]

for q in queries:
    res = adapter.extract(q)
    EntityAdapter.debug_print(res)
"""