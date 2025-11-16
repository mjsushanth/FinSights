# rag_modules_src/entity_adapter/metric_adapter.py

from __future__ import annotations

import logging
from typing import List

# Reuse the *existing* metric pipeline logic
from rag_modules_src.metric_pipeline.src.filter_extractor import FilterExtractor

# But point it at your richer v2 mapping constants
from rag_modules_src.constants.metric_mapping_v2 import METRIC_MAPPINGS

from .models import MetricMatches

logger = logging.getLogger(__name__)


class FilterExtractorV2(FilterExtractor):
    """
    Extension of the original FilterExtractor that swaps in the
    v2 metric mappings.

    We do *not* reimplement _extract_metrics; we only override the
    metric_map that that method consults.

    This means:
    - All bugfixes / improvements in the original FilterExtractor
      (tokenization, fuzzy matching, etc.) are inherited automatically.
    - Only the underlying NL->canonical metric dictionary changes,
      coming from metric_mapping_v2.METRIC_MAPPINGS.
    """

    def __init__(self) -> None:
        super().__init__()
        # Original class does: self.metric_map = METRIC_MAPPINGS from config.metric_mappings
        # We overwrite it to use the richer v2 mapping instead.
        self.metric_map = METRIC_MAPPINGS
        logger.info(
            "FilterExtractorV2 initialized with "
            f"{len(self.metric_map)} metric mapping entries from metric_mapping_v2"
        )


class MetricAdapter:
    """
    Simple metric entity adapter for the RAG side.

    Responsibilities
    ----------------
    - Call the v2-enabled FilterExtractor to reuse the other dev's
      metric extraction logic.
    - Return a clean MetricMatches object with just the list of
      canonical metric IDs for a given query.

    This adapter intentionally does *not* touch:
    - the metric data tables
    - MetricLookup
    - MetricPipeline.process()

    Those remain the analytical pipeline's responsibility.
    """

    def __init__(self) -> None:
        self._extractor = FilterExtractorV2()

    def extract(self, query: str) -> MetricMatches:
        """
        Extract canonical metrics from a natural-language query.

        Parameters
        ----------
        query:
            The user's question, e.g.
            "Show me NVDA revenue and net income in 2021 and 2022"

        Returns
        -------
        MetricMatches
            metrics: list of canonical metric names
                     (deduplicated, sorted)
        """
        logger.info(f"MetricAdapter extracting metrics from query: {query!r}")

        filters = self._extractor.extract(query)
        raw_metrics: List[str] = filters.get("metrics", []) or []

        # Deduplicate + sort for stability
        uniq_metrics = sorted(set(raw_metrics))

        logger.info(f"MetricAdapter found metrics: {uniq_metrics}")

        return MetricMatches(metrics=uniq_metrics)
