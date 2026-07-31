"""Measure what the per-request DataLoader memo actually throws away.

The audit found S3StreamingLoader memoises each table into an instance
attribute on first use. init_rag_components() builds a fresh loader per
request, so that memo dies with the request.

Question: how much work is that? If a cold table load is expensive, caching
components buys far more than the 825 ms of constructor time - because it also
keeps the loaded tables.

Cold  = new loader instance, first call  (what every request pays today)
Warm  = same loader instance, second call (what a cached component would pay)
"""
import time

from finrag_ml_tg1.loaders.data_loader_factory import create_data_loader
from finrag_ml_tg1.loaders.ml_config_loader import MLConfig

TABLES = [
    ("load_stage2_meta", "Stage 2 meta (sentence fact + embed metadata)"),
    ("load_kpi_fact_data", "KPI fact table"),
    ("load_dimension_companies", "dim: companies"),
    ("load_dimension_sections", "dim: sections"),
]

config = MLConfig()
print(f"loader mode: {type(create_data_loader(config)).__name__}\n")
print(f"{'table':<46} {'cold ms':>10} {'warm ms':>10} {'rows':>12}")
print("-" * 82)

cold_total = warm_total = 0.0
for method, label in TABLES:
    loader = create_data_loader(config)          # fresh instance = cold memo
    fn = getattr(loader, method, None)
    if fn is None:
        print(f"{label:<46} {'no method':>10}")
        continue
    try:
        t0 = time.perf_counter()
        df = fn()
        cold = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        fn()                                     # same instance = warm memo
        warm = (time.perf_counter() - t0) * 1000
        rows = f"{len(df):,}" if hasattr(df, "__len__") else "?"
        cold_total += cold
        warm_total += warm
        print(f"{label:<46} {cold:10.1f} {warm:10.2f} {rows:>12}")
    except Exception as exc:
        print(f"{label:<46} ERROR {type(exc).__name__}: {str(exc)[:40]}")

print("-" * 82)
print(f"{'TOTAL':<46} {cold_total:10.1f} {warm_total:10.2f}")
print(f"\nPer-request table work discarded today: {cold_total:.0f} ms")
print(f"Same work with a cached component:      {warm_total:.1f} ms")
