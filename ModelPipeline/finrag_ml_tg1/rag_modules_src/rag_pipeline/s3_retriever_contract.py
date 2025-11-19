"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                         S3VectorsRetriever                                  │
│                    (Complete Retrieval Strategy)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ retrieve(base_embedding, base_query, 
                                    │          filtered_filters, global_filters)
                                    ▼
        ┌───────────────────────────────────────────────────────────┐
        │  STEP 1: Variant Generation (Internal)                    │
        │  ─────────────────────────────────────────                │
        │  if self.enable_variants:                                 │
        │     var_queries, var_embs = variant_pipeline.generate()   │
        │  else:                                                     │
        │     var_queries, var_embs = [], []                        │
        └───────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────────────┐
        │  STEP 2: Base Query Retrieval                             │
        │  ─────────────────────────────────────                    │
        │  _retrieve_for_embedding(base_embedding, variant_id=0)    │
        │     ├─ Filtered Call → S3 Vectors (topK=30)              │
        │     └─ Global Call   → S3 Vectors (topK=15)              │
        │                                                            │
        │  Result: base_hits (filtered + global sources)            │
        └───────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────────────┐
        │  STEP 3: Variant Queries Retrieval (Loop)                │
        │  ─────────────────────────────────────                    │
        │  for i, var_emb in enumerate(var_embs):                   │
        │     _retrieve_for_embedding(var_emb, variant_id=i+1)      │
        │        └─ Filtered Call ONLY → S3 Vectors (topK=15)       │
        │                                                            │
        │  Result: variant_hits (filtered source only)              │
        └───────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────────────┐
        │  STEP 4: Deduplication                                    │
        │  ─────────────────────────────────────────                │
        │  all_hits = base_hits + variant_hits                      │
        │                                                            │
        │  Group by: (sentence_id, embedding_id)                    │
        │  Keep: Best (lowest) distance                             │
        │  Aggregate: sources {filtered, global}                    │
        │            variant_ids {0, 1, 2, ...}                     │
        │                                                            │
        │  Result: union_hits (deduplicated)                        │
        └───────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────────────┐
        │  STEP 5: Bundle Assembly                                  │
        │  ─────────────────────────────────────────                │
        │  filtered_hits = [h for h in union if "filtered" in h]    │
        │  global_hits   = [h for h in union if "global" in h]      │
        │                                                            │
        │  return RetrievalBundle(                                  │
        │     filtered_hits, global_hits, union_hits,               │
        │     base_query, variant_queries                           │
        │  )                                                         │
        └───────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                            RetrievalBundle
                   (Ready for window expansion)


═══════════════════════════════════════════════════════════════════════════════
                            DATA FLOW SUMMARY
═══════════════════════════════════════════════════════════════════════════════

INPUT:
  • base_embedding: [1024-d float32]  ← From QueryEmbedderV2
  • base_query: str                   ← Original user query
  • filtered_filters: dict            ← Strong constraints (CIK, year, section)
  • global_filters: dict              ← Relaxed constraints (CIK, year>=2015)

INTERNAL (if variants enabled):
  • VariantPipeline.generate(base_query)
      ├─ VariantGenerator → ["variant1", "variant2", "variant3"]
      ├─ EntityAdapter.extract(each variant)
      └─ QueryEmbedderV2.embed_query(each variant) → [1024-d, 1024-d, 1024-d]

RETRIEVAL CALLS:
  • Base: 2 calls (filtered + global)
  • Variants: 3 calls (filtered only)
  • Total: 5 S3 Vectors queries

RAW RESULTS:
  • Base filtered:   ~30 hits (variant_id=0, source="filtered")
  • Base global:     ~15 hits (variant_id=0, source="global")
  • Variant 1:       ~15 hits (variant_id=1, source="filtered")
  • Variant 2:       ~15 hits (variant_id=2, source="filtered")
  • Variant 3:       ~15 hits (variant_id=3, source="filtered")
  • Total raw:       ~90 hits

AFTER DEDUP:
  • union_hits:      ~60 unique (sentence_id, embedding_id) pairs
  • filtered_hits:   ~45 hits (came from any filtered call)
  • global_hits:     ~20 hits (came from global call)

OUTPUT:
  • RetrievalBundle with all three lists + provenance metadata
═══════════════════════════════════════════════════════════════════════════════
"""