"""
Extract structured filters (ticker, year, metric) from natural language queries
"""

import re
from typing import Optional, Dict, List
from config.metric_mappings import COMPANY_TO_TICKER, METRIC_MAPPINGS


def simple_fuzzy_match(word: str, choices: list, threshold: float = 0.8) -> tuple:
    """
    Simple fuzzy matching using Levenshtein distance (no external libs needed)
    Returns: (best_match, similarity_score)
    """
    def levenshtein_distance(s1: str, s2: str) -> int:
        """Calculate edit distance between two strings"""
        if len(s1) < len(s2):
            return levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def similarity(s1: str, s2: str) -> float:
        """Calculate similarity ratio (0-1)"""
        distance = levenshtein_distance(s1.lower(), s2.lower())
        max_len = max(len(s1), len(s2))
        return 1 - (distance / max_len) if max_len > 0 else 0
    
    best_match = None
    best_score = 0
    
    for choice in choices:
        score = similarity(word, choice)
        if score > best_score:
            best_score = score
            best_match = choice
    
    if best_score >= threshold:
        return (best_match, best_score * 100)
    return (None, 0)


class FilterExtractor:
    """Extract ticker, year, and metric from user queries"""
    
    def __init__(self):
        self.company_map = COMPANY_TO_TICKER
        self.metric_map = METRIC_MAPPINGS
    
    def extract(self, query: str) -> Dict[str, any]:
        """
        Main extraction method
        
        Args:
            query: User's natural language query
            
        Returns:
            Dictionary with ticker, year, metrics (list), and confidence
        """
        filters = {
            'ticker': self._extract_ticker(query),
            'year': self._extract_year(query),
            'metrics': self._extract_metrics(query),
            'query': query
        }
        
        # Calculate confidence based on how many filters were found
        has_ticker = filters['ticker'] is not None
        has_year = filters['year'] is not None
        has_metrics = len(filters['metrics']) > 0
        
        found_filters = sum([has_ticker, has_year, has_metrics])
        filters['confidence'] = found_filters / 3.0
        
        return filters
    
    def _extract_ticker(self, query: str) -> Optional[str]:
        """
        Extract ticker symbol or map company name to ticker with FUZZY MATCHING
        Handles both uppercase and lowercase tickers
        
        Examples:
            "NVDA revenue" -> "NVDA"
            "nvda revenue" -> "NVDA"  (NEW!)
            "NVIDIA revenue" -> "NVDA"
            "nvida revenue" -> "NVDA" (typo correction!)
        """
        # First, try to find explicit ticker (2-5 letters, case-insensitive)
        ticker_pattern = r'\b([A-Za-z]{2,5})\b'
        
        # Find all potential ticker matches
        for match in re.finditer(ticker_pattern, query):
            potential_ticker = match.group(1).upper()  # Convert to uppercase
            
            # Filter out common words
            common_words = {'IN', 'IT', 'IS', 'AS', 'AT', 'TO', 'OR', 'AND', 'THE', 'WHAT', 'WAS', 'ARE', 'FOR'}
            
            # Check if it looks like a ticker (not a common word)
            if potential_ticker not in common_words:
                # Additional validation: if it's all uppercase in original query, likely a ticker
                # OR if it's 2-4 chars and not a common word, likely a ticker
                if match.group(1).isupper() or (2 <= len(potential_ticker) <= 4):
                    return potential_ticker
        
        # Fallback: Check for company names with FUZZY MATCHING
        query_lower = query.lower()
        
        # First try exact substring matching (fast)
        for company_name, ticker in self.company_map.items():
            if company_name in query_lower:
                return ticker
        
        # If no exact match, try fuzzy matching
        words = query_lower.split()
        
        for word in words:
            # Skip very short words and common words
            if len(word) < 3 or word in ['the', 'and', 'what', 'how', 'was', 'is', 'are']:
                continue
            
            # Use our simple fuzzy matcher
            best_match, score = simple_fuzzy_match(
                word, 
                list(self.company_map.keys()),
                threshold=0.8
            )
            
            if best_match and score >= 80:
                return self.company_map[best_match]
        
        return None
    
    def _extract_year(self, query: str) -> Optional[int]:
        """
        Extract year from query
        
        Examples:
            "revenue in 2024" -> 2024
            "2023 earnings" -> 2023
        """
        year_pattern = r'\b((19|20)\d{2})\b'
        year_match = re.search(year_pattern, query)
        
        if year_match:
            year = int(year_match.group(1))
            # Sanity check: years should be reasonable (1950-2030)
            if 1950 <= year <= 2030:
                return year
        
        return None
    
    def _extract_metrics(self, query: str) -> List[str]:
        """
        Map natural language to exact metric names with AUTOMATIC FUZZY MATCHING
        Handles ANY typo automatically without manual mappings
        
        Examples:
            "what is revenue" -> ["income_stmt_Revenue"]
            "prifit in 2024" -> ["income_stmt_Net Income"] (any typo!)
            "revenu and assts" -> ["income_stmt_Revenue", "balance_sheet_Total Assets"]
        """
        query_lower = query.lower()
        found_metrics = []
        
        # Sort by length to match longer phrases first
        sorted_metrics = sorted(self.metric_map.items(), 
                               key=lambda x: len(x[0]), 
                               reverse=True)
        
        # Track which parts of the query we've already matched
        matched_spans = []
        matched_words = set()  # Track words already matched
        
        # STEP 1: Try exact matching first (fast)
        for keyword, metric_name in sorted_metrics:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            for match in re.finditer(pattern, query_lower):
                span = match.span()
                
                overlaps = any(
                    (span[0] < end and span[1] > start)
                    for start, end in matched_spans
                )
                
                if not overlaps:
                    if metric_name not in found_metrics:
                        found_metrics.append(metric_name)
                        matched_spans.append(span)
                        # Track the words that were matched
                        matched_words.update(keyword.split())
        
        # STEP 2: Fuzzy match on remaining unmatched words
        words = query_lower.split()
        
        for word in words:
            # Skip if already matched, too short, common word, or number
            if word in matched_words:
                continue
            if len(word) < 4:
                continue
            if word in ['the', 'and', 'what', 'how', 'was', 'is', 'are', 'were', 'from', 'with']:
                continue
            if word.isdigit():
                continue
            
            # Try fuzzy matching against all metric keywords
            best_match, score = simple_fuzzy_match(
                word,
                list(self.metric_map.keys()),
                threshold=0.70  # 70% similarity threshold
            )
            
            if best_match and score >= 70:
                metric_name = self.metric_map[best_match]
                if metric_name not in found_metrics:
                    found_metrics.append(metric_name)
                    matched_words.add(word)  # Mark as matched
        
        return found_metrics
    
    def is_valid(self, filters: Dict[str, any]) -> bool:
        """
        Check if extracted filters are sufficient for lookup
        """
        return all([
            filters.get('ticker'),
            filters.get('year'),
            len(filters.get('metrics', [])) > 0
        ])