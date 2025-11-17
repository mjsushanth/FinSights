from data.loaders import data_loader

print("Testing Data Loader...")
print("=" * 70)

# Load all data
data_context = data_loader.load_all()

print(f"✅ Metrics loaded: {len(data_context.metrics)} rows")
print(f"✅ Sentences loaded: {len(data_context.sentences)} rows")
print(f"✅ FAISS index: {data_context.faiss_index.ntotal} vectors")
print(f"✅ Embedder model: {type(data_context.embedder).__name__}")

# Test available tickers
tickers = data_loader.get_available_tickers()
print(f"\n📊 Available tickers: {tickers}")

# Test available metrics
metrics = data_loader.get_available_metrics("NVDA")
print(f"📊 Available metrics for NVDA: {metrics}")

print("\n✅ Data Loader Test PASSED\n")