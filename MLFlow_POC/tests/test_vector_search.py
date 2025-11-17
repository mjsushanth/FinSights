from retrieval.vector_search import vector_search

print("Testing Vector Search with Company Names...")
print("=" * 70)

# Test 0: Check available data
print("\n0. Available Data:")
print("-" * 70)
available_companies = vector_search.get_available_companies()
available_years = vector_search.get_available_years(ticker="NVDA")
available_sections = vector_search.get_available_sections()

print(f"✅ Available companies: {len(available_companies)} companies")
for company in available_companies:
    print(f"   • {company}")

print(f"\n✅ Available years for NVDA: {len(available_years)} years")
if available_years:
    print(f"   Years: {available_years[:5]}...{available_years[-5:]}")
else:
    print("   (No years found)")

print(f"\n✅ Available sections: {len(available_sections)} sections")
for section in available_sections:
    print(f"   • {section}")

# Test 1: Basic semantic search using ticker (auto-converted to company name)
print("\n" + "=" * 70)
print("1. Basic Semantic Search - AI and Data Center (using ticker):")
print("-" * 70)
results = vector_search.search("AI and data center growth", top_k=3, ticker="NVDA")
print(f"   Found {len(results.results)} results:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Relevance: {1 - result.distance:.3f}")
    print(f"      Company: {result.company}")
    if result.year:
        print(f"      Year: {result.year}")
    if result.section:
        print(f"      Section: {result.section}")
    print(f"      Text: {result.text[:150]}...")
    print()

# Test 2: Search using company name directly
print("\n" + "=" * 70)
print("2. Search using Company Name Directly:")
print("-" * 70)
results = vector_search.search(
    "revenue growth drivers",
    top_k=3,
    company="NVIDIA CORP"
)
print(f"   Found {len(results.results)} results:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Company: {result.company} | Relevance: {1 - result.distance:.3f}")
    print(f"      Text: {result.text[:120]}...")
    print()

# Test 3: Search with year filter (ticker auto-converted)
print("\n" + "=" * 70)
print("3. Search with Year Filter (2023, using ticker):")
print("-" * 70)
results = vector_search.search(
    "revenue growth drivers",
    top_k=3,
    ticker="NVDA",
    year=2023
)
print(f"   Found {len(results.results)} results from 2023:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Year: {result.year} | Relevance: {1 - result.distance:.3f}")
    print(f"      Company: {result.company}")
    print(f"      Text: {result.text[:120]}...")
    print()

# Test 4: Search within year range
print("\n" + "=" * 70)
print("4. Search within Year Range (2020-2023):")
print("-" * 70)
results = vector_search.search_by_year_range(
    "artificial intelligence demand",
    start_year=2020,
    end_year=2023,
    top_k=4,
    ticker="NVDA"
)
print(f"   Found {len(results.results)} results from 2020-2023:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Year: {result.year} | Company: {result.company}")
    print(f"      Relevance: {1 - result.distance:.3f}")
    print(f"      Text: {result.text[:100]}...")
    print()

# Test 5: Search by section - Risk Factors (ITEM_1A)
print("\n" + "=" * 70)
print("5. Search by Section - Risk Factors (ITEM_1A):")
print("-" * 70)
results = vector_search.search_by_section(
    "competition and competitive risks",
    section="ITEM_1A",
    top_k=3,
    ticker="NVDA"
)
print(f"   Found {len(results.results)} results in Risk Factors:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Section: {result.section} | Year: {result.year}")
    print(f"      Company: {result.company}")
    print(f"      Relevance: {1 - result.distance:.3f}")
    print(f"      Text: {result.text[:120]}...")
    print()

# Test 6: Search by section - Business (ITEM_1)
print("\n" + "=" * 70)
print("6. Search by Section - Business Description (ITEM_1):")
print("-" * 70)
results = vector_search.search_by_section(
    "company products and markets",
    section="ITEM_1",
    top_k=3,
    company="NVIDIA CORP"
)
print(f"   Found {len(results.results)} results in Business section:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Section: {result.section} | Year: {result.year}")
    print(f"      Company: {result.company}")
    print(f"      Relevance: {1 - result.distance:.3f}")
    print(f"      Text: {result.text[:120]}...")
    print()

# Test 7: Search by section - MD&A (ITEM_7)
print("\n" + "=" * 70)
print("7. Search by Section - MD&A (ITEM_7):")
print("-" * 70)
results = vector_search.search_by_section(
    "revenue and operating results",
    section="ITEM_7",
    top_k=3,
    ticker="NVDA"
)
print(f"   Found {len(results.results)} results in MD&A:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Section: {result.section} | Year: {result.year}")
    print(f"      Relevance: {1 - result.distance:.3f}")
    print(f"      Text: {result.text[:120]}...")
    print()

# Test 8: Combined filters - section and year
print("\n" + "=" * 70)
print("8. Combined Filters - Risk Factors in 2023:")
print("-" * 70)
results = vector_search.search(
    "supply chain risks",
    top_k=3,
    ticker="NVDA",
    year=2023,
    section="ITEM_1A"
)
print(f"   Found {len(results.results)} results:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Year: {result.year} | Section: {result.section}")
    print(f"      Company: {result.company}")
    print(f"      Relevance: {1 - result.distance:.3f}")
    print(f"      Text: {result.text[:120]}...")
    print()

# Test 9: Multiple related queries
print("\n" + "=" * 70)
print("9. Multi-Query Search:")
print("-" * 70)
queries = [
    "AI chip demand",
    "data center growth",
    "machine learning acceleration"
]
results = vector_search.multi_query_search(
    queries,
    top_k_per_query=2,
    ticker="NVDA",
    year=2023
)
print(f"   Combined query: {results.query}")
print(f"   Found {len(results.results)} unique results:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Year: {result.year} | Relevance: {1 - result.distance:.3f}")
    print(f"      Text: {result.text[:100]}...")
    print()

# Test 10: Format for LLM context
print("\n" + "=" * 70)
print("10. Format Results for LLM Context:")
print("-" * 70)
context = vector_search.search_with_context(
    "gaming and professional visualization",
    top_k=3,
    ticker="NVDA"
)
print("   Formatted context strings:\n")
for ctx in context:
    print(f"   {ctx[:200]}...")
    print()

# Test 11: Search without any filters
print("\n" + "=" * 70)
print("11. Search Without Filters (All Data):")
print("-" * 70)
results = vector_search.search(
    "cryptocurrency and mining",
    top_k=5
)
print(f"   Found {len(results.results)} results:\n")
for i, result in enumerate(results.results, 1):
    print(f"   {i}. Company: {result.company} | Year: {result.year}")
    print(f"      Relevance: {1 - result.distance:.3f}")
    print(f"      Text: {result.text[:100]}...")
    print()

# Test 12: Ticker to company conversion test
print("\n" + "=" * 70)
print("12. Ticker to Company Name Conversion Test:")
print("-" * 70)
test_tickers = ["NVDA", "AAPL", "MSFT"]
for ticker in test_tickers:
    company = vector_search._ticker_to_company(ticker)
    print(f"   {ticker} → {company}")

# Test 13: Get available years for specific company
print("\n" + "=" * 70)
print("13. Available Years by Company:")
print("-" * 70)
years_by_ticker = vector_search.get_available_years(ticker="NVDA")
years_by_company = vector_search.get_available_years(company="NVIDIA CORP")
print(f"   Years for NVDA (ticker): {len(years_by_ticker)} years")
if years_by_ticker:
    print(f"      {years_by_ticker[:3]}...{years_by_ticker[-3:]}")
print(f"   Years for NVIDIA CORP (company): {len(years_by_company)} years")
if years_by_company:
    print(f"      {years_by_company[:3]}...{years_by_company[-3:]}")

print("\n" + "=" * 70)
print("✅ Vector Search Test COMPLETED")
print("=" * 70)

# Summary
print("\n📊 SUMMARY:")
print("-" * 70)
print(f"Total companies: {len(available_companies)}")
print(f"Total years available: {len(available_years)}")
print(f"Total sections available: {len(available_sections)}")
if available_years:
    print(f"Year range: {min(available_years)} - {max(available_years)}")
print("\nCompany-Ticker Mappings:")
for ticker, company in vector_search.TICKER_TO_COMPANY.items():
    print(f"  {ticker} → {company}")
print("\nKey sections:")
print("  • ITEM_1: Business Description")
print("  • ITEM_1A: Risk Factors")
print("  • ITEM_7: Management's Discussion & Analysis")
print("  • ITEM_8: Financial Statements")
print("=" * 70 + "\n")