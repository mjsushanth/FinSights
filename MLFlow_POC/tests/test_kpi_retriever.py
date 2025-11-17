from retrieval.kpi_retrieval import kpi_retriever
from data.loaders import data_loader

print("Testing KPI Retriever...")
print("=" * 70)

# First, load data and show available metrics
print("\n0. Loading Data and Available Metrics:")
data_context = data_loader.load_all()
available_metrics = data_loader.get_available_metrics("NVDA")
print(f"\n✅ Available metrics for NVDA ({len(available_metrics)} total):")
for metric in available_metrics:
    print(f"   • {metric}")

# Test 1: Single KPI - Revenue
print("\n" + "=" * 70)
print("1. Single KPI Query - Revenue:")
result = kpi_retriever.get_kpi("NVDA", "income_stmt_Revenue", 2023)
print(f"   Found: {result.found}")
if result.found:
    print(f"   Data: {result.data}")
    print(f"\n   Formatted:\n{result.format_response()}")
else:
    print("   ❌ No data found")

# Test 2: Single KPI - Net Income
print("\n" + "=" * 70)
print("2. Single KPI Query - Net Income:")
result = kpi_retriever.get_kpi("NVDA", "income_stmt_Net Income", 2023)
print(f"   Found: {result.found}")
if result.found:
    print(f"   Data: {result.data}")
    print(f"\n   Formatted:\n{result.format_response()}")
else:
    print("   ❌ No data found")

# Test 3: Single KPI - Gross Profit Margin
print("\n" + "=" * 70)
print("3. Single KPI Query - Gross Profit Margin:")
result = kpi_retriever.get_kpi("NVDA", "Gross Profit Margin %")
print(f"   Found: {result.found}")
if result.found:
    print(f"   Years available: {[int(d['year']) for d in result.data]}")
    print(f"\n   Formatted:\n{result.format_response()}")
else:
    print("   ❌ No data found")

# Test 4: Multi-Year Query with Range
print("\n" + "=" * 70)
print("4. Multi-Year Query with Range - Revenue (2020-2023):")
result = kpi_retriever.get_kpi("NVDA", "income_stmt_Revenue", year_range=(2020, 2023))
print(f"   Found: {result.found}")
if result.found:
    print(f"   Years: {[int(d['year']) for d in result.data]}")
    print(f"\n   Formatted:\n{result.format_response()}")
else:
    print("   ❌ No data found")

# Test 5: Multiple KPIs - Income Statement
print("\n" + "=" * 70)
print("5. Multiple KPIs - Income Statement Metrics:")
metrics = [
    "income_stmt_Revenue",
    "income_stmt_Gross Profit",
    "income_stmt_Net Income"
]
results = kpi_retriever.get_multiple_kpis("NVDA", metrics, year=2023)
print(f"   Retrieved {len(results)} metrics")
formatted = kpi_retriever.format_as_context(results)
for f in formatted:
    print(f"\n{f}")

# Test 6: Multiple KPIs - Balance Sheet
print("\n" + "=" * 70)
print("6. Multiple KPIs - Balance Sheet Metrics:")
metrics = [
    "balance_sheet_Total Assets",
    "balance_sheet_Total Liabilities",
    "balance_sheet_Stockholders Equity"
]
results = kpi_retriever.get_multiple_kpis("NVDA", metrics, year=2023)
print(f"   Retrieved {len(results)} metrics")
formatted = kpi_retriever.format_as_context(results)
for f in formatted:
    print(f"\n{f}")

# Test 7: Multiple KPIs - Cash Flow
print("\n" + "=" * 70)
print("7. Multiple KPIs - Cash Flow Metrics:")
metrics = [
    "cash_flow_Operating Cash Flow",
    "cash_flow_Investing Cash Flow",
    "cash_flow_Financing Cash Flow"
]
results = kpi_retriever.get_multiple_kpis("NVDA", metrics, year=2023)
print(f"   Retrieved {len(results)} metrics")
formatted = kpi_retriever.format_as_context(results)
for f in formatted:
    print(f"\n{f}")

# Test 8: Return Metrics
print("\n" + "=" * 70)
print("8. Return Metrics - ROA:")
result = kpi_retriever.get_kpi("NVDA", "Return on Assets (ROA) %")
print(f"   Found: {result.found}")
if result.found:
    print(f"   Years available: {[int(d['year']) for d in result.data]}")
    print(f"\n   Formatted:\n{result.format_response()}")
else:
    print("   ❌ No data found")

# Test 9: Latest Value
print("\n" + "=" * 70)
print("9. Get Latest Value - Revenue:")
latest = kpi_retriever.get_latest_value("NVDA", "income_stmt_Revenue")
if latest:
    print(f"   Latest Year: {int(latest['year'])}")
    print(f"   Latest Value: ${latest['value']:,.0f}")
else:
    print("   ❌ No data found")

# Test 10: Search Metrics by Keyword
print("\n" + "=" * 70)
print("10. Search Metrics by Keyword:")
keywords = ["revenue", "income", "cash flow", "assets"]
for keyword in keywords:
    matches = kpi_retriever.search_metrics("NVDA", keyword)
    print(f"\n   Keyword '{keyword}': {len(matches)} matches")
    if matches:
        for match in matches[:3]:  # Show first 3
            print(f"      • {match}")

# Test 11: Non-existent Metric
print("\n" + "=" * 70)
print("11. Non-existent Metric Test:")
result = kpi_retriever.get_kpi("NVDA", "NonExistent Metric", 2023)
print(f"   Found: {result.found}")
print(f"   Response: {result.format_response()}")

# Test 12: Year Out of Range
print("\n" + "=" * 70)
print("12. Year Out of Range Test:")
result = kpi_retriever.get_kpi("NVDA", "income_stmt_Revenue", 1999)
print(f"   Found: {result.found}")
if result.data:
    print(f"   Data: {result.data}")
else:
    print(f"   Response: {result.format_response()}")

print("\n" + "=" * 70)
print("✅ KPI Retriever Test COMPLETED")
print("=" * 70 + "\n")