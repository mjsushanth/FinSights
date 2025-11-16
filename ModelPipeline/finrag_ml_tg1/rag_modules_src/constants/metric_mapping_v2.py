"""
FinRAG-Insights: metric + section + risk keyword configuration

Grounded on:
- analysis_keywords_kpi_by_label.json
- analysis_keywords_kpi_tokens.json
- analysis_keywords_risk_by_topic.json
- analysis_keywords_risk_tokens.json
- analysis_keywords_section_by_section.json
- analysis_keywords_section_global.json
"""

# ---------------------------------------------------------------------
# 1) Natural language -> canonical metric name
# ---------------------------------------------------------------------

"""
tightly focused on semantic aliases - 
    all the ways humans talk about revenue, net income, operating income, COGS, tax, cash flow, EPS etc 
    -  normalized into canonical metric IDs like income_stmt_Revenue, cash_flow_Operating Cash Flow, 
    Return on Assets (ROA) %, EPS, etc.
"""
METRIC_MAPPINGS = {
    # Revenue / sales
    'revenue': 'income_stmt_Revenue',
    'revenues': 'income_stmt_Revenue',
    'total revenue': 'income_stmt_Revenue',
    'total revenues': 'income_stmt_Revenue',
    'sales': 'income_stmt_Revenue',
    'total sales': 'income_stmt_Revenue',
    'net sales': 'income_stmt_Revenue',
    'net revenue': 'income_stmt_Revenue',
    'net revenues': 'income_stmt_Revenue',
    'sales revenue': 'income_stmt_Revenue',
    'product revenue': 'income_stmt_Revenue',
    'service revenue': 'income_stmt_Revenue',
    'top line': 'income_stmt_Revenue',

    # Income / profit
    'net income': 'income_stmt_Net Income',
    'net earnings': 'income_stmt_Net Income',
    'earnings': 'income_stmt_Net Income',
    'profit': 'income_stmt_Net Income',
    'net profit': 'income_stmt_Net Income',
    'bottom line': 'income_stmt_Net Income',
    'income': 'income_stmt_Net Income',
    'income attributable': 'income_stmt_Net Income',
    'earnings attributable': 'income_stmt_Net Income',
    'income from continuing operations': 'income_stmt_Net Income',
    'earnings from continuing operations': 'income_stmt_Net Income',
    # treat "net loss" as the same metric with negative sign
    'net loss': 'income_stmt_Net Income',

    # Operating income
    'operating income': 'income_stmt_Operating Income',
    'income from operations': 'income_stmt_Operating Income',
    'income from operation': 'income_stmt_Operating Income',
    'operating profit': 'income_stmt_Operating Income',
    'operating loss': 'income_stmt_Operating Income',
    'operating margin': 'income_stmt_Operating Income',
    'results of operations': 'income_stmt_Operating Income',

    # Assets
    'total assets': 'balance_sheet_Total Assets',
    'assets': 'balance_sheet_Total Assets',
    'current assets': 'balance_sheet_Current Assets',

    # Liabilities / debt
    'total liabilities': 'balance_sheet_Total Liabilities',
    'liabilities': 'balance_sheet_Total Liabilities',
    'current liabilities': 'balance_sheet_Current Liabilities',
    'long term debt': 'balance_sheet_Total Liabilities',
    'short term borrowings': 'balance_sheet_Total Liabilities',
    'total debt': 'balance_sheet_Total Liabilities',

    # Equity
    'stockholders equity': 'balance_sheet_Stockholders Equity',
    'shareholders equity': 'balance_sheet_Stockholders Equity',
    'stockholder equity': 'balance_sheet_Stockholders Equity',
    'shareholder equity': 'balance_sheet_Stockholders Equity',
    'total equity': 'balance_sheet_Stockholders Equity',
    'equity': 'balance_sheet_Stockholders Equity',

    # Cash flow (operating / investing / financing)
    'operating cash flow': 'cash_flow_Operating Cash Flow',
    'cash flow from operations': 'cash_flow_Operating Cash Flow',
    'cash flows from operating activities': 'cash_flow_Operating Cash Flow',
    'cash provided by operating activities': 'cash_flow_Operating Cash Flow',
    'cash generated from operations': 'cash_flow_Operating Cash Flow',
    'net cash provided by operating activities': 'cash_flow_Operating Cash Flow',
    'cash from operations': 'cash_flow_Operating Cash Flow',
    'operating activities cash flows': 'cash_flow_Operating Cash Flow',
    'cashflow': 'cash_flow_Operating Cash Flow',
    'cash flow': 'cash_flow_Operating Cash Flow',

    'investing cash flow': 'cash_flow_Investing Cash Flow',
    'cash flow from investing activities': 'cash_flow_Investing Cash Flow',
    'cash used in investing activities': 'cash_flow_Investing Cash Flow',

    'financing cash flow': 'cash_flow_Financing Cash Flow',
    'cash flow from financing activities': 'cash_flow_Financing Cash Flow',
    'cash used in financing activities': 'cash_flow_Financing Cash Flow',

    # Other income-statement metrics
    'gross profit': 'income_stmt_Gross Profit',
    'gross income': 'income_stmt_Gross Profit',

    'operating expenses': 'income_stmt_Operating Expenses',
    'operating expense': 'income_stmt_Operating Expenses',
    'selling general and administrative': 'income_stmt_Operating Expenses',
    'sga': 'income_stmt_Operating Expenses',
    'sgna': 'income_stmt_Operating Expenses',
    'sg&a': 'income_stmt_Operating Expenses',

    'cost of revenue': 'income_stmt_Cost of Revenue',
    'cost of revenues': 'income_stmt_Cost of Revenue',
    'cost of sales': 'income_stmt_Cost of Revenue',
    'cogs': 'income_stmt_Cost of Revenue',

    'interest expense': 'income_stmt_Interest Expense',
    'interest expenses': 'income_stmt_Interest Expense',
    'net interest expense': 'income_stmt_Interest Expense',

    'provision for income tax': 'income_stmt_Provision for Income Tax',
    'income tax expense': 'income_stmt_Provision for Income Tax',
    'tax expense': 'income_stmt_Provision for Income Tax',
    'taxes': 'income_stmt_Provision for Income Tax',
    'income tax': 'income_stmt_Provision for Income Tax',
    'tax': 'income_stmt_Provision for Income Tax',

    # EPS / per-share metrics (canonical label left as generic "EPS" for now)
    'earnings per share': 'EPS',
    'earnings per diluted share': 'EPS',
    'earnings per basic share': 'EPS',
    'eps': 'EPS',
    'basic eps': 'EPS',
    'diluted eps': 'EPS',

    # Ratios (same naming style you already used)
    'return on assets': 'Return on Assets (ROA) %',
    'roa': 'Return on Assets (ROA) %',
    'gross profit margin': 'Gross Profit Margin %',
    'gross margin': 'Gross Profit Margin %',
}

# ---------------------------------------------------------------------
# 2) Base metric keywords (for quick pre-filtering)
# ---------------------------------------------------------------------

METRIC_KEYWORDS = [
    'assets', 'bottom line', 'capex', 'capital expenditure', 'capital expenditures', 'cash flow', 
    'cash flows', 'cashflow', 'cost', 'tax', 'debt', 'earnings', 'earnings per share', 'ebit', 'ebitda', 'eps', 'equity',
    'expenses', 'free cash flow', 'gross margin', 'gross profit', 'income', 'income tax', 'interest expense', 
    'leverage', 'liabilities', 'loss', 'market cap', 'operating', 'investing', 'financing', 'margin', 
    'market capitalization', 'net income', 'operating cash flow', 'operating income', 'operating margin', 
    'operating profit', 'profit', 'revenue', 'revenues', 'sales', 'top line', 'topline',
]

# ---------------------------------------------------------------------
# 3) Quantitative “question shape” indicators in user queries
# ---------------------------------------------------------------------

QUANTITATIVE_INDICATORS = [
    'amount', 'by how much', 'change in', 'decrease in', 'how big', 'how large', 'how many', 'how much', 'increase in',
    'number', 'percent of', 'percentage of', 'total', 'value', 'volume', 'what amount', 'what are', 'what figure', 
    'what is', 'what percent', 'what percentage', 'what was', 'what were',
]






# ---------------------------------------------------------------------
# 4) Section keywords: NL phrases -> sec_item_canonical (ITEM_x / ITEM_xA)
#    This is designed to drive S3 Vectors filters on `sec_item_canonical`
# ---------------------------------------------------------------------

SECTION_KEYWORDS = {
    # Core business (Item 1)
    "business description": "ITEM_1",
    "business overview": "ITEM_1",
    "company overview": "ITEM_1",
    "products and services": "ITEM_1",
    "market segments": "ITEM_1",
    "business strategy": "ITEM_1",

    # Risk factors (Item 1A)
    "risk factors": "ITEM_1A",
    "key risks": "ITEM_1A",
    "risk factor section": "ITEM_1A",
    "forward looking statements": "ITEM_1A",
    "forward-looking statements": "ITEM_1A",
    "uncertainties": "ITEM_1A",

    # Properties (Item 2)
    "properties": "ITEM_2",
    "facilities": "ITEM_2",
    "real estate": "ITEM_2",

    # Legal proceedings (Item 3)
    "legal proceedings": "ITEM_3",
    "litigation": "ITEM_3",
    "legal matters": "ITEM_3",

    # Mine safety (Item 4)
    "mine safety": "ITEM_4",
    "mine safety disclosures": "ITEM_4",

    # Market / trading info (Item 5)
    "market for registrant common equity": "ITEM_5",
    "stock market data": "ITEM_5",
    "share repurchases": "ITEM_5",
    "dividends": "ITEM_5",
    "stock performance": "ITEM_5",

    # Selected financial data (Item 6)
    "selected financial data": "ITEM_6",
    "multi-year financial summary": "ITEM_6",

    # MD&A core (Item 7)
    "md&a": "ITEM_7",
    "mda": "ITEM_7",
    "mdna": "ITEM_7",
    "management discussion and analysis": "ITEM_7",
    "management's discussion and analysis": "ITEM_7",
    "results of operations": "ITEM_7",
    "operating results": "ITEM_7",
    "liquidity and capital resources": "ITEM_7",
    "capital resources": "ITEM_7",
    "liquidity": "ITEM_7",
    "outlook": "ITEM_7",

    # Market risk (Item 7A)
    "market risk": "ITEM_7A",
    "quantitative and qualitative disclosures about market risk": "ITEM_7A",
    "interest rate risk": "ITEM_7A",
    "foreign currency risk": "ITEM_7A",
    "fx risk": "ITEM_7A",
    "commodity price risk": "ITEM_7A",

    # Financial statements (Item 8)
    "financial statements": "ITEM_8",
    "audited financial statements": "ITEM_8",
    "balance sheet": "ITEM_8",
    "income statement": "ITEM_8",
    "statement of operations": "ITEM_8",
    "statement of cash flows": "ITEM_8",
    "cash flow statement": "ITEM_8",
    "supplementary data": "ITEM_8",

    # Changes in accountants (Item 9)
    "changes in and disagreements with accountants": "ITEM_9",
    "changes in accountants": "ITEM_9",

    # Controls & procedures (Item 9A)
    "controls and procedures": "ITEM_9A",
    "internal controls": "ITEM_9A",
    "icfr": "ITEM_9A",
    "sox 404": "ITEM_9A",
    "internal control over financial reporting": "ITEM_9A",

    # Other information (Item 9B)
    "other information": "ITEM_9B",

    # Governance & ownership (Part III)
    "directors and executive officers": "ITEM_10",
    "corporate governance": "ITEM_10",
    "board of directors": "ITEM_10",

    "executive compensation": "ITEM_11",
    "compensation discussion and analysis": "ITEM_11",

    "security ownership": "ITEM_12",
    "beneficial ownership": "ITEM_12",

    "related party transactions": "ITEM_13",
    "related transactions": "ITEM_13",

    "auditor fees": "ITEM_14",
    "principal accountant fees": "ITEM_14",

    # Exhibits / summary (Part IV)
    "exhibits and financial statement schedules": "ITEM_15",
    "exhibit index": "ITEM_15",

    "10-k summary": "ITEM_16",
    "form 10-k summary": "ITEM_16",
}

# ---------------------------------------------------------------------
# 4b) Explicit "Item X" patterns -> sec_item_canonical
#
# This is *in addition* to SECTION_KEYWORDS and will be used by the
# SectionExtractor as regexes on the normalized query string.
# ---------------------------------------------------------------------

SECTION_ITEM_PATTERNS = {
    # Generic "item N" / "itemN" / "item-N" etc.
    r"\bitem\s*[-_ ]?\s*1\b": "ITEM_1",
    r"\bitem\s*[-_ ]?\s*1a\b": "ITEM_1A",
    r"\bitem\s*[-_ ]?\s*2\b": "ITEM_2",
    r"\bitem\s*[-_ ]?\s*3\b": "ITEM_3",
    r"\bitem\s*[-_ ]?\s*4\b": "ITEM_4",
    r"\bitem\s*[-_ ]?\s*5\b": "ITEM_5",
    r"\bitem\s*[-_ ]?\s*6\b": "ITEM_6",
    r"\bitem\s*[-_ ]?\s*7\b": "ITEM_7",
    r"\bitem\s*[-_ ]?\s*7a\b": "ITEM_7A",
    r"\bitem\s*[-_ ]?\s*8\b": "ITEM_8",
    r"\bitem\s*[-_ ]?\s*9\b": "ITEM_9",
    r"\bitem\s*[-_ ]?\s*9a\b": "ITEM_9A",
    r"\bitem\s*[-_ ]?\s*9b\b": "ITEM_9B",
    r"\bitem\s*[-_ ]?\s*10\b": "ITEM_10",
    r"\bitem\s*[-_ ]?\s*11\b": "ITEM_11",
    r"\bitem\s*[-_ ]?\s*12\b": "ITEM_12",
    r"\bitem\s*[-_ ]?\s*13\b": "ITEM_13",
    r"\bitem\s*[-_ ]?\s*14\b": "ITEM_14",
    r"\bitem\s*[-_ ]?\s*15\b": "ITEM_15",
    r"\bitem\s*[-_ ]?\s*16\b": "ITEM_16",

    # Bare numeric references that often appear as "see Item 7A above"
    r"\b7a\b": "ITEM_7A",
    r"\b1a\b": "ITEM_1A",
}




# ---------------------------------------------------------------------
# 5) Risk-topic keywords (natural phrases -> risk_topic buckets)
#    Keys are your topic labels from view2_risk_atlas
# ---------------------------------------------------------------------

RISK_TOPIC_KEYWORDS = {
    'liquidity_credit': [
        'liquidity', 'cash flow', 'cash flows', 'cash position', 'capital resources', 'capital structure', 'refinancing',
        'refinance', 'credit facility', 'credit facilities', 'revolving credit', 'covenant', 'covenants', 'default',
          'debt maturity', 'going concern', 'solvency', ],
    'regulatory': [
        'regulatory', 'regulation', 'regulations', 'regulatory approval', 'regulatory changes', 'laws and regulations',
          'legal and regulatory', 'compliance', 'government investigations', 'regulatory investigations', 'fines',
            'penalties', 'sanctions', 'enforcement actions', ],
    'market_competitive': [
        'competition', 'competitive', 'competitive pressures', 'market share', 'pricing pressure', 'pricing pressures',
          'demand', 'customer demand', 'macroeconomic', 'economic conditions', 'recession', 'downturn',
            'market volatility', 'volatility', ],
    'operational_supply_chain': [
        'operations', 'operational', 'operating disruptions', 'supply chain', 'supply-chain', 'supply disruptions',
          'logistics', 'manufacturing', 'production facilities', 'plant closures', 'outages', 'business interruption',
            'natural disaster', 'catastrophic events', ],
    'cybersecurity_tech': [
        'cybersecurity', 'cyber security', 'cyber', 'information security', 'data security', 'data breach',
          'breach of data', 'security incident', 'security incidents', 'ransomware', 'malware', 'hacking', 'unauthorized access', 'privacy', 'personal data', 'confidential information', ],
    'legal_ip_litigation': [
        'litigation', 'lawsuits', 'class action', 'legal proceedings', 'legal claims', 'claims and proceedings',
          'disputes', 'arbitration', 'settlement', 'judgment', 'patent', 'patent infringement', 'intellectual property',
            'ip rights', ],
    'general_risk': [
        'risk factors', 'risks and uncertainties', 'material adverse effect', 'adverse effect', 'adverse impacts',
          'economic conditions', 'market conditions', 'pandemic', 'covid-19', 'downturn', 'volatility', ],
}
