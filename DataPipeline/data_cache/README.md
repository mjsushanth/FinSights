# DataPipeline/data_cache

Local data assets for the DataPipeline (ETL) side, organized the same way
ModelPipeline/finrag_ml_tg1/data_cache/ is: one subfolder per data category.
Consolidated 2026-07-26 from two previously-scattered locations
(`data_engineering_research/duckdb_data_engineering/necessary_import_tables/`
and a local-only `OD_MS_DataBackups_Bulk/` folder, now removed) - moved, not
copied, to avoid duplicating a ~1.7GB set of files.

## dimensions/
Company and section dimension tables produced by the DuckDB engineering work.
Company-tier files at increasing size: `finrag_dim_companies_21` (the
original curated tier), `finrag_dim_companies_25` (2026-07-27 - the 21 plus
four gap-fill additions: UnitedHealth Group, Northrop Grumman, Caterpillar,
T-Mobile US, chosen via a sector-gap analysis against the full corpus - see
`src_edgar_incremental/PLAN.md` and the company-research findings referenced
there; **this is the tier the current production fact table actually uses**),
`_75`, `_150`, `_540` (broader candidate pools, not a final selection).
Plus `finrag_dim_sec_sections` (SEC 10-K section taxonomy - also the
ground-truth `section_ID`/`section_name` mapping the edgartools pipeline
uses) and `finrag_dim_sp500_holdings` (~500 S&P 500 constituents).
All small, all git-tracked.

## full_corpus/
The full raw universe before any company-tier curation:
`sec_filings_large_full.parquet` - 71,866,962 sentences, 4,674 distinct
companies, years 1993-2020. 1.5GB - gitignored, local only.
Note: the 21-company tier is missing exactly one company from this corpus -
Alphabet/GOOGL (CIK 1652044) - which is why `sec_10k_static_alphabet...`
exists separately under samples/ (see below).

## samples/
- `sec_filings_small_full.parquet` - an early, arbitrary 200K-row sample
  (first 10 CIKs numerically) taken from the full corpus. NOT the same as
  the curated 21-company production dataset - zero CIK overlap with it.
  Small, git-tracked.
- `sec_finrag_1M_sample.parquet` / `sec_finrag_1M_sample_filtered.parquet` -
  stratified samples built from the 75-company tier (1,003,534 / 564,551
  rows, years 2006-2020). Large - gitignored, local only.
- `sec_10k_static_alphabet_2017_20_api_data.parquet` - a targeted, separately
  API-pulled patch for Alphabet/GOOGL specifically (13,629 rows, 2016-2023,
  8 distinct years) - fills the one gap in the 21-company tier noted above.
  Small, git-tracked.

## reference/
`sec_company_tickers.json` - SEC ticker/CIK lookup reference data.
Gitignored, local only (matches its prior untracked state).

## stage1_facts/ (added 2026-07-27)
`finrag_fact_sentences.parquet` - **the canonical production RAG dataset**,
now generated here (previously only lived under
`ModelPipeline/finrag_ml_tg1/data_cache/stage1_facts/`, which is kept as a
synced copy for the RAG runtime to read - see that folder's own notes).
614,787 rows (614,910 originally, then 123 exact-duplicate rows removed -
see `analytics/duplicate_sentence_analysis.md`), 25 companies, report_years
2006-2025, produced by `src_aws_etl/etl/merge_pipeline.py` (the real merge/
dedupe logic - reused, not reimplemented) merging the prior 21-company/
469,252-row table against two `src_edgar_incremental` batches: FY2025 for
the original 20 non-Google companies + a full rebuilt history for
Alphabet, then a full 2006-2025 history for the four new companies.
Gitignored - regenerate via `src_edgar_incremental/run_pipeline.py` +
`run_dev_merges.py`, or restore from the S3 backup noted below, rather
than hand-editing.

## metrics_fact/ (added 2026-07-27)
`KPI_FACT_DATA_EDGAR.parquet` - the structured/numeric half of the hybrid
RAG (raw GAAP XBRL facts + 10 derived ratios per company-year). 9,071 rows,
25 companies. Produced by `src_metrics/pipeline.py`'s `MetricsPipeline`,
pushed to S3 first (`DATA_MERGE_ASSETS/FINRAG_FACT_METRICS/`, the path
`ModelPipeline/finrag_ml_tg1/.aws_config/ml_config.yaml` already expects),
then synced here and to `ModelPipeline/finrag_ml_tg1/data_cache/metrics_fact/`
automatically as the pipeline's last step (`push_to_s3.py`) - same cloud-
source-of-truth pattern as `stage1_facts/`. Gitignored - regenerate via
`src_metrics/run_pipeline.py`, don't hand-edit. Built in two passes: a full
2006-2025 history fetch for the 4 newly-added companies (with a real
domain review of their statement terminology - see
`analytics/03_kpi_domain_review_new_companies.ipynb`), then a standard
incremental (last-2-years) refresh for the original 21.

## incremental_batches/ (added 2026-07-27)
The two incremental inputs consumed by the merge above, kept here for
traceability of what went into the current fact table (not needed to
regenerate it - `src_edgar_incremental/manifests/` holds the finer-grained
per-run outputs if that's ever needed). Also uploaded to
`s3://sentence-data-ingestion-mjs/DEV_INCREMENTAL_BATCHES/2026-07-27_edgartools_expansion/`.
Gitignored (small but purely intermediate - the merged fact table above is
the artifact that matters going forward).
- `incremental_batch_A_fy2025_20co_plus_google_fullhist.parquet` - 52,124 rows
- `incremental_batch_B_new4companies_fullhist.parquet` - 118,283 rows

## Backups
A pre-rebuild copy of the original 469,252-row/21-company fact table lives at
`s3://sentence-data-ingestion-mjs/PREDEV_BACKUPS/edgartools_rebuild_2026-07-27/`
- a development-stage backup (not a real ETL archive run). The real ETL
archive path (`DATA_MERGE_ASSETS/ARCHIVE_DATA/`, managed by
`src_aws_etl/etl/preflight_check.py`) now also holds its own timestamped
copies from the two merges performed via `merge_pipeline.py`.
