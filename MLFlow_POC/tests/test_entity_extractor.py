from retrieval.entity_extractor import entity_extractor

print("Testing Entity Extractor with Real Metrics...")
print("=" * 70)

# Test queries matching actual parquet file structure
test_queries = [
    # Revenue queries
    "What was NVDA's revenue in 2023?",
    "Show me Nvidia's sales from 2020 to 2023",
    
    # Profit queries
    "What is the net income for NVDA?",
    "Show me profit trends",
    "What was the gross profit in 2023?",
    
    # Margin queries
    "What are NVDA's gross margins?",
    "Show me profit margins over time",
    
    # Balance sheet queries
    "What are Nvidia's total assets?",
    "Show me the balance sheet for NVDA",
    "What is the stockholders equity?",
    "Show me current assets and liabilities",
    
    # Cash flow queries
    "What is the operating cash flow?",
    "Show me all cash flows for NVDA",
    "What is the free cash flow?",
    
    # Returns
    "What is the ROA for Nvidia?",
    "Show me return on assets",
    
    # Costs
    "What was the cost of revenue?",
    "Show me operating expenses",
    
    # Tax and Interest
    "What are the tax provisions?",
    "Show me interest expense",
    
    # Complex queries
    "Why did revenue grow?",
    "What are the main business risks?",
    "Analyze net income trends from 2020 to 2023 for NVDA",
    "Compare revenue and profit margins"
]

for i, query in enumerate(test_queries, 1):
    print(f"\n{'='*70}")
    print(f"Test {i}: {query}")
    print('-' * 70)
    
    entities = entity_extractor.extract(query)
    
    print(f"✓ Ticker: {entities.ticker}")
    
    if entities.metrics:
        print(f"✓ Metrics: {len(entities.metrics)} found")
        for metric in entities.metrics:
            print(f"    • {metric}")
    else:
        print(f"✗ Metrics: None (will use defaults)")
    
    if entities.years:
        print(f"✓ Years: {entities.years}")
    else:
        print(f"  Years: None (all available)")
    
    if entities.year_range:
        print(f"✓ Year Range: {entities.year_range[0]} to {entities.year_range[1]}")
    
    if entities.comparison_terms:
        print(f"✓ Comparison Terms: {', '.join(entities.comparison_terms)}")

print("\n" + "=" * 70)
print("✅ Entity Extractor Test COMPLETED")
print("=" * 70)

# Summary statistics
print("\n📊 SUMMARY:")
print("-" * 70)
total = len(test_queries)
with_metrics = sum(1 for q in test_queries if entity_extractor.extract(q).metrics)
with_years = sum(1 for q in test_queries if entity_extractor.extract(q).years)
with_ranges = sum(1 for q in test_queries if entity_extractor.extract(q).year_range)
with_trends = sum(1 for q in test_queries if entity_extractor.extract(q).comparison_terms)

print(f"Total queries tested: {total}")
print(f"Queries with extracted metrics: {with_metrics} ({with_metrics/total*100:.0f}%)")
print(f"Queries with extracted years: {with_years} ({with_years/total*100:.0f}%)")
print(f"Queries with year ranges: {with_ranges} ({with_ranges/total*100:.0f}%)")
print(f"Queries with trend indicators: {with_trends} ({with_trends/total*100:.0f}%)")
print("=" * 70 + "\n")