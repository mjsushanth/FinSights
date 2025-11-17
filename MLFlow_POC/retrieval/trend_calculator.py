"""
Trend calculation and analysis for KPI data.
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from data.loaders import data_loader


@dataclass
class TrendResult:
    """Container for trend analysis results"""
    ticker: str
    metric: str
    start_year: int
    end_year: int
    start_value: float
    end_value: float
    absolute_change: float
    percent_change: float
    cagr: Optional[float] = None
    trend_direction: str = ""
    
    def __post_init__(self):
        """Calculate derived fields"""
        if self.percent_change > 5:
            self.trend_direction = "Strong Growth"
        elif self.percent_change > 0:
            self.trend_direction = "Moderate Growth"
        elif self.percent_change > -5:
            self.trend_direction = "Slight Decline"
        else:
            self.trend_direction = "Significant Decline"
    
    def format_response(self) -> str:
        """Format trend data as readable string"""
        lines = [
            f"{self.metric} Trend for {self.ticker} ({self.start_year}-{self.end_year}):",
            f"  Start: ${self.start_value:,.0f}",
            f"  End: ${self.end_value:,.0f}",
            f"  Change: ${self.absolute_change:,.0f} ({self.percent_change:+.2f}%)",
        ]
        
        if self.cagr is not None:
            lines.append(f"  CAGR: {self.cagr:.2f}%")
        
        lines.append(f"  Direction: {self.trend_direction}")
        
        return "\n".join(lines)


class TrendCalculator:
    """
    Calculate trends and growth rates for financial KPIs.
    """
    
    def __init__(self):
        self.data_context = data_loader.load_all()
    
    def calculate_trend(
        self,
        ticker: str,
        metric: str,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None
    ) -> Optional[TrendResult]:
        """
        Calculate trend for a specific KPI.
        
        Args:
            ticker: Stock ticker
            metric: Metric name
            start_year: Start year (optional, uses earliest available)
            end_year: End year (optional, uses latest available)
            
        Returns:
            TrendResult or None if insufficient data
        """
        df = self.data_context.metrics
        
        # Filter data
        mask = (df.ticker == ticker) & (df.metric == metric)
        metric_df = df[mask].sort_values("year")
        
        if len(metric_df) < 2:
            return None
        
        # Apply year filters
        if start_year:
            metric_df = metric_df[metric_df.year >= start_year]
        if end_year:
            metric_df = metric_df[metric_df.year <= end_year]
        
        if len(metric_df) < 2:
            return None
        
        # Get first and last values
        first_row = metric_df.iloc[0]
        last_row = metric_df.iloc[-1]
        
        start_val = first_row.value
        end_val = last_row.value
        
        # Calculate metrics
        absolute_change = end_val - start_val
        percent_change = (absolute_change / start_val) * 100
        
        # Calculate CAGR
        num_years = last_row.year - first_row.year
        if num_years > 0 and start_val > 0:
            cagr = (((end_val / start_val) ** (1 / num_years)) - 1) * 100
        else:
            cagr = None
        
        return TrendResult(
            ticker=ticker,
            metric=metric,
            start_year=int(first_row.year),
            end_year=int(last_row.year),
            start_value=start_val,
            end_value=end_val,
            absolute_change=absolute_change,
            percent_change=percent_change,
            cagr=cagr
        )
    
    def calculate_multiple_trends(
        self,
        ticker: str,
        metrics: List[str],
        start_year: Optional[int] = None,
        end_year: Optional[int] = None
    ) -> List[TrendResult]:
        """
        Calculate trends for multiple metrics.
        
        Args:
            ticker: Stock ticker
            metrics: List of metric names
            start_year: Optional start year
            end_year: Optional end year
            
        Returns:
            List of TrendResult objects
        """
        results = []
        
        for metric in metrics:
            trend = self.calculate_trend(ticker, metric, start_year, end_year)
            if trend:
                results.append(trend)
        
        return results
    
    def get_year_over_year_growth(
        self,
        ticker: str,
        metric: str
    ) -> List[Dict[str, Any]]:
        """
        Calculate year-over-year growth rates.
        
        Args:
            ticker: Stock ticker
            metric: Metric name
            
        Returns:
            List of dicts with year and yoy_growth
        """
        df = self.data_context.metrics
        
        mask = (df.ticker == ticker) & (df.metric == metric)
        metric_df = df[mask].sort_values("year").reset_index(drop=True)
        
        if len(metric_df) < 2:
            return []
        
        yoy_data = []
        for i in range(1, len(metric_df)):
            prev_val = metric_df.iloc[i-1].value
            curr_val = metric_df.iloc[i].value
            
            if prev_val > 0:
                yoy_growth = ((curr_val - prev_val) / prev_val) * 100
                yoy_data.append({
                    "year": int(metric_df.iloc[i].year),
                    "value": curr_val,
                    "yoy_growth": round(yoy_growth, 2)
                })
        
        return yoy_data
    
    def format_as_context(self, trends: List[TrendResult]) -> List[str]:
        """
        Format trend results for inclusion in LLM context.
        
        Args:
            trends: List of TrendResult objects
            
        Returns:
            List of formatted strings
        """
        return [trend.format_response() for trend in trends]


# Global calculator instance
trend_calculator = TrendCalculator()