"""
Query the metrics data using extracted filters
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List


class MetricLookup:
    """Handle querying the metrics dataframe"""
    
    def __init__(self, data_path: str):
        """
        Initialize with path to metrics data
        
        Args:
            data_path: Path to JSON file with metrics data
        """
        self.data_path = Path(data_path)
        self.df = None
        self._load_data()
    
    def _load_data(self):
        """Load and prepare the metrics dataframe"""
        if not self.data_path.exists():
            raise FileNotFoundError(f"Data file not found: {self.data_path}")
        
        self.df = pd.read_json(self.data_path)
        print(f"✓ Loaded {len(self.df)} metric records")
        print(f"✓ Unique tickers: {self.df['ticker'].nunique()}")
        print(f"✓ Year range: {self.df['year'].min()}-{self.df['year'].max()}")
    
    def query(self, ticker: str, year: int, metric: str) -> Optional[Dict[str, any]]:
        """
        Query for a specific metric value
        
        Args:
            ticker: Stock ticker symbol (e.g., "NVDA")
            year: Year (e.g., 2024)
            metric: Exact metric name (e.g., "income_stmt_Revenue")
            
        Returns:
            Dictionary with query results or None if not found
        """
        # Filter dataframe
        result = self.df[
            (self.df['ticker'] == ticker) &
            (self.df['year'] == year) &
            (self.df['metric'] == metric)
        ]
        
        if result.empty:
            return None
        
        value = result.iloc[0]['value']
        
        # Check for NaN values
        if pd.isna(value):
            return {
                'ticker': ticker,
                'year': year,
                'metric': metric,
                'value': None,
                'found': False,
                'reason': 'Value is NaN/missing in dataset'
            }
        
        return {
            'ticker': ticker,
            'year': year,
            'metric': metric,
            'value': value,
            'found': True
        }
    
    def get_available_years(self, ticker: str, metric: str) -> list:
        """Get all years where data is available for a ticker/metric combo"""
        results = self.df[
            (self.df['ticker'] == ticker) &
            (self.df['metric'] == metric) &
            (self.df['value'].notna())
        ]
        return sorted(results['year'].unique().tolist())
    
    def get_available_metrics(self, ticker: str, year: int) -> list:
        """Get all available metrics for a ticker/year combo"""
        results = self.df[
            (self.df['ticker'] == ticker) &
            (self.df['year'] == year) &
            (self.df['value'].notna())
        ]
        return sorted(results['metric'].unique().tolist())
    
    def query_multiple(self, ticker: str, year: int, metrics: List[str]) -> List[Dict[str, any]]:
        """
        Query for multiple metrics at once
        
        Args:
            ticker: Stock ticker symbol (e.g., "NVDA")
            year: Year (e.g., 2024)
            metrics: List of exact metric names
            
        Returns:
            List of dictionaries with query results
        """
        results = []
        
        for metric in metrics:
            result = self.query(ticker, year, metric)
            if result:
                results.append(result)
        
        return results