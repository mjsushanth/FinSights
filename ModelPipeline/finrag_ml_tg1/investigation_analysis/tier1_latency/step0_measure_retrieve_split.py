"""Throwaway diagnostic: split the `retrieve` timer into variant-gen vs S3-query time.

TIER1_LATENCY_DESIGN.md section 0.1 / Step 0. Calls run_supply_line_2_rag() directly
(NOT answer_query()) to avoid paying for LLM synthesis on every measurement - this
isolates retrieval, which is all Step 0 needs to measure.

Cost per run: 1 Haiku variant-gen call (max_tokens=150) + up to 3 Cohere embeddings
(the base embedding is already paid for by embed_query) + up to 5 QueryVectors calls.
No LLM synthesis call. Far cheaper than a full answer_query().

Output: a Polars dataframe written to
  investigation_analysis/tier1_latency/step0_results_<timestamp>.parquet
plus a printed summary (median/mean/min/max for the two split timers).
"""
from pathlib import Path
import sys
import time

for p in [Path.cwd()] + list(Path.cwd().parents):
    if p.name == "ModelPipeline":
        model_root = p
        break
if str(model_root) not in sys.path:
    sys.path.insert(0, str(model_root))

import polars as pl

from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.supply_lines import (
    init_rag_components,
    run_supply_line_2_rag,
)

QUERIES = [
    "What was NVIDIA's revenue in 2021?",
    "How did Microsoft describe cloud growth in 2022?",
    "What were Apple's R&D expenses in 2020?",
    "Describe Tesla's risk factors related to supply chain in 2019.",
]
RUNS_PER_QUERY = 3  # 4 queries x 3 = 12 runs, under the 40-query session cap

rag = init_rag_components()

rows = []
for query in QUERIES:
    for run_idx in range(RUNS_PER_QUERY):
        t0 = time.perf_counter()
        _, _, bundle, unique_sents, _, telemetry = run_supply_line_2_rag(query, rag)
        wall_ms = (time.perf_counter() - t0) * 1000

        rows.append({
            "query": query,
            "run_idx": run_idx,
            "wall_ms": wall_ms,
            "variant_gen_ms": bundle.variant_gen_ms,
            "s3_query_ms": bundle.s3_query_ms,
            "n_union_hits": len(bundle.union_hits),
            "n_unique_sents": len(unique_sents),
            "n_variant_queries": len(bundle.variant_queries),
        })
        print(
            f"[{query[:40]:<40}] run={run_idx} "
            f"variant_gen={bundle.variant_gen_ms:7.1f}ms  "
            f"s3_query={bundle.s3_query_ms:7.1f}ms  "
            f"wall={wall_ms:7.1f}ms"
        )

df = pl.DataFrame(rows)

out_dir = Path(__file__).parent
timestamp = time.strftime("%Y%m%d_%H%M%S")
out_path = out_dir / f"step0_results_{timestamp}.parquet"
df.write_parquet(out_path)

print("\n" + "=" * 70)
print("SUMMARY (across all runs)")
print("=" * 70)
summary = df.select(
    pl.col("variant_gen_ms").median().alias("variant_gen_median"),
    pl.col("variant_gen_ms").mean().alias("variant_gen_mean"),
    pl.col("variant_gen_ms").min().alias("variant_gen_min"),
    pl.col("variant_gen_ms").max().alias("variant_gen_max"),
    pl.col("s3_query_ms").median().alias("s3_query_median"),
    pl.col("s3_query_ms").mean().alias("s3_query_mean"),
    pl.col("s3_query_ms").min().alias("s3_query_min"),
    pl.col("s3_query_ms").max().alias("s3_query_max"),
)
print(summary)
print(f"\nWritten to: {out_path}")
print(f"n_runs = {len(df)}")

s3_median = summary["s3_query_median"][0]
print(f"\nGATE per TIER1_LATENCY_DESIGN.md section 0: S (median s3_query_ms) = {s3_median:.1f} ms")
if s3_median > 2500:
    print("  -> S > 2500ms: change 3 (concurrency) worth pursuing, proceed.")
elif s3_median > 1500:
    print("  -> S in 1500-2500ms: proceed, expect ~1.2-1.8s saved, not 3s.")
else:
    print("  -> S < 1500ms: ABANDON change 3. Time is in variant generation.")
