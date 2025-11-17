# ModelPipeline/finrag_ml_tg1/rag_modules_src/utilities/supply_line_formatters.py

"""
Formatting utilities for Supply Line 1 - KPI fact table output.

Used to convert MetricPipeline results into compact, human-readable text
suitable for notebook display or LLM context.
"""

from typing import Dict, Any
from collections import defaultdict


def format_value_compact(value: float) -> str:
    """
    Format financial values compactly using B/M/K suffixes.
    
    Args:
        value: Numeric value (e.g., revenue in dollars)
    
    Returns:
        Compact string like "$394.3B", "$1.5M", "$250K"
    
    Examples:
        >>> format_value_compact(394328000000)
        '$394.3B'
        >>> format_value_compact(1500000)
        '$1.5M'
    """
    if abs(value) >= 1_000_000_000:
        return f"${value/1_000_000_000:.1f}B"
    elif abs(value) >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    elif abs(value) >= 1_000:
        return f"${value/1_000:.0f}K"
    else:
        return f"${value:.0f}"


def format_analytical_compact(raw_result: Dict[str, Any]) -> str:
    """
    Format MetricPipeline result into compact multi-line text.
    
    Converts fact table query results into format like:
        MSFT 2021: Revenue=$168.1B, TotalAssets=$333.8B
        MSFT 2022: Revenue=$198.3B, TotalAssets=$364.8B
        NVDA 2021: Revenue=$26.9B, TotalAssets=$28.8B
    
    Args:
        raw_result: Output from MetricPipeline.process()
                   Expected keys: 'success', 'data', 'filters'
    
    Returns:
        Multi-line string with compact KPI data, or empty string if no data
    """
    # Handle failure cases
    if not raw_result.get('success'):
        return ""
    
    data = raw_result.get('data', [])
    if not data:
        return ""
    
    # Group by ticker → year → metrics
    grouped = defaultdict(lambda: defaultdict(dict))
    
    for item in data:
        if item.get('found'):
            ticker = item['ticker']
            year = item['year']
            metric = item['metric']
            value = item['value']
            
            # Shorten metric names for readability
            metric_short = (
                metric.replace('income_stmt_', '')
                      .replace('balance_sheet_', '')
                      .replace('cash_flow_', '')
                      .replace('_', '')
            )
            grouped[ticker][year][metric_short] = value
    
    # Build output lines
    lines = []
    for ticker in sorted(grouped.keys()):
        for year in sorted(grouped[ticker].keys()):
            metrics = grouped[ticker][year]
            metrics_str = ', '.join([
                f"{k}={format_value_compact(v)}" 
                for k, v in metrics.items()
            ])
            lines.append(f"{ticker} {year}: {metrics_str}")
    
    return '\n'.join(lines)