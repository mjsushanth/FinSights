# S3 Vectors — Revival Plan (post-embedding phase)

**Written:** 2026-07-27, trimmed 2026-07-28 to remove completed/decided material.
**Status:** Steps B and C below are **done** (S3 Vectors confirmed enabled, bucket + index
created and verified). Everything from Step E onward — Stage 3 build, bulk insert, retrieval
validation — is **deliberately not started**: explicit decision to finish all three embedding
bins first (see `EMBEDDING_PROGRESS_LOG.md` §8 for why). For embedding generation's current
status and blockers, see `EMBEDDING_PROGRESS_LOG.md` in this same directory — read that first
if you're resuming fresh.

---

## 1. The data model (what feeds what)

Three stages + a separate vectors table + the native index. Confirmed via
`platform_core/data_preparation.py`, `embedding_generation.py`, `s3vectors_table_preparation.py`.

```
Stage 1  finrag_fact_sentences.parquet            [DONE — 614,787 rows]
  v      platform_core/data_preparation.py :: _add_ml_columns()
Stage 2  finrag_fact_sentences_meta_embeds.parquet  [DONE — regenerated, 614,787 rows]
  |
  |  ---> embedding_generation.py :: EmbeddingGenerationPipeline
  |        Bedrock Cohere embed-v4:0, 1024-d, batch 96 texts / 128k tokens
  v
Vectors  finrag_embeddings_cohere_1024d.parquet    [IN PROGRESS — see progress log]
  |      (sentenceID, embedding_id, embedding: List[Float32] -- NO cik/year here)
  v      s3vectors_table_preparation.py :: _build_stage3_table()
Stage 3  finrag_embeddings_s3vectors_cohere_1024d.parquet
  |      [NOT STARTED]   (join meta+vectors on sentenceID; adds mmh3 surrogate key;
  |                        FILTERABLE metadata: cik_int, report_year, section_name, sic,
  |                        sentence_pos ; NON-filterable: embedding_id, section_sentence_count)
  v      s3vectors_bulk_insertion.py :: put_vectors (<=500/batch, 20MiB cap)
S3 VECTORS INDEX (native AWS "s3vectors" service)  [NOT STARTED -- code to create it is MISSING]
  ^      queried at runtime by rag_pipeline/s3_retriever.py (config-driven, already works
         once the index exists)
```

**Keying:** sentences ↔ vectors join purely on `sentenceID`. Company (`cik_int`) and year
(`report_year`) live only in the meta table and get attached to each vector at the Stage-3 join.
**The KPI/metrics table is a completely separate supply line** — loaded independently and
string-concatenated in `rag_pipeline/supply_lines.py :: build_combined_context()`; it never
enters the vector index, so none of this phase touches it.

---

## 2. Execution steps, in order

Do not start any of this until all three embedding bins are done and verified (see progress log).

**Step B — Preflight the new account. ✅ DONE (2026-07-28).**
- Confirmed: native **AWS S3 Vectors** service is enabled/authorized in `us-east-1` for account
  `mjsushanth_mlops` (908877262866). `boto3.client('s3vectors').list_vector_buckets()` succeeds
  (returned empty list before Step C ran — clean account, no leftovers from the old deleted
  account). This was the top schedule risk for this phase and it's resolved.
- Bedrock model access for the LLM synthesis path was already implicitly confirmed by the
  working embedding/RAG code elsewhere in this project; not re-tested here.

**Step C — Create the S3 Vectors bucket + index. ✅ DONE (2026-07-28), P3 resolved.**
- Wrote `platform_core/s3vectors_index_creation.py` — idempotent creator (exists-check /
  optional force-recreate, mirrors `data_preparation.py`'s `_initialize_meta_table()` pattern).
  Reads bucket/index name and dimension from `MLConfig().get_retrieval_config()`, never
  hardcoded, so it can't silently diverge from `s3vectors_bulk_insertion.py` or the retriever
  (the exact P1 bug already found elsewhere).
- **Created and verified, real AWS resources:**
  - Vector bucket: `finrag-embeddings-s3vectors`
  - Index: `finrag-sentence-fact-embed-1024d` — `dataType=float32`, `dimension=1024`,
    `distanceMetric=cosine`
  - Non-filterable metadata: `embedding_id`, `section_sentence_count`, `sentenceID` (declared at
    creation, can never be converted to filterable later — get this right before any real
    insert). Everything else (`cik_int`, `report_year`, `section_name`, `sic`, `sentence_pos`)
    is filterable by default.
  - Confirmed via `get_index` (ARN:
    `arn:aws:s3vectors:us-east-1:908877262866:bucket/finrag-embeddings-s3vectors/index/finrag-sentence-fact-embed-1024d`)
    and re-running the script a second time (correctly reported "already exists" both times,
    no duplication).
- **Deliberately not done yet:** no vectors have been inserted into this index. The bucket and
  index existing does not require Stage 3 to exist yet — see the note below on why that's
  still an open decision, not a blocker.

**Step E — Build the Stage 3 staging table.**
- Code: `platform_core/s3vectors_table_preparation.py :: _build_stage3_table()` (lazy Polars
  join of meta + vectors on `sentenceID`, adds `mmh3.hash64` surrogate key).
- Out: `finrag_embeddings_s3vectors_cohere_1024d.parquet`. **This parquet is your regenerable
  source of truth for the index** — keep it in S3 so the index can be rebuilt without paying to
  re-embed (see §5).

**Step F — Bulk-insert into the S3 Vectors index.**
- Code: `platform_core/s3vectors_bulk_insertion.py` (`put_vectors`, ≤500/batch, 20MiB cap,
  already has working exponential-backoff retry for `TooManyRequestsException` — confirmed
  correct for this service via botocore's real service model, no fix needed here).
- **Apply fix P1 below first** — the bucket/index names are hardcoded in this file, bypassing
  config.

**Step G — Validate retrieval end-to-end.**
- Code: `rag_modules_src/rag_pipeline/s3_retriever.py` (config-driven from `retrieval.*`,
  already implemented, no changes expected).
- Run a few known queries; confirm vectors come back with correct `cik_int`/`report_year`
  metadata and that filtered search (by company/year) works.

**Step H — Persist to cloud.**
- Upload the vectors table + Stage-3 staging parquet to S3 under `ML_EMBED_ASSETS/...` (paths
  already defined in `ml_config.yaml data_ml.*`), then sync local mirrors — same "S3 first,
  then mirror" pattern used throughout this project (see `DataPipeline/CLOUD_SOURCE_OF_TRUTH.md`).

---

## 3. Fixes to apply (none of these have been touched yet)

- **P1 — `platform_core/s3vectors_bulk_insertion.py` ~L198-199:** `vector_bucket` and
  `index_name` are **hardcoded string literals** despite a comment claiming they come from
  `MLConfig`. They currently match `ml_config.yaml retrieval.*` by coincidence. Make them read
  `MLConfig().get_retrieval_config()` so the ingestion script and the query-time retriever can
  never silently diverge. **Highest priority — this is the script that runs at ingest.**
- **P3 — Index-creation code — ✅ DONE.** `platform_core/s3vectors_index_creation.py` written,
  run, and verified (see Step C above). Was the single biggest code gap for this phase.
- **P4 — `ml_config.yaml` ~L250-297 legacy `rag_orchestrator.*` block:** dead/superseded
  (`s3_vectors.index_name: finrag-embeddings`, `llm.model_id: claude-3-5-sonnet-...`). Nothing
  reads it; live keys are `retrieval.*` and `serving_models.*`. Delete it or mark
  `# DEAD - superseded by retrieval.*/serving_models.*`.
- **P5 — `rag_modules_src/metric_pipeline/main.py` ~L47-48, L80-81:** a standalone smoke test
  pointing at a *separate stale* KPI copy and overriding loader attributes that
  `LocalCacheLoader.load_kpi_fact_data()` never reads. Harmless (not in the composition root)
  but confusing — fix or delete if you touch it.
- **Do NOT touch:** `platform_core/s3_vectors_table_prep_eagerload_v1.py` — explicitly marked
  outdated/reference-only.

---

## 4. Risks & open questions

- **S3 Vectors is a newer AWS service** — regional/account gating is the top schedule risk.
  Resolve Step B before planning timelines for anything downstream.
- **Config/code coupling on names** — vector bucket, index name, dimension (1024), distance
  metric (cosine), and metadata key names must agree across four places: index creation (new
  code), `s3vectors_bulk_insertion.py`, `s3vectors_table_preparation.py` schema, and
  `ml_config.yaml retrieval.*`. A single mismatch breaks insert or query.
- **No embedding-stage latency/cost documentation existed before this session** —
  `PIPELINE_LATENCY_ANALYSIS.md` and `S3Vect_QueryCost.md` cover *query* time only; real
  embedding-stage cost/latency numbers now exist in `EMBEDDING_PROGRESS_LOG.md`, but nothing
  equivalent exists yet for the S3 Vectors ingest/query stage this doc covers.

---

## 5. Rollback / safety

- The **Stage-3 staging parquet is the cheap-rebuild source of truth**: re-embedding costs
  money, but re-inserting from the Stage-3 parquet into a fresh index is free. Persist it to S3
  (Step H) so a broken index can be rebuilt without touching Bedrock again.
- Keep the vectors table parquet too — Stage 3 can be rejoined from meta + vectors if the
  staging file is lost.
- The KPI/structured half is independent and already archived (S3 `.../ARCHIVE/`); nothing in
  this phase touches it.

---

*Companion docs: `EMBEDDING_PROGRESS_LOG.md` (embedding generation status, blockers, what's been
built), `.claude/PROJECT_STATE.md` (overall revival roadmap), `ARCHITECTURE.md` (directory map),
`finrag_ml_tg1/CLAUDE.md` (ML rules/state), `DataPipeline/CLOUD_SOURCE_OF_TRUTH.md` (S3-first
sync pattern). Re-verify file:line anchors before editing — they drift.*
