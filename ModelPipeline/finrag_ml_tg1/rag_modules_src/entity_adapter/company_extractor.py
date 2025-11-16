
from __future__ import annotations

import re
from typing import List, Set
import logging

from .company_universe import CompanyUniverse
from .models import CompanyMatches, CompanyInfo
from .string_utils import simple_fuzzy_match

logger = logging.getLogger(__name__)


class CompanyExtractor:
    """
    Extract companies from a natural-language query using the CompanyUniverse.

    Strategies:

    1. Explicit ticker mentions (e.g., "NVDA", "AAPL").
       - Tokens that look like 1–5 uppercase letters.
       - Only accepted if they exist in the universe's ticker set.

    2. Explicit CIK mentions (e.g., "CIK 0000320193").
       - Sequences of 5–10 digits that match a known CIK (cik_int).

    3. Alias-based name mentions.
       - Normalize the query, tokenize into alphanumeric tokens:
         "Apple's" -> "apple", "NVIDIA's" -> "nvidia".
       - Exact match against alias tokens built from the dim
         (e.g. "apple" -> Apple Inc., "microsoft" -> MICROSOFT CORP).
       - Optional fuzzy match of remaining tokens against alias tokens
         to catch minor typos (e.g. "microsft" -> "microsoft").

    4. Fallback substring matching on normalized full names.
       - For cases like "Meta Platforms" or "Johnson & Johnson"
         appearing in full, if alias matching missed them.

    The final result aggregates all matches and returns distinct lists
    of CIK ints, CIK strings, tickers, and names.
    """

    # Regex for candidate tickers: 1–5 letters, all caps, as a standalone token.
    _TICKER_TOKEN_RE = re.compile(r"\b([A-Z]{1,5})\b")

    # Regex for candidate CIK-like numeric strings: 5–10 digits.
    _CIK_TOKEN_RE = re.compile(r"\b(\d{5,10})\b")

    # Tokenization for alias matching: continuous [a-z0-9]+ segments.
    _ALIAS_TOKEN_RE = re.compile(r"[a-z0-9]+")

    def __init__(self, universe: CompanyUniverse) -> None:
        self.universe = universe

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def extract(self, query: str) -> CompanyMatches:
        """
        Main entry point.

        Parameters
        ----------
        query:
            Natural language text from the user.

        Returns
        -------
        CompanyMatches
            Lists of matched CIK ints, CIK strings, tickers, and company names.
        """
        logger.info(f"Extracting companies from query: {query!r}")

        if not query:
            return CompanyMatches(
                ciks_int=[],
                ciks_str=[],
                tickers=[],
                names=[],
            )

        # Strategy 1: tickers
        ticker_matches = self._extract_by_ticker(query)

        # Strategy 2: CIKs
        cik_matches = self._extract_by_cik(query)

        # Strategy 3 + 4: alias-based and fallback name matching
        name_matches = self._extract_by_name(query)

        # Aggregate
        ciks_int_set: Set[int] = set()
        ciks_str_set: Set[str] = set()
        tickers_set: Set[str] = set()
        names_set: Set[str] = set()

        def _add_info(info: CompanyInfo) -> None:
            ciks_int_set.add(info.cik_int)
            if info.cik_str:
                ciks_str_set.add(info.cik_str)
            if info.ticker:
                tickers_set.add(info.ticker)
            names_set.add(info.name)

        for info in ticker_matches:
            _add_info(info)

        for info in cik_matches:
            _add_info(info)

        for info in name_matches:
            _add_info(info)

        ciks_int_list = sorted(ciks_int_set)
        ciks_str_list = sorted(ciks_str_set)
        tickers_list = sorted(tickers_set)
        names_list = sorted(names_set)

        logger.info(
            "Extraction result: "
            f"ciks_int={ciks_int_list}, "
            f"tickers={tickers_list}, "
            f"names={names_list}"
        )

        return CompanyMatches(
            ciks_int=ciks_int_list,
            ciks_str=ciks_str_list,
            tickers=tickers_list,
            names=names_list,
        )

    # ------------------------------------------------------------------ #
    # Individual strategies
    # ------------------------------------------------------------------ #

    def _extract_by_ticker(self, query: str) -> List[CompanyInfo]:
        """
        Identify tickers by scanning for tokens that look like tickers
        and validating them against the universe.
        """
        candidates = set(self._TICKER_TOKEN_RE.findall(query))
        logger.debug(f"Ticker candidates in query: {candidates}")

        if not candidates:
            return []

        valid_tickers = self.universe.tickers
        matches: List[CompanyInfo] = []

        for token in candidates:
            if token in valid_tickers:
                info = self.universe.get_by_ticker(token)
                if info is not None:
                    logger.debug(f"Ticker match: {token} -> {info.name}")
                    matches.append(info)

        return matches

    def _extract_by_cik(self, query: str) -> List[CompanyInfo]:
        """
        Identify CIKs by scanning for digit sequences and mapping them
        to known CIK integers (cik_int).
        """
        candidates = set(self._CIK_TOKEN_RE.findall(query))
        logger.debug(f"CIK candidates in query: {candidates}")

        if not candidates:
            return []

        ciks_int_set = self.universe.ciks_int
        matches: List[CompanyInfo] = []

        for token in candidates:
            try:
                cik_val = int(token)
            except ValueError:
                continue
            if cik_val in ciks_int_set:
                info = self.universe.get_by_cik_int(cik_val)
                if info is not None:
                    logger.debug(f"CIK match: {token} -> {info.name}")
                    matches.append(info)

        return matches

    def _extract_by_name(self, query: str) -> List[CompanyInfo]:
        """
        Identify company names via alias tokens + conservative fuzzy matching,
        with a fallback on normalized full-name substring matching.

        Handles human patterns like:
        - "Apple and Microsoft"
        - "NVIDIA's liquidity risk"
        - "compare nvda and apple in 2023"
        """
        query_norm = self._normalize_text(query)
        logger.debug(f"Normalized query for name extraction: {query_norm!r}")

        if not query_norm:
            return []

        tokens = self._tokenize_for_alias(query_norm)
        logger.debug(f"Alias tokens in query: {tokens}")

        if not tokens:
            return []

        alias_keys = self.universe.alias_tokens
        logger.debug(f"Available alias tokens in universe: {sorted(alias_keys)}")

        seen_cik_ints: Set[int] = set()
        matches: List[CompanyInfo] = []

        # ---- exact alias matches ------------------------------------- #
        matched_aliases: Set[str] = set()
        for tok in tokens:
            if tok in alias_keys:
                matched_aliases.add(tok)

        logger.debug(f"Matched alias tokens (exact): {matched_aliases}")

        for alias in matched_aliases:
            infos = self.universe.get_by_alias_exact(alias)
            logger.debug(f"Alias {alias!r} -> {[i.name for i in infos]}")
            for info in infos:
                if info.cik_int not in seen_cik_ints:
                    seen_cik_ints.add(info.cik_int)
                    matches.append(info)

        # ---- fuzzy alias matches (for remaining tokens) -------------- #
        unmatched_tokens: List[str] = [
            t for t in tokens if t not in matched_aliases and len(t) >= 4
        ]
        logger.debug(f"Unmatched tokens for fuzzy alias: {unmatched_tokens}")

        if alias_keys and unmatched_tokens:
            alias_list = list(alias_keys)
            for tok in unmatched_tokens:
                best_alias, score = simple_fuzzy_match(
                    tok,
                    alias_list,
                    threshold=0.85,  # 85% similarity
                )
                logger.debug(
                    f"Fuzzy check token={tok!r} -> best_alias={best_alias!r}, score={score:.2f}"
                )
                if best_alias is None:
                    continue

                infos = self.universe.get_by_alias_exact(best_alias)
                logger.debug(f"Fuzzy alias {best_alias!r} -> {[i.name for i in infos]}")
                for info in infos:
                    if info.cik_int not in seen_cik_ints:
                        seen_cik_ints.add(info.cik_int)
                        matches.append(info)

        # ---- fallback: full-name substring matching ------------------ #
        full_name_hits = self.universe.find_by_normalized_substring(query_norm)
        if full_name_hits:
            logger.debug(
                "Full-name substring hits: "
                f"{[info.name for info in full_name_hits]}"
            )
        for info in full_name_hits:
            if info.cik_int not in seen_cik_ints:
                seen_cik_ints.add(info.cik_int)
                matches.append(info)

        return matches

    # ------------------------------------------------------------------ #
    # Text normalization / tokenization
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text for name matching:
        - lowercase
        - strip
        - collapse whitespace

        Note: we *do not* remove apostrophes here; the alias tokenizer
        works on [a-z0-9]+, so "nvidia's" -> tokens ["nvidia", "s"].
        """
        text = text.strip().lower()
        parts = text.split()
        return " ".join(parts)

    def _tokenize_for_alias(self, text: str) -> List[str]:
        """
        Tokenize a normalized string into alphanumeric tokens suitable
        for alias matching.

        Examples:
            "apple's performance" -> ["apple", "s"]
            "NVIDIA CORP" (normalized) -> ["nvidia", "corp"]
        """
        return self._ALIAS_TOKEN_RE.findall(text)
