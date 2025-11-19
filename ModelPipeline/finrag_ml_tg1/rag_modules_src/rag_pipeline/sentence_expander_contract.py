# Purpose: S3Hits → ContextBlocks (window expansion + text fetch in one pass)
# ModelPipeline\finrag_ml_tg1\rag_modules_src\rag_pipeline\context_builder.py

"""
S3Hit:
  - sentence_id: str           # "doc123_1A_0045"
  - embedding_id: str          # "bedrock_cohere_v4_1024d_20241115..."
  - sentence_pos: int          # 45 (position in section)
  - section_sentence_count: int # 250 (total sentences in section)
  - cik_int, report_year, section_name, docID (grouping context)
  - distance, sources, variant_ids (scoring/provenance)

---------------------------------------------------------------------------------------------
From Stage 2 Meta Table: -- prev/next/section_count from Stage 2 
Available fields:
  - sentenceID: str
  - sentence: str              # ← THE TEXT
  - prev_sentenceID: str       # ← NAVIGATION
  - next_sentenceID: str       # ← NAVIGATION  
  - section_sentence_count: int # ← BOUNDARY
  - embedding_id: str          # ← JOIN KEY
  - cik_int, report_year, section_name, name (context)

1. Join on (sentenceID, embedding_id) - critical for multi-embedding scenarios. 
2. robust boundary logic - don't request impossible neighbors.

---------------------------------------------------------------------------------------------
Stage 2 Meta Table = Financial Information Textbook
├─ sentenceID → sentence (TEXT)
├─ Company/Year/Section metadata
└─ Context navigation (prev/next, sentence_pos)
Purpose: Get TEXT for context windows
Join key: sentenceID ONLY (no embedding_id needed!)
We're not querying "which embedding exists"
We're querying "what does this sentence SAY"
---------------------------------------------------------------------------------------------
"""


"""
═══════════════════════════════════════════════════════════════════════════════
sentence_expander !! RENAMED.
Past: CONTEXT BUILDER 

- DESIGN CONTRACT
═══════════════════════════════════════════════════════════════════════════════

Purpose:
    Converts S3 sentence-level hits into deduplicated sentence records with
    windowed context (±N neighbors). Does NOT create blocks - just expands
    and deduplicates. Assembly handles grouping and formatting.

Architecture Philosophy:
    - Expand windows to get context (neighbors around core hits)
    - Deduplicate at sentence level (one sentence, one record, best evidence)
    - Return flat list (let Assembly decide how to group/format)
    - No premature optimization (no "contiguous run detection")

═══════════════════════════════════════════════════════════════════════════════
PIPELINE FLOW
═══════════════════════════════════════════════════════════════════════════════

Input: 30 S3Hits (after S3 retrieval + proportional topK)
    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Window Expansion                                                    │
│ ─────────────────────────────────────────────────────────────────────────── │
│ For each S3Hit:                                                             │
│   • Calculate window: [sentence_pos - 3, sentence_pos + 3]                  │
│   • Clamp to bounds: [max(0, start), min(section_count-1, end)]             │
│   • Query Stage 2 Meta: Get sentences in position range                     │
│   • Create SentenceRecord for each (core + neighbors)                       │
│   • Mark is_core_hit=True for the actual S3 hit                             │
│                                                                              │
│ Output: ~210 SentenceRecords (7 avg per hit, with duplicates)               │
└─────────────────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Sentence-Level Deduplication                                        │
│ ─────────────────────────────────────────────────────────────────────────── │
│ Group by: (sentence_id, cik_int, report_year, section_name)                │
│ Keep: Record with BEST (lowest) parent_hit_distance                         │
│ Aggregate: sources, variant_ids, is_core_hit (OR operation)                 │
│                                                                              │
│ Why this works:                                                             │
│   • Overlapping windows → same sentence appears multiple times              │
│   • We keep the version from the BEST hit (lowest distance)                 │
│   • Provenance preserved (which sources/variants contributed)               │
│   • is_core_hit=TRUE if ANY version was a core hit                          │
│                                                                              │
│ Output: ~140 unique SentenceRecords (one per sentence)                      │
└─────────────────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ OUTPUT: List[SentenceRecord]                                                │
│ ─────────────────────────────────────────────────────────────────────────── │
│ Flat list of deduplicated sentences                                         │
│ Ready for Assembly to sort/group/format                                     │
│                                                                              │
│ NO ContextBlocks created                                                    │
│ NO contiguous run detection                                                 │
│ NO premature grouping                                                       │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
DOWNSTREAM: CONTEXT ASSEMBLER (Step 10)
═══════════════════════════════════════════════════════════════════════════════

Input: ~140 SentenceRecords
    ↓
Step 1: Sort by functional order
    Key: (company, year DESC, section, doc_id, sentence_pos)
    Purpose: Group related sentences, most recent first
    ↓
Step 2: Optional - Select top K sentences
    By: parent_hit_distance (best evidence first)
    Or: Take all if under token limit
    ↓
Step 3: Group by (company, year, section)
    Purpose: Insert headers when context changes
    NOT for deduplication - just for formatting
    ↓
Step 4: Format with minimal headers
    Output:
        === NVIDIA CORP | 2020 | ITEM_1A ===
        sentence1
        sentence2
        
        === MICROSOFT CORP | 2020 | ITEM_7 ===
        sentence3
        sentence4
    ↓
Step 5: Return single string
    Purpose: LLM-ready context
    One coherent text with clear section markers

═══════════════════════════════════════════════════════════════════════════════
CRITICAL DESIGN DECISIONS
═══════════════════════════════════════════════════════════════════════════════

1. WINDOW EXPANSION STRATEGY
   ───────────────────────────────────────────────────────────────────────────
   Method: Position-based (sentence_pos ± window_size)
   
   Why not prev/next_sentenceID?
   • sentence_pos is contiguous (verified for 2015-2020 data)
   • Range queries are faster (one filter vs N lookups)
   • Edge cases handled automatically by max/min clamping
   
   Edge case handling:
   • First sentence (pos=0): window starts at 0
   • Last sentence (pos=N-1): window ends at N-1
   • Tiny sections: window doesn't exceed section bounds
   • Single sentence sections: window = [just that sentence]
   
   Formula:
   window_start = max(0, sentence_pos - window_size)
   window_end = min(section_sentence_count - 1, sentence_pos + window_size)

2. EMBEDDING_ID HANDLING
   ───────────────────────────────────────────────────────────────────────────
   Question: Should we filter by embedding_id when fetching neighbors?
   
   Answer: NO
   
   Reasoning:
   • We're querying Stage 2 Meta = "financial information textbook"
   • We want TEXT, not embeddings
   • Neighbor's embedding status is irrelevant for context
   • If sentence has multiple embeddings, take first (text is identical)
   
   Implementation:
   window = meta_df.filter(
       (cik == ...) & (year == ...) & (section == ...) &
       (sentence_pos.is_between(start, end))
       # NO embedding_id filter ✓
   ).unique(subset=['sentenceID'], keep='first')

3. DEDUPLICATION STRATEGY
   ───────────────────────────────────────────────────────────────────────────
   Total dedups in pipeline: 2 (not 3!)
   
   Dedup #1: In S3VectorsRetriever
   • Key: (sentence_id, embedding_id)
   • Purpose: Merge filtered/global/variant results
   • Keep: Best distance per sentence
   
   Dedup #2: In ContextBuilder (THIS MODULE)
   • Key: (sentence_id, cik, year, section)
   • Purpose: Merge overlapping windows
   • Keep: Best parent_hit_distance
   • Aggregate: sources, variant_ids, is_core_hit
   
   NO Stage-2 Dedup module needed!
   • After sentence dedup, we're done
   • Assembly just sorts and formats
   • No block-level deduplication required

4. PROVENANCE TRACKING
   ───────────────────────────────────────────────────────────────────────────
   is_core_hit marker:
   • TRUE: This sentence was an actual S3 retrieval result
   • FALSE: This sentence is a neighbor (context)
   
   Aggregation during dedup:
   • If sentence appears in multiple windows:
     - Keep version with best parent_hit_distance
     - is_core_hit = TRUE if ANY version was core
     - sources = union of all sources
     - variant_ids = union of all variant_ids
   
   Purpose:
   • Evaluation: "Did we retrieve gold sentence or just its neighbor?"
   • Analysis: "How many core hits vs context in final output?"

5. OUTPUT FORMAT
   ───────────────────────────────────────────────────────────────────────────
   ContextBuilder returns: List[SentenceRecord]
   
   NOT List[ContextBlock]
   NOT grouped by contiguous runs
   NOT formatted for LLM
   
   Just: Flat list of unique sentences with full metadata
   
   Assembly handles:
   • Sorting by functional order
   • Grouping by semantic boundaries (company/year/section)
   • Formatting with headers
   • Creating final LLM prompt string

6. STAGE 2 META TABLE USAGE
   ───────────────────────────────────────────────────────────────────────────
   Path: model_root/finrag_ml_tg1/data_cache/meta_embeds/finrag_fact_sentences_meta_embeds.parquet
   
   Fields used:
   • sentenceID (str) - join key
   • sentence (str) - THE TEXT
   • sentence_pos (int) - for range queries
   • cik_int, report_year, section_name - for filtering
   • name (str) - company name for display
   • docID (str) - document identifier
   • prev_sentenceID (str) - populated for safety (optional use)
   • next_sentenceID (str) - populated for safety (optional use)
   • section_sentence_count (int) - populated for safety (optional use)
   
   NOT used:
   • embedding_id - we don't care about embedding status
   • embedding vector - we want text, not vectors

═══════════════════════════════════════════════════════════════════════════════
EXAMPLE FLOW
═══════════════════════════════════════════════════════════════════════════════

Input: 3 S3Hits
    Hit A: sentence_pos=44, distance=0.18, cik=1045810, year=2020, section=ITEM_1A
    Hit B: sentence_pos=46, distance=0.22, cik=1045810, year=2020, section=ITEM_1A
    Hit C: sentence_pos=12, distance=0.15, cik=789019, year=2020, section=ITEM_7

After Step 1 (Expansion):
    Hit A → [41, 42, 43, 44*, 45, 46, 47] = 7 records (* = core)
    Hit B → [43, 44, 45, 46*, 47, 48, 49] = 7 records
    Hit C → [9, 10, 11, 12*, 13, 14, 15] = 7 records
    Total: 21 records (with duplicates)

After Step 2 (Dedup):
    From Hit A+B overlap:
        s43: Keep from A (0.18 < 0.22), is_core=False
        s44: Keep from A (0.18 < 0.22), is_core=True (A's core)
        s45: Keep from A (0.18 < 0.22), is_core=False
        s46: Keep from A (0.18 < 0.22), is_core=True (B's core, but A wins on distance)
        s47: Keep from A (0.18 < 0.22), is_core=False
    
    Unique from A: [s41, s42]
    Unique from B: [s48, s49]
    Unique from C: [s9, s10, s11, s12, s13, s14, s15]
    
    Total: 14 unique sentences

Output: List[SentenceRecord] with 14 deduplicated sentences

Then Assembly:
    Sort by: (cik, year DESC, section, doc, pos)
    Result order:
        MSFT 2020 ITEM_7: [s9, s10, s11, s12, s13, s14, s15]
        NVDA 2020 ITEM_1A: [s41, s42, s43, s44, s45, s46, s47, s48, s49]
    
    Format:
        === MICROSOFT CORP | 2020 | ITEM_7 ===
        sentence9
        sentence10
        ...
        
        === NVIDIA CORP | 2020 | ITEM_1A ===
        sentence41
        sentence42
        ...

═══════════════════════════════════════════════════════════════════════════════
EDGE CASES & VALIDATION
═══════════════════════════════════════════════════════════════════════════════

Window Expansion Edge Cases:
    ✓ First sentence (pos=0): Window starts at 0, not negative
    ✓ Last sentence (pos=N-1): Window ends at N-1, not beyond
    ✓ Tiny sections (<7 sentences): Window = entire section
    ✓ Single sentence section: Window = just that sentence
    ✓ Empty window results: Log warning, skip hit (graceful)
    ✓ Core hit not in window: Log error, continue (defensive)

Deduplication Edge Cases:
    ✓ Empty input: Returns empty list
    ✓ Single version: No aggregation, just return
    ✓ Multiple versions: Keep best distance, aggregate provenance
    ✓ is_core_hit conflict: TRUE if ANY version was core
    ✓ Provenance aggregation: Union of sources and variant_ids

Data Quality Validation:
    ✓ Log expansion stats (core vs neighbors)
    ✓ Log dedup stats (before → after counts)
    ✓ Track core_hit_count for evaluation
    ✓ Validate core hit appears in its own window

═══════════════════════════════════════════════════════════════════════════════
MODULE RESPONSIBILITIES
═══════════════════════════════════════════════════════════════════════════════

ContextBuilder (Steps 6-7):
    DOES:
        ✓ Window expansion (±3 sentences)
        ✓ Sentence-level deduplication
        ✓ Provenance aggregation
        ✓ Edge case handling
    
    DOES NOT:
        ✗ Create ContextBlocks (that's Assembly's job)
        ✗ Group into contiguous runs (artificial boundaries)
        ✗ Format text (that's Assembly's job)
        ✗ Apply topK selection (already done in retriever)
    
    Returns: List[SentenceRecord]

ContextAssembler (Step 10):
    DOES:
        ✓ Sort sentences by functional order
        ✓ Group by (company, year, section) for headers
        ✓ Format with minimal headers
        ✓ Concatenate into LLM-ready string
        ✓ Optional: Select top K sentences by score
    
    DOES NOT:
        ✗ Deduplicate (already done)
        ✗ Expand windows (already done)
        ✗ Create artificial block boundaries
    
    Returns: str (formatted context)

═══════════════════════════════════════════════════════════════════════════════
DATA FLOW
═══════════════════════════════════════════════════════════════════════════════

S3VectorsRetriever
    ↓
RetrievalBundle.union_hits (30 S3Hits)
    ↓
ContextBuilder.build_sentences()  ← Returns List[SentenceRecord]
    ↓
~140 unique SentenceRecords
    ↓
ContextAssembler.assemble()
    ↓
Single formatted string with headers
    ↓
LLM Prompt

═══════════════════════════════════════════════════════════════════════════════
IMPLEMENTATION DETAILS
═══════════════════════════════════════════════════════════════════════════════

1. WINDOW CALCULATION
   ───────────────────────────────────────────────────────────────────────────
   window_start = max(0, sentence_pos - window_size)
   window_end = min(section_sentence_count - 1, sentence_pos + window_size)
   
   Why this works:
   • max(0, ...) prevents negative positions
   • min(..., section_count-1) prevents exceeding section
   • Automatically handles all edge cases (first/last/tiny sections)

2. STAGE 2 META QUERY
   ───────────────────────────────────────────────────────────────────────────
   window_sentences = meta_df.filter(
       (pl.col('cik_int') == hit.cik_int) &
       (pl.col('report_year') == hit.report_year) &
       (pl.col('section_name') == hit.section_name) &
       (pl.col('sentence_pos') >= window_start) &
       (pl.col('sentence_pos') <= window_end)
   ).unique(subset=['sentenceID'], keep='first').sort('sentence_pos')
   
   Key decisions:
   • NO embedding_id filter (we want text regardless)
   • .unique() handles multi-embedding sentences (rare)
   • .sort() ensures proper sentence order

3. SENTENCE RECORD CREATION
   ───────────────────────────────────────────────────────────────────────────
   For each sentence in window:
       is_core = (row['sentenceID'] == hit.sentence_id)
       
       record = SentenceRecord(
           sentence_id=row['sentenceID'],
           text=row['sentence'],
           is_core_hit=is_core,  ← KEY MARKER
           parent_hit_distance=hit.distance,
           sources=hit.sources.copy(),
           variant_ids=hit.variant_ids.copy(),
           prev_sentence_id=row.get('prev_sentenceID'),  ← Populate for safety
           next_sentence_id=row.get('next_sentenceID'),  ← Even if not used
           section_sentence_count=row.get('section_sentence_count'),
           ...
       )

4. DEDUPLICATION LOGIC
   ───────────────────────────────────────────────────────────────────────────
   groups = defaultdict(list)
   for rec in records:
       key = (rec.sentence_id, rec.cik_int, rec.report_year, rec.section_name)
       groups[key].append(rec)
   
   for key, group in groups.items():
       best = min(group, key=lambda r: r.parent_hit_distance)
       
       # Aggregate provenance
       best.sources = set().union(*[r.sources for r in group])
       best.variant_ids = set().union(*[r.variant_ids for r in group])
       best.is_core_hit = any(r.is_core_hit for r in group)
       
       deduped.append(best)

5. ASSEMBLY GROUPING
   ───────────────────────────────────────────────────────────────────────────
   Why group by (company, year, section)?
   • Semantic boundaries (different context)
   • LLM citation quality (clear provenance)
   • Human readability (easy to scan)
   
   Why NOT group by docID?
   • Multiple docs from same company/year/section are coherent
   • Unnecessary fragmentation
   
   Why NOT group by contiguous positions?
   • Gaps in positions are fine for LLM (still coherent)
   • Creates artificial boundaries
   
   Minimal grouping = Better coherence

═══════════════════════════════════════════════════════════════════════════════
CONFIGURATION
═══════════════════════════════════════════════════════════════════════════════

From ml_config.yaml:

retrieval:
  window_size: 3  # ±N sentences around each hit
  
  # Note: NO max_context_blocks parameter
  # Assembly decides how many sentences to include based on token budget

═══════════════════════════════════════════════════════════════════════════════
FILE STRUCTURE
═══════════════════════════════════════════════════════════════════════════════

rag_pipeline/
├── models.py                    # SentenceRecord, ContextBlock dataclasses
├── metadata_filters.py          # Step 4: Build S3 filters
├── s3_retriever.py              # Step 5: S3 queries + Dedup #1
├── variant_pipeline.py          # Variant generation + embedding
├── context_builder.py           # Steps 6-7: Window expansion + Dedup #2
├── context_assembler.py         # Step 10: Sort + format for LLM
└── reranker.py                  # Empty placeholder (future)

DELETED:
├── hit_merger.py                # Logic in S3VectorsRetriever
├── deduplicator.py              # Dedup logic in retriever + builder
├── block_deduplicator.py        # Not needed (no block-level dedup)
├── context_window.py            # Merged into context_builder.py
└── text_fetcher.py              # Merged into context_builder.py

═══════════════════════════════════════════════════════════════════════════════
TESTING STRATEGY
═══════════════════════════════════════════════════════════════════════════════

Isolation Test for ContextBuilder:
    1. Create 3 synthetic S3Hits with overlapping windows
    2. Call build_sentences()
    3. Verify:
       ✓ Correct number of sentence records created
       ✓ Duplicates removed (sentence appears once)
       ✓ is_core_hit markers correct
       ✓ Provenance aggregated properly
       ✓ Best distance preserved

Integration Test (End-to-End):
    1. Real query → S3Retriever → ContextBuilder → Assembler
    2. Verify:
       ✓ LLM context is coherent
       ✓ Headers inserted at right boundaries
       ✓ No duplicate sentences in output
       ✓ Core hits present in context

═══════════════════════════════════════════════════════════════════════════════
FUTURE ENHANCEMENTS
═══════════════════════════════════════════════════════════════════════════════

Potential improvements (not for MVP):
    • Dynamic window sizing (larger for narrative sections)
    • Boilerplate filtering (remove "forward-looking statements")
    • Smart truncation (if over token limit, keep sentences with most core_hits)
    • Reranking (add back if S3 quality degrades)

═══════════════════════════════════════════════════════════════════════════════
═══════════════════════════════════════════════════════════════════════════════
"""

