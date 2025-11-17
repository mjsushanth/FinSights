# ModelPipeline\finrag_ml_tg1\rag_modules_src\entity_adapter\year_extractor.py

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Set

from .models import YearMatches


class YearExtractor:
    """
    Extract one or more years from a natural-language query, including ranges.

    Features
    --------
    - Recognizes standalone years like "2019", "2020".
    - Recognizes ranges like:
        "2015 to 2020"
        "2015 - 2020"
        "2015-2020"
        "2015–2020" (en dash)
        "2015—2020" (em dash)
      and expands them to [2015, 2016, ..., 2020].
    - Categorizes years into past / current / future relative to the
      current calendar year.
    - Leaves the decision about actually *using* future years to the caller,
      but provides a clear warning string if any are present.
    """

    # Simple 4-digit year pattern
    YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

    # Range pattern: start-year (19xx/20xx), separator (to / hyphen / en dash / em dash), end-year
    RANGE_RE = re.compile(
        r"\b((19|20)\d{2})\s*(?:to|-|–|—)\s*((19|20)\d{2})\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        min_year: int = 1950,
        max_year: Optional[int] = None,
    ) -> None:
        """
        Parameters
        ----------
        min_year:
            Lower bound for acceptable years (inclusive).
        max_year:
            Upper bound for acceptable years (inclusive). If None, defaults
            to current_year + 5 to allow a small buffer for "future" mentions.
        """
        self.min_year = min_year
        current_year = datetime.now().year
        self.current_year = current_year
        self.max_year = max_year if max_year is not None else current_year + 5

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def extract(self, query: str) -> YearMatches:
        """
        Extract all years mentioned in the query, expanding ranges.

        Returns
        -------
        YearMatches
            years: all distinct valid years (sorted ascending)
            past_years:    years < current_year
            current_years: [current_year] if present
            future_years:  years > current_year
            warning: optional textual description for future (and optional current) years
        """
        if not query:
            return YearMatches(
                years=[],
                past_years=[],
                current_years=[],
                future_years=[],
                warning=None,
            )

        # Normalize dash variants for easier scanning
        normalized = self._normalize_dashes(query)

        # 1) Expand explicit ranges like "2015-2020"
        range_years = self._extract_range_years(normalized)

        # 2) Extract all standalone year tokens
        standalone_years = self._extract_standalone_years(normalized)

        # Union of all years
        all_years_set: Set[int] = range_years.union(standalone_years)
        years_sorted: List[int] = sorted(all_years_set)

        # Categorize vs current year
        past_years: List[int] = [y for y in years_sorted if y < self.current_year]
        current_years: List[int] = [y for y in years_sorted if y == self.current_year]
        future_years: List[int] = [y for y in years_sorted if y > self.current_year]

        warning = self._build_warning(current_years, future_years)

        return YearMatches(
            years=years_sorted,
            past_years=past_years,
            current_years=current_years,
            future_years=future_years,
            warning=warning,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_dashes(text: str) -> str:
        """
        Normalize various Unicode dash characters to a simple hyphen.
        """
        return (
            text.replace("\u2013", "-")  # en dash
            .replace("\u2014", "-")      # em dash
            .replace("\u2212", "-")      # minus sign, just in case
        )

    def _extract_range_years(self, text: str) -> Set[int]:
        """
        Find patterns like "2015-2020" or "2015 to 2020" and expand them
        into full year lists.

        Returns
        -------
        Set[int]
            All years that belong to any recognized range.
        """
        years: Set[int] = set()

        for match in self.RANGE_RE.finditer(text):
            start_str, _, end_str, _ = match.groups()
            start = int(start_str)
            end = int(end_str)

            # Ensure order and reasonable bounds
            if start > end:
                start, end = end, start

            if end < self.min_year or start > self.max_year:
                continue

            start_clamped = max(start, self.min_year)
            end_clamped = min(end, self.max_year)

            for y in range(start_clamped, end_clamped + 1):
                years.add(y)

        return years

    def _extract_standalone_years(self, text: str) -> Set[int]:
        """
        Extract individual years (tokens like '2019').

        Note: these may include the endpoints of ranges as well; union with
        range years is harmless because we deduplicate.
        """
        years: Set[int] = set()

        for match in self.YEAR_RE.finditer(text):
            year = int(match.group(0))
            if self.min_year <= year <= self.max_year:
                years.add(year)

        return years

    def _build_warning(
        self,
        current_years: List[int],
        future_years: List[int],
    ) -> Optional[str]:
        """
        Build a human-readable warning string if the query references
        the current or future years.
        """
        parts: List[str] = []

        if future_years:
            parts.append(
                f"Query includes future years {future_years}. "
                "These filings do not exist yet; any results will be empty or synthetic."
            )

        # Optional: keep or drop this according to your preference.
        # I'm keeping it conservative and textual-only, like your current behaviour.
        if current_years:
            parts.append(
                f"Query includes current year {current_years}. "
                "Some filings may not be fully available yet."
            )

        if not parts:
            return None

        return " ".join(parts)
