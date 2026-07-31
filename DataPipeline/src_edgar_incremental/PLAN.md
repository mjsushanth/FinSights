# src_edgar_incremental — implementation plan

**Status: Stages 1-5 + orchestrator IMPLEMENTED and validated end-to-end**
against a real experimental round (Apple/Amazon/Exxon/Tesla FY2025, 5,043
sentences, 0 schema/dtype mismatches against the real production parquet -
see the session report for full results). Not yet run at the full 16-company
scope - awaiting go-ahead. This
document is the result of researching edgartools (see
`EDGARTOOLS_REFERENCE.md`) plus real experiments against SEC EDGAR, and
studying the existing codebase (`src_legacy_bs4_scraper/`, `src_aws_etl/`,
the real production schema). It is meant to be reviewed and adjusted before
any code is written.

## Why this exists
`src_legacy_bs4_scraper/` (the old `src/`) works but is a hand-rolled
BeautifulSoup + `sec-edgar-downloader` pipeline with real problems (hardcoded
personal path/email, duplicated S3 logic, no tests - see the earlier
code-quality report). `edgartools` already solves fetching, section
detection, and item-boundary edge cases more robustly than the hand-rolled
version, and it's already a proven dependency here (`src_metrics` uses it
successfully). Goal: a clean, incremental EDGAR-sentence fetcher built on
edgartools that can (a) backfill the 2006-2011 gap left unembedded when the
old AWS account was deleted, and (b) fetch new years going forward, in the
exact schema the RAG pipeline already expects.

## Target schema (from the real production file, verified by direct read of
`ModelPipeline/finrag_ml_tg1/data_cache/stage1_facts/finrag_fact_sentences.parquet`)

| Column | Type | Derivation plan |
|---|---|---|
| `cik` | str, zero-padded 10 digits | `f"{cik_int:010d}"` |
| `cik_int` | int | `Company.cik` |
| `name` | str | `Company.name` |
| `tickers` | list[str] | `Company.tickers` |
| `docID` | str | `f"{cik}_{form}_{report_year}"` (exact old convention, e.g. `0000320193_10-K_2021`) |
| `sentenceID` | str | **CONFIRMED exact old convention.** `f"{docID}_section_{item_token}_{s_idx}"` where `item_token` = `sec_item_canonical` with the `ITEM_` prefix stripped (e.g. `ITEM_1A` -> `1A`, `ITEM_10` -> `10`) - verified live: `0000034088_10-K_2006_section_1A_10` |
| `section_ID` | int | **RESOLVED, ground-truth confirmed.** Exact join key exists: `DataPipeline/data_cache/dimensions/finrag_dim_sec_sections.parquet`, column `hf_section_code` (0-19; `ITEM_16` is the one row with `hf_section_code=null` and never appears in the real fact table - 20 distinct section_IDs observed, 0-19, matches exactly). Look up by `sec_item_canonical` (e.g. `ITEM_1A`). Do NOT invent a new ordinal - this dimension table already IS the documented, internally-consistent mapping. |
| `section_name` | str | `sec_item_canonical` verbatim from the same dimension table row (e.g. `ITEM_1A`, `ITEM_10`) - confirmed exact match against real fact table values, not the long `section_name` description column in the dim table (that column is a different, human-readable field despite the confusing name collision) |
| `form` | str | `Filing.form`, filtered to exactly `"10-K"` via `amendments=False` (Gotcha 2) - confirmed the real fact table has ONLY the literal value `"10-K"`, zero `"10-K/A"` rows |
| `sic` | str | `Company.sic` as-is (confirmed 4-digit numeric string, e.g. `"7372"`, no padding/transform) |
| `sentence` | str | one row per sentence, after cleaning (see Stage 3) |
| `filingDate` | **str**, `YYYY-MM-DD` | **CORRECTED** - confirmed the real column is a plain date string, NOT a datetime, e.g. `"2019-02-27"`. `str(Filing.filing_date)` |
| `report_year` | int | **RESOLVED.** `Filing.report_date.year` - confirmed against real data (e.g. Apple FY ending 2006-09-30, filed 2006-12-29, `report_year=2006` matches `reportDate.year`, not `filingDate.year`). This also answers the "2026 files last year's 10-K" nuance: report_year always tracks the fiscal-period-end year, never the filing year. |
| `reportDate` | **str**, `YYYY-MM-DD` | **CORRECTED**, same as `filingDate` - plain date string, e.g. `"2006-09-30"` |
| `temporal_bin` | str | reuse exact old buckets (`bin_2006_2009`, `bin_2010_2015`, `bin_2016_2020`, `bin_2021_2025`, `bin_unknown`) from `src_legacy_bs4_scraper/extract_and_convert.py:89` |
| `likely_kpi` | bool | **RESOLVED - keep it simple, final.** Real regex logic (Stage 4), but explicitly scoped down per user direction: only ever produce True/False, never used to derive or drag out new fields, and this logic will not be extended later. A basic two-condition heuristic is good enough - do not over-build it. Old ETL path only ever wrote `None` (204,324 null rows confirmed live, all from the `extract_and_convert`/`v2.1_combined_extraction` batch) |
| `has_numbers` | bool | same as above - basic regex, final form, not a stepping stone to anything fancier |
| `has_comparison` | bool | same as above |
| `sample_created_at` | datetime (UTC) | pipeline run timestamp |
| `last_modified_date` | datetime (UTC) | same as above for a fresh row |
| `sample_version` | str | new tag, next in the existing sequence. Real values observed: `v1.0_75companies_1M`, `v2.1_combined_extraction` -> use `v2.2_edgartools_incremental` |
| `source_file_path` | str | `Filing.filing_url` (real, public, stable SEC.gov URL). **Confirmed this fixes a real, live anti-pattern**: existing rows literally contain `D:/JoelDesktop folds_24/NEU FALL2025/.../sec_filings_large_full.parquet` - a dead Windows path from the original author's laptop, baked into 204K+ production rows already. Not perpetuating that. |
| `load_method` | str | new tag, distinct from existing 3 values (`extract_and_convert`, `incremental_inject`, `stratified_sampling`) -> `"edgartools_incremental"` |
| `row_hash` | str (32-char hex) | `MD5(sentenceID + sentence)` - exact same formula as `src_aws_etl/etl/merge_pipeline.py` |

## Pipeline stages

```
Stage 1: fetch_filings.py
  Input:  list of (cik, year) pairs to fetch - default target set is the 16
          of 21 curated companies not yet at FY2025 (see resolved backfill
          scope below); parameterized so it also works for J&J's 5 sampling-
          gap years or any future incremental year set
  Output: local cache of Filing objects' raw metadata (accession_no, form,
          filing_date, report_date, filing_url) per (cik, year) - a small
          manifest parquet/json, NOT the full text yet (keeps this stage fast
          and re-runnable/idempotent without re-parsing HTML every retry)
  Uses:   Company(cik).get_filings(form="10-K", amendments=False)
                        .filter(filing_date=f"{year}-01-01:{year}-12-31")

Stage 2: extract_sections.py
  Input:  the manifest from Stage 1
  Output: one row per (docID, item) with raw section text - an intermediate
          "sections" parquet (docID, item_token, item_title, raw_text)
  Uses:   filing.obj() -> tenk.items / tenk.sections[key].text()
  Sanity: log + skip (not crash) filings where tenk.sections is empty or a
          given expected item is missing (Gotcha 2) - record a per-filing
          coverage count so gaps are visible, not silent

Stage 3: clean_and_split.py
  Input:  the "sections" intermediate parquet
  Output: one row per sentence - matches target schema's grain
  Steps:  1. normalize_item_periods() (reuse verbatim from
             src_legacy_bs4_scraper/extract_and_convert.py:85)
          2. strip page-footer boilerplate (Gotcha 3) - regex for the
             observed pattern (`r'{Company}\s*\|\s*\d{{4}}\s*Form\s*10-K\s*\|\s*\d+'`
             or a more general "short all-caps/pipe-delimited line" heuristic
             - needs testing against a few more companies before finalizing,
             since the exact footer format may vary by filer/filing agent)
          3. sentence-split (lightweight regex splitter, verified working in
             experiments - no nltk needed)
          4. filter degenerate "sentences" (e.g. bare item headers left over,
             very short fragments below a min-token threshold)
          5. assign sentenceID (sequential index within docID+item)

Stage 4: derive_features.py
  Input:  cleaned sentence rows
  Output: rows with has_numbers/has_comparison/likely_kpi populated
  Proposed heuristics (simple, auditable regex - not ML, matching the
  project's existing "practical over clever" preference):
    has_numbers    = contains a digit (r'\d')
    has_comparison = contains a comparison term (increase(d)/decrease(d)/
                      compared to/versus/higher/lower/grew/declined/etc.)
    likely_kpi     = has_numbers AND contains a financial-metric keyword
                      (revenue/margin/EBITDA/net income/EPS/cash flow/%/
                      growth/etc.) - a simple two-condition AND, easy to
                      unit test and to tune later against the real KPI list
                      already used in src_metrics/gaap_aliases.py (reuse
                      those canonical metric names as the keyword seed list
                      instead of inventing a new one)

Stage 5: assemble_and_validate.py
  Input:  fully-featured sentence rows
  Output: a Stage-1-schema-compatible parquet, ready to be merged by the
          EXISTING src_aws_etl/etl/merge_pipeline.py as the "incremental"
          input (reuse that pipeline rather than writing a second merge
          path - this new code's job stops at producing a clean,
          schema-correct incremental file)
  Sanity checks (field + data thoroughness, run before Stage 5 hands off):
    - sentenceID uniqueness (no collisions within this batch)
    - no null cik_int/docID/sentenceID/sentence
    - report_year within the expected backfill/target range
    - cik_int is one of the 21 curated companies (dim_companies_21.parquet)
    - row_hash recomputed and matches (integrity self-check)
    - per-(cik,year) sentence-count sanity range (flag outliers - e.g. a
      filing that produced 0 or suspiciously few sentences likely means a
      section-detection failure, not a genuinely short filing)
    - schema/dtype match against the real production parquet's schema
      (column names, order, and polars dtypes) via a direct
      `pl.scan_parquet(...).collect_schema()` comparison in a test
```

## Decisions - RESOLVED (verified against real data this session)

1. **`section_ID` scheme - RESOLVED: reuse, do not invent.**
   `DataPipeline/data_cache/dimensions/finrag_dim_sec_sections.parquet` already
   is the documented ordinal table (`hf_section_code`, keyed by
   `sec_item_canonical`). Confirmed 1:1 against the real fact table's 20
   distinct `section_ID` values (0-19; `ITEM_16` never appears in production
   data and has `hf_section_code=null` in the dim table - consistent).

2. **Footer-boilerplate regex (Gotcha 3) - still needs a small tuning pass**,
   but not blocking: build Stage 3 with the pattern observed on Apple, then
   test it against the 3-4 experimental-round companies below before it
   touches the full backfill. Low risk since it only affects sentence
   boundaries, not field identity.

3. **Heuristics - RESOLVED: basic and final, per explicit user direction.**
   Simple regex two/three-condition checks (Stage 4, unchanged from the
   original proposal). Confirmed the real bulk file's booleans came from an
   undocumented separate process (204,324 rows are still literally `None` -
   the `extract_and_convert`/`v2.1_combined_extraction` batch never computed
   them either) - not worth chasing further. This basic implementation is
   the final form; it will not be extended to derive any other fields later.

4. **HTML caching - RESOLVED: no caching, always re-fetch.** Simpler, always
   fresh; incremental loads happen once and the *output* (the assembled
   parquet) is what gets persisted, not the raw HTML.

5. **Backfill scope - RESOLVED via direct EDA on the real fact table**
   (all 21 curated companies, `report_year` coverage):
   - Every company already has continuous fiscal-year coverage from its IPO
     year (or 2006, whichever is later) through **at least FY2024** - Tesla
     2010-2024, Meta 2012-2024, Visa 2008-2024, Alphabet 2015-2024, all
     others 2006-2024. **No real 2006-2011 sentence-data hole exists** - that
     gap was in the *embeddings* (Phase 4, gated), not in this fact table.
   - **5 of 21 companies already reached FY2025**: Walmart, Microsoft, NVIDIA,
     Oracle, Costco. The other **16 companies are missing their most recent
     (FY2025) 10-K** - this is the real, concrete, current incremental-add
     target, not a historical backfill.
   - One irregular case: **Johnson & Johnson** is missing 5 non-contiguous
     years within its own range (2009, 2012, 2015, 2017, 2020) - traced to
     the original `v1.0_75companies_1M` load being a *stratified sample*,
     not an exhaustive corpus, so this is an artifact of sampling, not a
     genuine data gap. Optional lower-priority backfill, not urgent.
   - **Conclusion: default scope going forward = "fetch FY2025 for the 16
     companies not yet at FY2025."** J&J's 5 gap-years can be added later as
     a separate, explicitly-labeled backfill run using the same pipeline.

## What's already been validated experimentally (this session, scratchpad)
- Fetching, filtering, section extraction, and section text quality all
  confirmed working against real curated companies (Apple, Microsoft,
  Tesla) - see `EDGARTOOLS_REFERENCE.md` for the verified API and gotchas.
- Lightweight regex sentence splitting works (315 sentences from Apple's
  Item 1A) once the "Item X." false-split issue is handled.
- Throughput: ~1-3.5s per filing fetch+parse - full 21-company backfill is a
  minutes-scale job, not hours.

## Development pattern (per user direction)

Build all 5 stage files plus one orchestration entrypoint that chains them
(mirroring `src_aws_etl`'s small-focused-file pattern), but do not treat the
first working run as final:

1. Write Stages 1-5 + `run_pipeline.py` orchestrator.
2. **Experimental validation round (mandatory before any full-scale run):**
   fetch just the FY2025 filing for 3-4 companies with clean, fully
   contiguous prior coverage - **Apple (320193), Amazon (1018724), Exxon
   Mobil (34088), Tesla (1318605)** - into a temporary parquet. These are
   real, currently-missing rows (none of the four has reached FY2025 yet),
   so this is a genuine incremental-add test, not a synthetic one.
3. Load that temp parquet next to the real
   `finrag_fact_sentences.parquet` and directly compare: dtypes, string
   formats (dates, IDs), `section_ID`/`section_name` pairs, sentenceID
   collision-freedom, row_hash recomputation, and eyeball a sample of actual
   sentence text/cleaning quality.
4. Fix whatever the comparison surfaces - **especially** any inconsistency
   in `sentenceID`, `temporal_bin`, `report_year`, or `filingDate`/
   `reportDate`, since those are the fields the user flagged as most likely
   to corrupt data/embeddings if wrong - before considering the pipeline
   done.
5. Only after that validation round passes: run the full 16-company FY2025
   incremental fetch.

## Next step
Implement Stages 1-5 + orchestrator as separate, individually-testable
modules, then run the experimental validation round above before scaling up.
