# Embeddings & S3 Vectors — Next-Phase Revival Plan

**Written:** 2026-07-27 (end of the KPI/structured-half session)
**For:** the next agent (likely a smaller model in a fresh terminal after `/clear`)
**Status of this doc:** LIVING PLAN. Expect to revise it. Data-volume choices, cost
numbers, and file:line anchors below are grounded in a 2026-07-27 read-only
investigation — **verify anchors before editing code**, they drift as files change.

---

## 0. How to use this document

- The **structured/KPI half** of the hybrid RAG is DONE and LIVE as of this session
  (see §1). This plan covers only the **semantic/embedding half**: regenerate embeddings
  on the new AWS account, stand up a fresh S3 Vectors index, and validate retrieval.
- This is a **revival, not a build**. The RAG code already exists and is described as
  complete. The old AWS account was deleted, taking the S3 Vectors index and its
  ~203,076 vectors with it — they are **unrecoverable and must be regenerated**, not
  re-uploaded (`.claude/PROJECT_STATE.md`).
- Read in order: §1 (state) → §3 (the one real decision) → §4 (execution) → §5 (fixes
  to apply first). §6-§10 are operational detail, risks, checklist, rollback.
- **Do not trust file:line numbers blindly.** Re-grep the symbol before editing. Every
  reference below is tagged with the file so you can re-locate it.

---

## 1. Where things stand (ground truth, 2026-07-27)

| Artifact | State | Location | Notes |
|---|---|---|---|
| **Stage 1 sentence facts** | ✅ DONE | `DataPipeline/data_cache/stage1_facts/finrag_fact_sentences.parquet` | **614,787 rows, 25 companies, 2006-2025** (regenerated this session) |
| **KPI/metrics facts** | ✅ DONE & LIVE | S3 `DATA_MERGE_ASSETS/FINRAG_FACT_METRICS/KPI_FACT_DATA_EDGAR.parquet` + 2 local mirrors | 9,260 rows, 25 companies; pushed + verified byte-identical this session |
| **Stage 2 meta table** | ⚠️ STALE | `ModelPipeline/finrag_ml_tg1/data_cache/meta_embeds/finrag_fact_sentences_meta_embeds.parquet` | Dated **Jun 28** — built from the OLD 21-company/200k data. **Must regenerate from the new Stage 1.** |
| **Embedding vectors** | ❌ ABSENT | `.../data_cache/embeddings/` (empty) | Never regenerated after account deletion |
| **Stage 3 S3-Vectors staging** | ❌ ABSENT | `.../data_cache/stage3_s3vectors/` (empty) | Built by joining meta + vectors |
| **S3 Vectors index** | ❌ ABSENT | new account `mjsushanth_mlops` | Old index gone; **no code exists to create it — must be written** |
| **Retrieval path** | ✅ config-driven, ready | `rag_modules_src/rag_pipeline/s3_retriever.py` | Works once the index exists |

**Volume vs the past (the key sizing fact):** **614,787 sentences now ≈ 3.0× the ~203,076
vectors the old account held.** The prior ~$5 Bedrock estimate and the stale
`embedding_execution.filters` in config were sized for the old 21-company set — both must
be re-scoped (see §3).

---

## 2. The data model (what feeds what)

Three stages + a separate vectors table + the native index. Confirmed via
`platform_core/data_preparation.py`, `embedding_generation.py`,
`s3vectors_table_preparation.py`.

```
Stage 1  finrag_fact_sentences.parquet            (24 cols: cik, cik_int, sentenceID,
  |      614,787 rows  [DONE]                       section_name, sentence, report_year, sic, ...)
  v      platform_core/data_preparation.py :: _add_ml_columns()
Stage 2  finrag_fact_sentences_meta_embeds.parquet  ("META FACT TABLE": Stage1
  |      [STALE - regenerate]                        + prev/next_sentenceID neighbor pointers,
  |                                                   sentence_char_length, sentence_token_count,
  |                                                   section_sentence_count,
  |                                                   + 5 NULL embedding-metadata cols)
  |
  |  ---> embedding_generation.py :: EmbeddingGenerationPipeline
  |        Bedrock Cohere embed-v4:0, 1024-d, batch 96 texts / 128k tokens
  |        (skips sentences with token_count > 1000)
  v
Vectors  finrag_embeddings_cohere_1024d.parquet    (sentenceID, embedding_id,
  |      [ABSENT - generate]                          embedding: List[Float32]  -- NO cik/year here)
  v      s3vectors_table_preparation.py :: _build_stage3_table()
Stage 3  finrag_embeddings_s3vectors_cohere_1024d.parquet
  |      [ABSENT - build]   (join meta+vectors on sentenceID; adds mmh3 surrogate key;
  |                          FILTERABLE metadata: cik_int, report_year, section_name, sic,
  |                          sentence_pos ; NON-filterable: embedding_id, section_sentence_count)
  v      s3vectors_bulk_insertion.py :: put_vectors (<=500/batch, 20MiB cap)
S3 VECTORS INDEX (native AWS "s3vectors" service)  [MUST CREATE FIRST]
  ^      queried at runtime by rag_pipeline/s3_retriever.py (config-driven)
```

**Keying:** sentences ↔ vectors join purely on `sentenceID`. Company (`cik_int`) and
year (`report_year`) live only in the meta table and get attached to each vector at the
Stage-3 join. **The KPI/metrics table is a completely separate supply line** — it is
loaded by `rag_modules_src/metric_pipeline/` and string-concatenated with the semantic
results in `rag_pipeline/supply_lines.py :: build_combined_context()`; it never enters
the vector index. So this session's KPI work and this phase's embedding work don't
overlap at the data level.

---

## 3. THE decision to make first: embedding scope (years × companies)

You flagged this yourself: **how many years of data do we actually embed?** It drives
cost, wall-clock time, and index size. Here is the real distribution to decide against.

Sentences per `report_year` (all 25 companies):

| Years | Sentences | Cumulative | Character |
|---|---|---|---|
| 2006-2015 | ~163,674 | 163,674 | sparse (~14-18k/yr; fewer companies had filings) |
| 2016 | 43,338 | 207,012 | step-up (25-company dense coverage begins) |
| 2017-2025 | ~407,775 | 614,787 | dense (~44-49k/yr) |

Natural cut points:
- **Full 2006-2025** = **614,787** (≈3.0× the old set). Best for historical-trend queries.
- **2016-2025** = **451,113** (the dense-coverage era; drops the thin early years).
- **2020-2025** = ~280,700 (recent 6 years; strongest relevance for "current" questions).

Cost/time framing (confirm before committing — see §7):
- Prior estimate was ~$5 for ~203k vectors (`ml_config.yaml costs.embedding_budget_usd`).
  Cohere embed-v4 cost scales ~linearly with token volume, so **full 25-company/2006-2025
  is order ~$15**; 2016-2025 order ~$11; 2020-2025 order ~$7. **These are extrapolations —
  the next agent must confirm current Bedrock Cohere embed-v4 pricing and benchmark a
  small batch for wall-clock.**
- Storage is trivial either way (~$0.30/million vectors/month → cents; see `S3Vect_QueryCost.md`).

**Recommendation (not a decision):** the incremental cost of full history is small in
absolute dollars, and the KPI table already covers 2006-2025, so a full-history embed
keeps the two supply lines aligned. But if a fast, cheap first pass is wanted, 2016-2025
captures 73% of sentences and all the dense modern coverage. **Decide, then encode the
choice in `embedding_execution.filters` (see §5 P2) — do not leave the stale value.**

---

## 4. Execution pipeline (ordered, each step: input → output → code → gotchas)

> Run everything from within the conda env `finsight-venv`. For any S3/Bedrock step,
> load creds first (see §6). Nothing here should run before the §5 fixes are applied.

**Step A — Regenerate the Stage 2 meta table.**
- In: new Stage 1 (`finrag_fact_sentences.parquet`, 614,787 rows).
- Out: fresh `finrag_fact_sentences_meta_embeds.parquet` (overwrites the stale Jun 28 file).
- Code: `platform_core/data_preparation.py` (`_add_ml_columns`, `_initialize_vectors_table`).
- Gotcha: the current meta file predates the 25-company expansion. If you skip this, every
  downstream step embeds the wrong sentence set. Confirm the regenerated file has 614,787
  rows (or your chosen scope) and the neighbor-pointer + token-count columns populated.
- Gotcha: filter thresholds in `ml_config.yaml` (`min_char_length: 30, max_char_length:
  1000, max_token_count: 500, exclude_sections: [ITEM_15, ITEM_16]`) may be applied here in
  Stage 2 rather than in `embedding_generation.py` — confirm where filtering actually
  happens so your final vector count is predictable.

**Step B — Preflight the new account (do BEFORE spending money on embeddings).**
- Confirm the native **AWS S3 Vectors** service is enabled in `us-east-1` for account
  `mjsushanth_mlops` (908877262866). It is a newer service with possible account/region
  gating. `boto3.client("s3vectors")` must exist and `list_vector_buckets`/`create_index`
  must be authorized.
- Confirm **Bedrock model access** is granted for `cohere.embed-v4:0` and
  `us.anthropic.claude-haiku-4-5-20251001-v1:0` (Bedrock access is opt-in per account/region).

**Step C — Create the S3 Vectors bucket + index. ⚠️ CODE DOES NOT EXIST — write it.**
- No module in the repo creates the vector bucket or index; `create_vector_bucket`/
  `create_index` appear only in a notebook's *printed* list of available boto3 methods,
  not as runnable code. `s3vectors_bulk_insertion.py :: _validate_index_configuration()`
  *assumes the index already exists* and only validates it.
- Write a small idempotent creator (mirror the pattern of `src_metrics/push_to_s3.py`):
  create vector bucket `finrag-embeddings-s3vectors`, then index
  `finrag-sentence-fact-embed-1024d` with **dimension 1024, distance metric cosine**, and
  the **filterable metadata keys** `cik_int, report_year, section_name, sic, sentence_pos`
  (non-filterable: `embedding_id, section_sentence_count, sentenceID`). These names must
  match the Stage-3 schema (`s3vectors_table_preparation.py`) and the retriever config
  (`retrieval.*` in `ml_config.yaml`) exactly, or inserts/queries fail.

**Step D — Generate embeddings.**
- In: Stage 2 meta (chosen scope). Out: vectors table
  `finrag_embeddings_cohere_1024d.parquet`.
- Code: `platform_core/embedding_generation.py :: EmbeddingGenerationPipeline`.
- Gotcha: `embedding_id` string is hardcoded as `bedrock_cohere_v4_{dims}d_...`
  (`embedding_generation.py`) regardless of the config's selected model — fine while the
  model is Cohere v4, latent bug if ever switched to Titan.
- Gotcha: this is the only step that costs real money and time. Consider a dry run on one
  company first to validate the Bedrock path and measure per-batch latency, then scale.

**Step E — Build the Stage 3 staging table.**
- Code: `platform_core/s3vectors_table_preparation.py :: _build_stage3_table()`
  (lazy Polars join of meta + vectors on `sentenceID`, adds `mmh3.hash64` surrogate key).
- Out: `finrag_embeddings_s3vectors_cohere_1024d.parquet`. **This parquet is your
  regenerable source of truth for the index** — keep it in S3 so the index can be rebuilt
  without paying to re-embed (see §10).

**Step F — Bulk-insert into the S3 Vectors index.**
- Code: `platform_core/s3vectors_bulk_insertion.py` (`put_vectors`, ≤500/batch, 20MiB cap).
- **Apply §5 P1 first** (the bucket/index names are hardcoded here, bypassing config).

**Step G — Validate retrieval end-to-end.**
- Code: `rag_modules_src/rag_pipeline/s3_retriever.py` (config-driven from `retrieval.*`).
- Run a few known queries; confirm vectors come back with correct `cik_int`/`report_year`
  metadata and that filtered search (by company/year) works.

**Step H — Persist to cloud (source-of-truth pattern).**
- Upload the vectors table + Stage-3 staging parquet to S3 under `ML_EMBED_ASSETS/...`
  (paths already defined in `ml_config.yaml data_ml.*`), then sync local mirrors — same
  "S3 first, then mirror" pattern this session used for the KPI table
  (`src_metrics/push_to_s3.py`, `DataPipeline/CLOUD_SOURCE_OF_TRUTH.md`).

---

## 5. Fixes to apply before/within the run (prioritized swap points)

*(file:line per 2026-07-27 investigation — re-grep before editing.)*

- **P1 — `platform_core/s3vectors_bulk_insertion.py` ~L198-199:** `vector_bucket` and
  `index_name` are **hardcoded string literals** (`"finrag-embeddings-s3vectors"`,
  `"finrag-sentence-fact-embed-1024d"`) despite a comment claiming they come from
  `MLConfig`. They currently match `ml_config.yaml retrieval.*` by coincidence. Make them
  read `MLConfig().get_retrieval_config()` so the ingestion script and the query-time
  retriever can never silently diverge. **Highest priority — this is the script that runs
  at ingest.**
- **P2 — `ml_config.yaml` ~L172-173 `embedding_execution.filters`:** stale leftover from
  the old account (21 CIKs, years 2006-2011 only). **Reset to your §3 scope decision**
  before running Step D, or you will embed the wrong subset.
- **P3 — Index-creation code (MISSING):** write it (Step C). This is the single biggest
  code gap for the revival.
- **P4 — `ml_config.yaml` ~L250-297 legacy `rag_orchestrator.*` block:** dead/superseded
  (`s3_vectors.index_name: finrag-embeddings`, `llm.model_id: claude-3-5-sonnet-...`).
  Nothing reads it; the live keys are `retrieval.*` and `serving_models.*`. Delete it or
  mark `# DEAD - superseded by retrieval.*/serving_models.*` so nobody edits the wrong key.
- **P5 — `rag_modules_src/metric_pipeline/main.py` ~L47-48, L80-81:** a standalone smoke
  test that points at a *separate stale* KPI copy
  (`metric_pipeline/data/KPI_FACT_DATA_EDGAR.parquet`) and overrides loader attributes that
  `LocalCacheLoader.load_kpi_fact_data()` never reads (dead pattern). Harmless (not in the
  composition root) but confusing — fix or delete if you touch it. Note: the live loader
  reads `data_cache/metrics_fact/KPI_FACT_DATA_EDGAR.parquet`, which this session updated.
- **Tiny (doc/comment drift, no functional risk):** `loaders/ml_config_loader.py` ~L633
  docstring still says `finrag_dim_companies_21`; `loaders/data_loader_strategy.py` ~L200
  commented-out `_21` S3 key; `ARCHITECTURE.md` ~L142 names the Stage-3 file
  `finrag_s3vectors_cohere_1024d.parquet` vs config's
  `finrag_embeddings_s3vectors_cohere_1024d.parquet`. Clean up opportunistically.
- **Do NOT touch:** `platform_core/s3_vectors_table_prep_eagerload_v1.py` — explicitly
  marked outdated/reference-only.

---

## 6. Operational notes (the non-obvious stuff discovered this session)

- **AWS creds:** `DataPipeline/src_aws_etl/.aws_secrets/aws_credentials.env` is **BLANK**
  (key names, empty values) and there is no root `.env` — so `ETLConfig`/`MLConfig` cred
  loading fails out of the box. There **is** a working CLI profile `mjsushanth_mlops`. Load
  it into the process env before any S3/Bedrock script:
  ```
  eval "$(aws configure export-credentials --profile mjsushanth_mlops --format env)"
  ```
  `ETLConfig` checks `os.environ` first, so this satisfies it without writing secrets to
  disk. (This is exactly how the KPI push ran this session.)
- **Env:** conda `finsight-venv` (has `edgar`, `polars`, `pandas`, `boto3`). Python at
  `/opt/homebrew/Caskroom/miniconda/base/envs/finsight-venv/bin/python`.
- **Bucket/region:** `sentence-data-ingestion-mjs`, `us-east-1` (from `ml_config.yaml s3`).
- `EDGAR_IDENTITY` env var is only needed for edgartools re-runs (KPI/sentence side), not
  for the embedding phase.

---

## 7. Verification / investigation tasks for the next agent

1. Confirm S3 Vectors service is enabled + authorized on the new account/region (Step B).
2. Confirm Bedrock access for `cohere.embed-v4:0` and the Haiku 4.5 serving model.
3. Confirm current Bedrock Cohere embed-v4 **pricing**; benchmark one company's embed to
   get real per-1k-sentence wall-clock + cost; extrapolate to the §3 scope. Replace the
   ~$15 guess with a measured number.
4. Confirm Step A regenerated the meta table from the **new** Stage 1 (614,787 rows / your
   scope), not the stale Jun 28 file.
5. After Step F: assert `vectors inserted == Stage-3 row count`; run sanity queries via the
   retriever including a company+year filtered search.

---

## 8. Risks & open questions

- **S3 Vectors is a newer AWS service** — regional/account gating is the top schedule risk.
  Resolve Step B before planning timelines.
- **No embedding-stage latency/cost documentation exists** — `PIPELINE_LATENCY_ANALYSIS.md`
  and `S3Vect_QueryCost.md` cover *query* time only. You are creating this datapoint.
- **Config/code coupling on names:** the vector bucket, index name, dimension (1024),
  distance metric (cosine), and metadata key names must agree across four places — index
  creation (new code), `s3vectors_bulk_insertion.py`, `s3vectors_table_preparation.py`
  schema, and `ml_config.yaml retrieval.*`. A single mismatch breaks insert or query.
- **Meta-table filter placement** (`ml_config.yaml` L204-208) — verify whether the
  char/token/section filters run in Stage 2 or in `embedding_generation.py`, so the final
  vector count is predictable and matches your scope decision.
- **Stale artifacts on disk** can mislead: the Jun 28 meta_embeds file and any cached
  notebook outputs referencing the old bucket `sentence-data-ingestion` (no `-mjs`).

---

## 9. Suggested execution order (checklist)

- [ ] Decide embedding scope (§3) and set `embedding_execution.filters` (P2)
- [ ] Preflight: S3 Vectors enabled + Bedrock model access (Step B)
- [ ] Apply P1 (config-drive the bulk-insert bucket/index) and P4 (dead config)
- [ ] Regenerate Stage 2 meta table from new Stage 1 (Step A); verify row count
- [ ] Write + run index creation (Step C / P3)
- [ ] Dry-run embeddings on 1 company; measure cost/latency (Step D partial, §7.3)
- [ ] Full embedding generation at chosen scope (Step D)
- [ ] Build Stage 3 staging table (Step E)
- [ ] Bulk insert into index (Step F); assert count parity
- [ ] Validate retrieval end-to-end, incl. filtered search (Step G)
- [ ] Push vectors + Stage-3 parquet to S3, sync mirrors (Step H)
- [ ] Update `ARCHITECTURE.md` / `PROJECT_STATE.md` with the new counts + this phase's outcome

---

## 10. Rollback / safety

- The **Stage-3 staging parquet is the cheap-rebuild source of truth**: re-embedding costs
  money, but re-inserting from the Stage-3 parquet into a fresh index is free. Persist it to
  S3 (Step H) so a broken index can be rebuilt without touching Bedrock.
- Keep the vectors table parquet too — Stage 3 can be rejoined from meta + vectors if the
  staging file is lost.
- The KPI/structured half is independent and already archived (S3 `.../ARCHIVE/`); nothing
  in this phase touches it.

---

*Companion context: `.claude/PROJECT_STATE.md` (revival roadmap), `ARCHITECTURE.md`
(directory map + stage sizes), `finrag_ml_tg1/CLAUDE.md` (ML rules/state),
`DataPipeline/analytics/REVIEW_1.1_senior_findings_2026-07-27.md` (this session's KPI fixes),
`DataPipeline/CLOUD_SOURCE_OF_TRUTH.md` (S3-first sync pattern). Anchors here reflect the
2026-07-27 state — re-verify against the live tree.*
