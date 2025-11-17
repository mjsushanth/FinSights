"""
Vector-based semantic search for narrative content.
"""
import numpy as np
import faiss
import pandas as pd
from typing import List, Optional
from dataclasses import dataclass

from data.loaders import data_loader


@dataclass
class SearchResult:
    """Single semantic search result"""
    text: str
    company: str
    distance: float  # Cosine distance (lower is better)
    year: Optional[int] = None
    section: Optional[str] = None
    metadata: dict = None
    
    def format_with_score(self) -> str:
        """Format result with relevance score"""
        score = 1 - self.distance
        year_info = f" [{self.year}]" if self.year else ""
        section_info = f" ({self.section})" if self.section else ""
        return f"[Relevance: {score:.3f}]{year_info}{section_info} {self.text}"


@dataclass
class SearchResults:
    """Collection of search results"""
    query: str
    results: List[SearchResult]
    company_filter: Optional[str] = None
    year_filter: Optional[int] = None
    section_filter: Optional[str] = None
    
    def format_for_context(self) -> List[str]:
        """Format results for LLM context"""
        if not self.results:
            return ["No relevant passages found."]
        
        formatted = []
        for i, result in enumerate(self.results, 1):
            year_info = f" (Year: {result.year})" if result.year else ""
            section_info = f" [Section: {result.section}]" if result.section else ""
            formatted.append(f"{i}. {result.text}{year_info}{section_info}")
        
        return formatted


class VectorSearchEngine:
    """
    FAISS-based semantic search for financial narratives.
    Updated to handle company names instead of tickers.
    """
    
    # Mapping from ticker symbols to company names
    TICKER_TO_COMPANY = {
        "NVDA": "NVIDIA CORP",
        "AAPL": "APPLE INC",
        "MSFT": "MICROSOFT CORP",
        "GOOGL": "ALPHABET INC",
        "AMZN": "AMAZON COM INC",
        "TSLA": "TESLA INC",
        "META": "META PLATFORMS INC",
    }
    
    # Reverse mapping
    COMPANY_TO_TICKER = {v: k for k, v in TICKER_TO_COMPANY.items()}
    
    def __init__(self):
        self.data_context = data_loader.load_all()
        self.index = self.data_context.faiss_index
        self.embedder = self.data_context.embedder
        self.sentences_df = self.data_context.sentences
        
        # Verify required columns exist
        required_cols = ['primary_sentence']
        missing_cols = [col for col in required_cols if col not in self.sentences_df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns in sentences dataframe: {missing_cols}")
        
        # Check if we have 'company' or 'ticker' column
        self.has_company = 'company' in self.sentences_df.columns
        self.has_ticker = 'ticker' in self.sentences_df.columns
        
        if not self.has_company and not self.has_ticker:
            print("⚠️ Warning: No company or ticker column found in sentences dataframe")
        
        print(f"✅ Vector Search initialized with {len(self.sentences_df)} sentences")
        print(f"   Using column: {'company' if self.has_company else 'ticker' if self.has_ticker else 'none'}")
    
    def _ticker_to_company(self, ticker: Optional[str]) -> Optional[str]:
        """Convert ticker to company name"""
        if not ticker:
            return None
        # Handle numpy array or other non-string types
        if not isinstance(ticker, str):
            try:
                ticker = str(ticker)
            except:
                return None
        return self.TICKER_TO_COMPANY.get(ticker.upper(), ticker)
    
    def _company_to_ticker(self, company: Optional[str]) -> Optional[str]:
        """Convert company name to ticker"""
        if not company:
            return None
        # Handle numpy array or other non-string types
        if not isinstance(company, str):
            try:
                company = str(company)
            except:
                return None
        return self.COMPANY_TO_TICKER.get(company.upper(), company)
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        ticker: Optional[str] = None,
        company: Optional[str] = None,
        year: Optional[int] = None,
        years: Optional[List[int]] = None,
        section: Optional[str] = None,
        distance_threshold: float = 0.7
    ) -> SearchResults:
        """
        Perform semantic search on financial narratives.
        
        Args:
            query: Natural language query
            top_k: Number of results to return
            ticker: Optional ticker filter (e.g., "NVDA") - will be converted to company name
            company: Optional company name filter (e.g., "NVIDIA CORP")
            year: Optional single year filter
            years: Optional list of years to include
            section: Optional section filter (e.g., "ITEM_7", "ITEM_1A")
            distance_threshold: Maximum distance to include (0.0-1.0)
            
        Returns:
            SearchResults object
        """
        # Convert ticker to company name if provided
        if ticker and not company:
            company = self._ticker_to_company(ticker)
        
        # Generate query embedding
        query_embedding = self._embed_query(query)
        
        # Calculate how many candidates to search based on filters
        filter_multiplier = 1
        if company:
            filter_multiplier *= 2
        if year or years:
            filter_multiplier *= 3
        if section:
            filter_multiplier *= 2
        
        search_k = min(top_k * filter_multiplier * 4, len(self.sentences_df))
        
        # Search FAISS index
        distances, indices = self.index.search(
            query_embedding.astype("float32"),
            int(search_k)
        )
        
        # Convert to results with filtering
        results = []
        for idx, distance in zip(indices[0], distances[0]):
            # Skip if distance too high (relevance too low)
            if distance > distance_threshold:
                continue
            
            # Get corresponding sentence
            if idx >= len(self.sentences_df):
                continue
            
            row = self.sentences_df.iloc[idx]
            
            # Get company name from row
            row_company = None
            if self.has_company:
                raw_company = row['company'] if 'company' in row.index else None
                if raw_company is not None and not pd.isna(raw_company):
                    row_company = str(raw_company)
            elif self.has_ticker:
                raw_ticker = row['ticker'] if 'ticker' in row.index else None
                if raw_ticker is not None and not pd.isna(raw_ticker):
                    row_ticker = str(raw_ticker)
                    row_company = self._ticker_to_company(row_ticker)
            
            # Apply company filter if specified
            if company and row_company:
                # Normalize comparison (case-insensitive, handle variations)
                if company.upper() not in row_company.upper() and row_company.upper() not in company.upper():
                    continue
            
            # Apply year filter if specified
            if 'year' in row.index:
                row_year = row.year
                if year and row_year != year:
                    continue
                if years and row_year not in years:
                    continue
            else:
                row_year = None
            
            # Apply section filter if specified
            if section and 'section' in row.index:
                row_section = str(row['section']) if not pd.isna(row['section']) else None
                if row_section != section:
                    continue
            
            # Extract section if available
            row_section = str(row['section']) if 'section' in row.index and not pd.isna(row['section']) else None
            
            # Create result
            result = SearchResult(
                text=row.primary_sentence,
                company=row_company if row_company else "Unknown",
                distance=float(distance),
                year=int(row_year) if row_year and not pd.isna(row_year) else None,
                section=row_section if row_section and not pd.isna(row_section) else None,
                metadata=row.to_dict() if hasattr(row, 'to_dict') else {}
            )
            results.append(result)
            
            # Stop once we have enough results
            if len(results) >= top_k:
                break
        
        return SearchResults(
            query=query,
            results=results,
            company_filter=company,
            year_filter=year,
            section_filter=section
        )
    
    def _embed_query(self, query: str) -> np.ndarray:
        """
        Generate normalized embedding for query.
        
        Args:
            query: Text to embed
            
        Returns:
            Normalized embedding vector
        """
        embedding = self.embedder.encode([query])
        
        # Normalize for cosine similarity
        faiss.normalize_L2(embedding)
        
        return embedding
    
    def search_with_context(
        self,
        query: str,
        top_k: int = 3,
        ticker: Optional[str] = None,
        company: Optional[str] = None,
        year: Optional[int] = None,
        years: Optional[List[int]] = None,
        section: Optional[str] = None
    ) -> List[str]:
        """
        Search and return results formatted for LLM context.
        
        Args:
            query: Search query
            top_k: Number of results
            ticker: Optional ticker filter (converted to company name)
            company: Optional company name filter
            year: Optional year filter
            years: Optional years list filter
            section: Optional section filter
            
        Returns:
            List of formatted result strings
        """
        results = self.search(query, top_k, ticker, company, year, years, section)
        return results.format_for_context()
    
    def search_by_section(
        self,
        query: str,
        section: str,
        top_k: int = 3,
        ticker: Optional[str] = None,
        company: Optional[str] = None
    ) -> SearchResults:
        """
        Search within a specific SEC filing section.
        
        Common sections:
        - ITEM_1: Business
        - ITEM_1A: Risk Factors
        - ITEM_7: MD&A (Management Discussion & Analysis)
        - ITEM_8: Financial Statements
        
        Args:
            query: Search query
            section: Section identifier (e.g., "ITEM_1A")
            top_k: Number of results
            ticker: Optional ticker filter
            company: Optional company name filter
            
        Returns:
            SearchResults object
        """
        return self.search(query, top_k, ticker=ticker, company=company, section=section)
    
    def search_by_year_range(
        self,
        query: str,
        start_year: int,
        end_year: int,
        top_k: int = 5,
        ticker: Optional[str] = None,
        company: Optional[str] = None
    ) -> SearchResults:
        """
        Search within a specific year range.
        
        Args:
            query: Search query
            start_year: Start year (inclusive)
            end_year: End year (inclusive)
            top_k: Number of results
            ticker: Optional ticker filter
            company: Optional company name filter
            
        Returns:
            SearchResults object
        """
        years = list(range(start_year, end_year + 1))
        return self.search(query, top_k, ticker=ticker, company=company, years=years)
    
    def multi_query_search(
        self,
        queries: List[str],
        top_k_per_query: int = 2,
        ticker: Optional[str] = None,
        company: Optional[str] = None,
        year: Optional[int] = None
    ) -> SearchResults:
        """
        Perform multiple related searches and combine results.
        Useful for complex queries that need multiple perspectives.
        
        Args:
            queries: List of related queries
            top_k_per_query: Results per query
            ticker: Optional ticker filter
            company: Optional company name filter
            year: Optional year filter
            
        Returns:
            Combined SearchResults
        """
        all_results = []
        seen_texts = set()
        
        for query in queries:
            results = self.search(query, top_k_per_query, ticker, company, year)
            
            # Deduplicate by text content
            for result in results.results:
                if result.text not in seen_texts:
                    all_results.append(result)
                    seen_texts.add(result.text)
        
        # Sort by relevance (distance)
        all_results.sort(key=lambda r: r.distance)
        
        return SearchResults(
            query=" | ".join(queries),
            results=all_results,
            company_filter=company,
            year_filter=year
        )
    
    def get_available_sections(self) -> List[str]:
        """Get list of available SEC sections in the data"""
        if 'section' not in self.sentences_df.columns:
            return []
        # Use drop_duplicates instead of unique
        sections = self.sentences_df['section'].dropna().drop_duplicates().tolist()
        return sorted(sections)
    
    def get_available_years(self, ticker: Optional[str] = None, company: Optional[str] = None) -> List[int]:
        """Get list of available years in the data"""
        if 'year' not in self.sentences_df.columns:
            return []
        
        df = self.sentences_df
        
        # Filter by company/ticker if specified
        if company:
            if self.has_company:
                df = df[df['company'].astype(str).str.upper().str.contains(company.upper(), na=False)]
        elif ticker:
            company_name = self._ticker_to_company(ticker)
            if company_name and self.has_company:
                df = df[df['company'].astype(str).str.upper().str.contains(company_name.upper(), na=False)]
        
        # Use drop_duplicates instead of unique
        years = df['year'].dropna().drop_duplicates().tolist()
        return sorted([int(y) for y in years])
    
    def get_available_companies(self) -> List[str]:
        """Get list of available companies in the data"""
        if self.has_company:
            # Use drop_duplicates instead of unique to avoid numpy array issues
            companies = self.sentences_df['company'].dropna().drop_duplicates().tolist()
            # Convert to strings and filter out invalid values
            companies = [str(c) for c in companies if c is not None]
            return sorted(set(companies))
        elif self.has_ticker:
            # Use drop_duplicates instead of unique
            tickers = self.sentences_df['ticker'].dropna().drop_duplicates().tolist()
            # Convert each ticker to string first, then to company name
            companies = []
            for t in tickers:
                if t is not None:
                    t_str = str(t) if not isinstance(t, str) else t
                    company = self._ticker_to_company(t_str)
                    if company:
                        companies.append(company)
            return sorted(set(companies))
        return []


# Global search engine instance
vector_search = VectorSearchEngine()