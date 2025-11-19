"""
═══════════════════════════════════════════════════════════════════════════════
                        FINRAG RETRIEVAL PIPELINE v1.0
                      (Entity → S3 Vectors → LLM Context)
═══════════════════════════════════════════════════════════════════════════════

User Query: "What were NVIDIA's AI risks in 2017-2020?"
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Entity Extraction                                                 │
│ ───────────────────────────────────────────────────────────────────────── │
│ Module: EntityAdapter                                                     │
│ Output: EntityExtractionResult                                            │
│   • companies: [NVIDIA] (CIK: 1045810)                                    │
│   • years: [2017, 2018, 2019, 2020]                                       │
│   • sections: [ITEM_1A] (Risk Factors)                                    │
│   • metrics: [] (none detected)                                           │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Base Query Embedding                                              │
│ ───────────────────────────────────────────────────────────────────────── │
│ Module: QueryEmbedderV2                                                   │
│ Output: 1024-d Cohere v4 embedding                                        │
│   • Bedrock inference (us-east-1)                                         │
│   • Cost: ~$0.0001 per query                                              │
│   • Guardrails: Query length, scope validation                            │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Metadata Filter Construction                                      │
│ ───────────────────────────────────────────────────────────────────────── │
│ Module: MetadataFilterBuilder                                             │
│ Output: Filtered + Global filter JSONs                                    │
│   • Filtered: {cik_int: 1045810, report_year: [2017-2020], section: 1A}  │
│   • Global: {cik_int: 1045810, report_year: >=2015}                       │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Variant Generation (Internal to S3Retriever)                      │
│ ───────────────────────────────────────────────────────────────────────── │
│ Module: VariantPipeline (if enabled)                                      │
│ Output: 3 variant queries + 3 variant embeddings                          │
│   • VariantGenerator: LLM-based rephrasing (Haiku 4.5)                    │
│   • Per-variant entity extraction (EntityAdapter)                         │
│   • Per-variant embedding (QueryEmbedderV2)                               │
│   • Cost: ~$0.0006 per query (3 variants)                                 │
│   • Semantic similarity: 93-98% with base query                           │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ STEP 5: S3 Vectors Retrieval (Complete Strategy)                          │
│ ───────────────────────────────────────────────────────────────────────── │
│ Module: S3VectorsRetriever                                                │
│                                                                            │
│ Sub-step 5a: Base Query Retrieval                                         │
│   • Filtered call: topK=30 (strict constraints)                           │
│   • Global call: topK=15 (temporal relaxation)                            │
│                                                                            │
│ Sub-step 5b: Variant Query Retrieval (if enabled)                         │
│   • Variant 1: Filtered call, topK=15                                     │
│   • Variant 2: Filtered call, topK=15                                     │
│   • Variant 3: Filtered call, topK=15                                     │
│   • Strategy: Filtered ONLY (semantic, not temporal diversity)            │
│                                                                            │
│ Sub-step 5c: Hit-Level Deduplication (Dedup #1)                           │
│   • Key: (sentence_id, embedding_id)                                      │
│   • Keep: Best (lowest) distance                                          │
│   • Aggregate: sources {filtered, global}, variant_ids {0,1,2,3}          │
│   • Raw: ~75 hits → Unique: ~30 hits                                      │
│                                                                            │
│ Sub-step 5d: Proportional TopK Sampling                                   │
│   • Limit: 30 hits before window expansion                                │
│   • Strategy: 70% from filtered, 30% from global                          │
│   • Avoids cross-pool distance comparison issues                          │
│   • Output: ~21 filtered + 9 global = 30 balanced hits                    │
│                                                                            │
│ Output: RetrievalBundle (filtered_hits, global_hits, union_hits)          │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ STEP 6: Window Expansion                                                  │
│ ───────────────────────────────────────────────────────────────────────── │
│ Module: SentenceExpander._expand_windows()                                │
│ Input: 30 S3Hits                                                          │
│ Output: ~210 SentenceRecords (with duplicates)                            │
│                                                                            │
│ Process:                                                                   │
│   • For each hit: Calculate window [pos-3, pos+3]                         │
│   • Query Stage 2 meta (by position range)                                │
│   • Mark is_core_hit for actual S3 hits                                   │
│   • Populate navigation fields (prev/next/section_count)                  │
│   • Edge cases: Near-start, near-end, last sentence, malformed IDs        │
│                                                                            │
│ Tested edge cases:                                                        │
│   ✓ pos=2 (near-start): Window [1-5] = 5 sentences                        │
│   ✓ pos=90 (middle): Window [87-93] = 7 sentences                         │
│   ✓ pos=178 (near-end): Window [175-180] = 6 sentences                    │
│   ✓ pos=180 (last): Window [177-180] = 4 sentences                        │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ STEP 7: Sentence-Level Deduplication (Dedup #2 - FINAL)                   │
│ ───────────────────────────────────────────────────────────────────────── │
│ Module: SentenceExpander._deduplicate_sentences()                         │
│ Input: ~210 SentenceRecords (overlapping windows)                         │
│ Output: ~140 unique SentenceRecords                                       │
│                                                                            │
│ Strategy:                                                                  │
│   • Key: (sentence_id, cik, year, section)                                │
│   • Keep: Best (lowest) parent_hit_distance                               │
│   • Aggregate: sources, variant_ids, is_core_hit (OR)                     │
│                                                                            │
│ Tested overlap:                                                           │
│   ✓ 4-sentence overlap between Hit 3 and Hit 4                            │
│   ✓ Kept better distance (0.20 < 0.22)                                    │
│   ✓ Merged provenance (filtered+global, variant 0+1)                      │
│   ✓ Preserved both core markers (pos=178, pos=180)                        │
│                                                                            │
│ THIS IS THE FINAL DEDUPLICATION - No Stage-2 dedup needed                 │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ OUTPUT: List[SentenceRecord] (~140 unique sentences)                      │
│ ───────────────────────────────────────────────────────────────────────── │
│ Each record contains:                                                     │
│   • sentence_id, sentence_pos, text                                       │
│   • cik_int, report_year, section_name, company_name                      │
│   • is_core_hit (True=S3 hit, False=neighbor)                             │
│   • parent_hit_distance (best score)                                      │
│   • sources {filtered, global}, variant_ids {0,1,2,3}                     │
│                                                                            │
│ Ready for ContextAssembler                                                │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ STEP 8: Context Assembly & Formatting                                     │
│ ───────────────────────────────────────────────────────────────────────── │
│ Module: ContextAssembler ()                                               │
│ Input: ~140 SentenceRecords                                               │
│ Output: Formatted string for LLM                                          │
│                                                                            │
│ Process:                                                                   │
│   1. Sort by (company, year DESC, section, doc, pos)                      │
│   2. Optional: Select top K sentences (by parent_hit_distance)            │
│   3. Group by (company, year, section) for headers                        │
│   4. Format:                                                               │
│      === NVIDIA CORP | 2020 | ITEM_1A ===                                 │
│      sentence1                                                             │
│      sentence2                                                             │
│                                                                            │
│      === NVIDIA CORP | 2019 | ITEM_1A ===                                 │
│      sentence3                                                             │
│   5. Return single string                                                 │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────────────────────┐
│ STEP 9: LLM Synthesis ()                                                  │
│ ───────────────────────────────────────────────────────────────────────── │
│ Module: BedrockClient / QueryOrchestrator                                 │
│ Input: Formatted context string + user query                              │
│ Output: LLM-generated answer                                              │
│                                                                            │
│ Components:                                                                │
│   • Prompt template (system + context + query)                            │
│   • Bedrock Claude call (Sonnet/Opus)                                     │
│   • Citation extraction                                                    │
│   • Response validation                                                    │
└───────────────────────────────────────────────────────────────────────────┘
    ↓
Final Answer + Citations


═══════════════════════════════════════════════════════════════════════════════
PIPELINE STATISTICS (Based on Test Query)
═══════════════════════════════════════════════════════════════════════════════

Input:  1 user query
Step 1: 2 companies, 4 years, 2 sections extracted
Step 2: 1 base embedding (1024-d)
Step 4: 3 variant queries + 3 embeddings generated
Step 5: 5 S3 queries executed (1 base × 2 modes + 3 variants)
        75 raw hits → 34 deduplicated hits → 30 after proportional topK
Step 6: 30 hits → ~210 sentence records (±3 window expansion)
Step 7: 210 records → ~140 unique sentences (final dedup)
Step 8: Format ~140 sentences with headers
Step 9: Send to LLM for synthesis

Deduplication points:
  • Dedup #1: S3 hit level (75 → 34, by sentence_id+embedding_id)
  • Dedup #2: Sentence level (210 → 140, by sentence_id after windowing)
  • Total: 2 dedup stages, NO block-level dedup needed
"""