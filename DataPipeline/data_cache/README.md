# DataPipeline/data_cache

Local data assets for the DataPipeline (ETL) side, organized the same way
ModelPipeline/finrag_ml_tg1/data_cache/ is: one subfolder per data category.
Consolidated 2026-07-26 from two previously-scattered locations
(`data_engineering_research/duckdb_data_engineering/necessary_import_tables/`
and a local-only `OD_MS_DataBackups_Bulk/` folder, now removed) - moved, not
copied, to avoid duplicating a ~1.7GB set of files.

## dimensions/
Company and section dimension tables produced by the DuckDB engineering work.
Four company-tier files at increasing size: `finrag_dim_companies_21` (the
actual curated tier used to build the production RAG dataset -
`ModelPipeline/finrag_ml_tg1/data_cache/stage1_facts/finrag_fact_sentences.parquet`
uses exactly these 21 CIKs), `_75`, `_150`, `_540` (broader candidate pools,
not the final selection). Plus `finrag_dim_sec_sections` (SEC 10-K section
taxonomy) and `finrag_dim_sp500_holdings` (~500 S&P 500 constituents).
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

## What is NOT here
The actual production RAG dataset (`finrag_fact_sentences.parquet`, 469,252
rows, 21 companies, 2006-2025) lives in
`ModelPipeline/finrag_ml_tg1/data_cache/stage1_facts/` - it's the ETL output
of `src_aws_etl/etl/merge_pipeline.py`, not a static asset cached here.
