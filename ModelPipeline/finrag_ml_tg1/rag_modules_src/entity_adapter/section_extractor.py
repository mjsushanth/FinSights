# ModelPipeline\finrag_ml_tg1\rag_modules_src\entity_adapter\section_extractor.py
from __future__ import annotations

import logging
import re
from typing import List, Set, Tuple

from finrag_ml_tg1.rag_modules_src.constants.metric_mapping_v2 import (
    SECTION_KEYWORDS,
    SECTION_ITEM_PATTERNS,
    RISK_TOPIC_KEYWORDS,
)

## SectionUniverse and SectionMatches via relative imports (.) because they’re in the same entity_adapter package.
from .section_universe import SectionUniverse
from .models import SectionMatches, RiskMatches

logger = logging.getLogger(__name__)



class SectionExtractor:
    """
    Extract SEC section hints from a natural-language query.

    Output is expressed purely in `sec_item_canonical` codes such as
    "ITEM_7", "ITEM_1A", which can be used directly as filters for
    S3 Vectors on the `sec_item_canonical` metadata field.

    The extractor is intentionally conservative:
    - Uses explicit NL cues (SECTION_KEYWORDS)
    - Uses "Item X" patterns (SECTION_ITEM_PATTERNS)
    - Optionally uses risk-topic cues to suggest ITEM_1A
    - Applies a simple priority rule to choose a primary section
    """

    # Simple priority ranking among sections when multiple are found.
    # Lower index == higher priority.
    _DEFAULT_PRIORITY_ORDER = [
        "ITEM_7",   # MD&A
        "ITEM_8",   # Financial statements
        "ITEM_1A",  # Risk factors
        "ITEM_1",   # Business
        "ITEM_7A",  # Market risk
    ]

    def __init__(self, section_universe: SectionUniverse) -> None:
        self.section_universe = section_universe

        # Pre-normalize keyword mappings to lowercased keys
        self._keyword_map = {
            key.lower(): value
            for key, value in SECTION_KEYWORDS.items()
        }

        # Compile regex patterns once
        self._item_pattern_map: List[Tuple[re.Pattern, str]] = [
            (re.compile(pattern, flags=re.IGNORECASE), canonical)
            for pattern, canonical in SECTION_ITEM_PATTERNS.items()
        ]

        # Pre-normalize risk-topic keywords
        self._risk_keywords_by_topic = {
            topic: [kw.lower() for kw in kws]
            for topic, kws in RISK_TOPIC_KEYWORDS.items()
        }

        logger.info(
            "SectionExtractor initialized with %d keyword rules, %d item patterns, %d risk topics",
            len(self._keyword_map),
            len(self._item_pattern_map),
            len(self._risk_keywords_by_topic),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract_sections(self, query: str) -> SectionMatches:
        """
        Extract section hints from the query and return SectionMatches.

        This *does not* enforce any business logic about whether to
        actually filter by section; it simply exposes what looks most
        plausible given the text.
        """
        q_norm = query.lower()

        candidates: Set[str] = set()
        candidates.update(self._from_keywords(q_norm))
        candidates.update(self._from_item_patterns(q_norm))

        # Risk-topic presence -> consider ITEM_1A as a hint
        risk_matches = self.extract_risk_topics(query)
        if risk_matches.has_any:
            candidates.add("ITEM_1A")

        # Keep only valid sections from the universe
        items = self.section_universe.filter_existing(candidates)

        primary = self._pick_primary(items)

        logger.debug(
            "SectionExtractor.extract_sections: query=%r -> items=%s, primary=%s",
            query,
            items,
            primary,
        )

        return SectionMatches(items=items, primary=primary)

    def extract_risk_topics(self, query: str) -> RiskMatches:
        """
        Lightweight risk-topic extractor using RISK_TOPIC_KEYWORDS.

        This does not depend on section; it simply reports which topic
        buckets appear to be present in the NL query.
        """
        q_norm = query.lower()
        topics: List[str] = []

        for topic, keywords in self._risk_keywords_by_topic.items():
            if any(kw in q_norm for kw in keywords):
                topics.append(topic)

        # Deduplicate while preserving order
        seen = set()
        ordered_topics = []
        for t in topics:
            if t not in seen:
                seen.add(t)
                ordered_topics.append(t)

        logger.debug(
            "SectionExtractor.extract_risk_topics: query=%r -> topics=%s",
            query,
            ordered_topics,
        )

        return RiskMatches(topics=ordered_topics)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _from_keywords(self, q_norm: str) -> Set[str]:
        """
        Match SECTION_KEYWORDS by substring search on the normalized query.
        """
        found: Set[str] = set()
        for phrase, canonical in self._keyword_map.items():
            if phrase in q_norm:
                found.add(canonical)
        return found

    def _from_item_patterns(self, q_norm: str) -> Set[str]:
        """
        Match SECTION_ITEM_PATTERNS via regex for patterns such as:

        - "item 7", "item-7", "item_7", "item7"
        - "item 7a", "item-7a"
        - bare "7a", "1a" in some contexts
        """
        found: Set[str] = set()
        for pattern, canonical in self._item_pattern_map:
            if pattern.search(q_norm):
                found.add(canonical)
        return found

    def _pick_primary(self, items: List[str]) -> str | None:
        """
        Choose a single primary section from the list of candidates
        based on a simple priority ordering.

        If nothing matches the explicit priority list, default to the
        first item in the list (if any).
        """
        if not items:
            return None

        # Priority list first
        for sec in self._DEFAULT_PRIORITY_ORDER:
            if sec in items:
                return sec

        # Otherwise, just pick the first (already filtered & ordered by universe)
        return items[0]
