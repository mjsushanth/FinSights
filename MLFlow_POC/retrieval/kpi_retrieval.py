"""
KPI retrieval from structured data sources.
"""
import pandas as pd
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from data.loaders import data_loader


@dataclass
class KPIResult:
    """Container for KPI query results"""
    ticker: str
    metric: str
    data: List[Dict[str, Any]]
    found: bool
    
    def format_response(self) -> str:
        """Format KPI data as readable string"""
        if not self.found or not self.data:
            return f"No data found for {self.metric} ({self.ticker})"
        
        lines = [f"{self.metric} for {self.ticker}:"]
        for record in self.data:
            year = record.get("year")
            value = record.get("value")
            if value is not None:
                lines.append(f"  {int(year)}: ${value:,.0f}")
        
        return "\n".join(lines)


class KPIRetriever:
    """
    Retrieves structured KPI data from parquet files.
    Supports caching and flexible querying.
    """
    
    def __init__(self):
        self.data_context = data_loader.load_all()
    
    def get_kpi(
        self, 
        ticker: str, 
        metric: str, 
        year: Optional[int] = None,
        year_range: Optional[tuple] = None
    ) -> KPIResult:
        """
        Retrieve KPI data for a specific ticker and metric.
        
        Args:
            ticker: Stock ticker (e.g., "NVDA")
            metric: Metric name (e.g., "Revenue")
            year: Specific year (optional)
            year_range: Tuple of (start_year, end_year) (optional)
            
        Returns:
            KPIResult object
        """
        df = self.data_context.metrics
        
        # Filter by ticker and metric
        mask = (df.ticker == ticker) & (df.metric == metric)
        result_df = df[mask].copy()
        
        # Apply year filters if specified
        if year is not None:
            result_df = result_df[result_df.year == year]
        elif year_range is not None:
            start_year, end_year = year_range
            result_df = result_df[
                (result_df.year >= start_year) & 
                (result_df.year <= end_year)
            ]
        
        # Sort by year
        result_df = result_df.sort_values("year")
        
        # Convert to list of dicts
        data = result_df[["year", "value"]].to_dict("records")
        
        return KPIResult(
            ticker=ticker,
            metric=metric,
            data=data,
            found=len(data) > 0
        )
    
    def get_multiple_kpis(
        self,
        ticker: str,
        metrics: List[str],
        year: Optional[int] = None
    ) -> List[KPIResult]:
        """
        Retrieve multiple KPIs at once.
        
        Args:
            ticker: Stock ticker
            metrics: List of metric names
            year: Optional year filter
            
        Returns:
            List of KPIResult objects
        """
        return [
            self.get_kpi(ticker, metric, year)
            for metric in metrics
        ]
    
    def search_metrics(self, ticker: str, search_term: str) -> List[str]:
        """
        Search for metrics matching a term.
        
        Args:
            ticker: Stock ticker
            search_term: Term to search for
            
        Returns:
            List of matching metric names
        """
        available_metrics = data_loader.get_available_metrics(ticker)
        search_lower = search_term.lower()
        
        return [
            metric for metric in available_metrics
            if search_lower in metric.lower()
        ]
    
    def get_latest_value(self, ticker: str, metric: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent value for a KPI.
        
        Args:
            ticker: Stock ticker
            metric: Metric name
            
        Returns:
            Dict with year and value, or None if not found
        """
        result = self.get_kpi(ticker, metric)
        
        if result.found and result.data:
            return result.data[-1]  # Last item after sorting by year
        
        return None
    
    def format_as_context(self, results: List[KPIResult]) -> List[str]:
        """
        Format KPI results for inclusion in LLM context.
        
        Args:
            results: List of KPIResult objects
            
        Returns:
            List of formatted strings
        """
        formatted = []
        
        for result in results:
            if result.found:
                formatted.append(result.format_response())
        
        return formatted


# Global retriever instance
kpi_retriever = KPIRetriever()