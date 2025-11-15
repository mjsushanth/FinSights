"""
Configuration file for all mappings
"""

# Company name to ticker mapping
COMPANY_TO_TICKER = {
    'nvidia': 'NVDA',
    'microsoft': 'MSFT',
    'apple': 'AAPL',
    'amazon': 'AMZN',
    'google': 'GOOGL',
    'meta': 'META',
    'tesla': 'TSLA',
    # Add more as needed
}

# Natural language to exact metric name mapping (CLEAN - no typos needed!)
METRIC_MAPPINGS = {
    # Revenue
    'revenue': 'income_stmt_Revenue',
    'sales': 'income_stmt_Revenue',
    'total revenue': 'income_stmt_Revenue',
    'total sales': 'income_stmt_Revenue',
    
    # Income/Profit
    'net income': 'income_stmt_Net Income',
    'profit': 'income_stmt_Net Income',
    'earnings': 'income_stmt_Net Income',
    'net profit': 'income_stmt_Net Income',
    'bottom line': 'income_stmt_Net Income',
    'income': 'income_stmt_Net Income',
    
    # Assets
    'total assets': 'balance_sheet_Total Assets',
    'assets': 'balance_sheet_Total Assets',
    'current assets': 'balance_sheet_Current Assets',
    
    # Liabilities
    'total liabilities': 'balance_sheet_Total Liabilities',
    'liabilities': 'balance_sheet_Total Liabilities',
    'current liabilities': 'balance_sheet_Current Liabilities',
    
    # Equity
    'stockholders equity': 'balance_sheet_Stockholders Equity',
    'shareholders equity': 'balance_sheet_Stockholders Equity',
    'equity': 'balance_sheet_Stockholders Equity',
    
    # Cash Flow
    'operating cash flow': 'cash_flow_Operating Cash Flow',
    'cash flow from operations': 'cash_flow_Operating Cash Flow',
    'cashflow': 'cash_flow_Operating Cash Flow',
    'cash flow': 'cash_flow_Operating Cash Flow',
    'investing cash flow': 'cash_flow_Investing Cash Flow',
    'financing cash flow': 'cash_flow_Financing Cash Flow',
    
    # Other Income Statement
    'gross profit': 'income_stmt_Gross Profit',
    'operating expenses': 'income_stmt_Operating Expenses',
    'cost of revenue': 'income_stmt_Cost of Revenue',
    'cogs': 'income_stmt_Cost of Revenue',
    'interest expense': 'income_stmt_Interest Expense',
    'provision for income tax': 'income_stmt_Provision for Income Tax',
    'tax': 'income_stmt_Provision for Income Tax',
    
    # Ratios
    'return on assets': 'Return on Assets (ROA) %',
    'roa': 'Return on Assets (ROA) %',
    'gross profit margin': 'Gross Profit Margin %',
    'gross margin': 'Gross Profit Margin %',
}

# Base keywords (no typos needed - fuzzy matching handles it!)
METRIC_KEYWORDS = [
    'revenue', 'income', 'profit', 'loss', 'earnings',
    'assets', 'liabilities', 'equity', 'debt',
    'cash flow', 'cashflow', 'operating', 'investing', 'financing',
    'margin', 'expenses', 'cost', 'tax', 'sales'
]

# Keywords that indicate quantitative query
QUANTITATIVE_INDICATORS = [
    'how much', 'how many', 'what is', 'what was',
    'what were', 'total', 'amount', 'value', 'number'
]