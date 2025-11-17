from retrieval.trend_calculator import trend_calculator

print("Testing Trend Calculator...")
print("=" * 70)

# Test 1: Revenue Trend
print("\n1. Revenue Trend Analysis:")
print("-" * 70)
trend = trend_calculator.calculate_trend("NVDA", "income_stmt_Revenue")
if trend:
    print(trend.format_response())
else:
    print("   ❌ No trend data available")

# Test 2: Net Income Trend
print("\n" + "=" * 70)
print("2. Net Income Trend Analysis:")
print("-" * 70)
trend = trend_calculator.calculate_trend("NVDA", "income_stmt_Net Income")
if trend:
    print(trend.format_response())
else:
    print("   ❌ No trend data available")

# Test 3: Gross Profit Margin Trend
print("\n" + "=" * 70)
print("3. Gross Profit Margin Trend:")
print("-" * 70)
trend = trend_calculator.calculate_trend("NVDA", "Gross Profit Margin %")
if trend:
    print(trend.format_response())
else:
    print("   ❌ No trend data available")

# Test 4: Multiple Metrics Trend
print("\n" + "=" * 70)
print("4. Multiple Metrics Trend Analysis:")
print("-" * 70)
metrics = [
    "income_stmt_Revenue",
    "income_stmt_Net Income",
    "income_stmt_Gross Profit"
]
trends = trend_calculator.calculate_multiple_trends("NVDA", metrics)
print(f"   Calculated {len(trends)} trends:\n")
for trend in trends:
    print(trend.format_response())
    print()

# Test 5: Balance Sheet Trends
print("\n" + "=" * 70)
print("5. Balance Sheet Trends:")
print("-" * 70)
metrics = [
    "balance_sheet_Total Assets",
    "balance_sheet_Stockholders Equity"
]
trends = trend_calculator.calculate_multiple_trends("NVDA", metrics)
print(f"   Calculated {len(trends)} trends:\n")
for trend in trends:
    print(trend.format_response())
    print()

# Test 6: Cash Flow Trends
print("\n" + "=" * 70)
print("6. Cash Flow Trends:")
print("-" * 70)
metrics = [
    "cash_flow_Operating Cash Flow",
    "cash_flow_Investing Cash Flow"
]
trends = trend_calculator.calculate_multiple_trends("NVDA", metrics)
print(f"   Calculated {len(trends)} trends:\n")
for trend in trends:
    print(trend.format_response())
    print()

# Test 7: Year-over-Year Growth
print("\n" + "=" * 70)
print("7. Year-over-Year Growth - Revenue:")
print("-" * 70)
yoy = trend_calculator.get_year_over_year_growth("NVDA", "income_stmt_Revenue")
if yoy:
    print("   Year-over-Year Growth Rates:")
    for data in yoy:
        print(f"      {data['year']}: ${data['value']:,.0f} ({data['yoy_growth']:+.2f}%)")
else:
    print("   ❌ No YoY data available")

# Test 8: Year-over-Year Growth - Net Income
print("\n" + "=" * 70)
print("8. Year-over-Year Growth - Net Income:")
print("-" * 70)
yoy = trend_calculator.get_year_over_year_growth("NVDA", "income_stmt_Net Income")
if yoy:
    print("   Year-over-Year Growth Rates:")
    for data in yoy:
        print(f"      {data['year']}: ${data['value']:,.0f} ({data['yoy_growth']:+.2f}%)")
else:
    print("   ❌ No YoY data available")

# Test 9: Trend with Specific Year Range
print("\n" + "=" * 70)
print("9. Trend with Year Range (2020-2023) - Revenue:")
print("-" * 70)
trend = trend_calculator.calculate_trend(
    "NVDA", 
    "income_stmt_Revenue",
    start_year=2020,
    end_year=2023
)
if trend:
    print(trend.format_response())
else:
    print("   ❌ No trend data available for this range")

# Test 10: ROA Trend
print("\n" + "=" * 70)
print("10. Return on Assets Trend:")
print("-" * 70)
trend = trend_calculator.calculate_trend("NVDA", "Return on Assets (ROA) %")
if trend:
    print(trend.format_response())
else:
    print("   ❌ No ROA trend data available")

# Test 11: Format Multiple Trends as Context
print("\n" + "=" * 70)
print("11. Format Trends for LLM Context:")
print("-" * 70)
metrics = [
    "income_stmt_Revenue",
    "income_stmt_Net Income",
    "Gross Profit Margin %"
]
trends = trend_calculator.calculate_multiple_trends("NVDA", metrics)
formatted = trend_calculator.format_as_context(trends)
print("   Formatted Context Strings:\n")
for i, context_str in enumerate(formatted, 1):
    print(f"{i}. {context_str}")
    print()

# Test 12: Non-existent Metric
print("\n" + "=" * 70)
print("12. Non-existent Metric Test:")
print("-" * 70)
trend = trend_calculator.calculate_trend("NVDA", "NonExistent Metric")
if trend:
    print(trend.format_response())
else:
    print("   ✓ Correctly returned None for non-existent metric")

print("\n" + "=" * 70)
print("✅ Trend Calculator Test COMPLETED")
print("=" * 70 + "\n")