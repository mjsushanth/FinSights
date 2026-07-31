# Findings: `src_metrics_legacy/` (formerly `src_metrics/`)

**Why this exists**: before rebuilding this module, every concrete problem
was verified directly against the actual files (not assumed from a
description) - both by a dedicated code-review pass and by direct
re-reads of the exact line numbers. This document is the record of what's
actually wrong, so the rebuild in `PLAN.md` is fixing real, cited problems
rather than a vague "it's messy" impression.

## What this module is

The numeric/KPI half of FinSights' hybrid RAG: extracts SEC XBRL facts via
`edgartools`, derives ratios/ROI-style metrics, and produces
`KPI_FACT_DATA_EDGAR.parquet` - the structured side that gets merged with
semantic sentence retrieval before LLM synthesis
(`ModelPipeline/finrag_ml_tg1/ARCHITECTURE.md`, Supply Line 1).

## Confirmed bugs and hardcoding, with citations

1. **`analytical_layer.py:34-56` - `EXPECTED_CIKS`**: a literal Python list
   of 21 zero-padded CIK strings, with no reference to any dimension/config
   table. Load-bearing in at least 3 places: `build_analytical_layer(ciks=
   EXPECTED_CIKS, ...)` (line 1206), `compute_total_missing_derived` (line
   904), `generate_coverage_report_csv`. Adding a company means editing
   Python source and pushing to `main`.

2. **`analytical_layer.py:146-223` - `NOT_APPLICABLE_BY_CIK`**: a second
   hardcoded structure (real domain logic - ratio suppression for
   insurers/no-inventory companies) keyed the same way. Contains a genuine
   duplicate-key bug: CIK `"0000059478"` (Eli Lilly) is defined twice
   (lines 199-202 and 219-222, identical values) - a plain dict literal
   silently keeps the last one. Harmless only because both copies agree by
   luck.

3. **`gaap_aliases.py:549-580` - a missing closing brace**, confirmed by
   direct read: the `"DeferredTaxAndOtherLiabilitiesNoncurrent"` entry's
   `aliases` list is never closed with `}` before the next intended
   top-level key. As a result, four entries -
   `OtherLiabilitiesCurrent`, `VariableInterestEntityActivityBetweenVIEAndEntityRevenues`,
   `EquityMethodInvestmentSummarizedFinancialInformationGrossProfitLoss`,
   `NetIncomeLossPerOutstandingLimitedPartnershipUnitDiluted` - are nested
   *inside* that one entry as siblings of `canonical_key`/`human_label`,
   not reachable as top-level `GAAP_ALIASES` keys. **These four GAAP
   concepts have never been queried from EDGAR by this pipeline** - a
   silent data-completeness bug, not just a lookup inconvenience.

4. **`config.py` is dead code** - confirmed via repo-wide grep: nothing
   imports it. Contains a hardcoded personal identity string,
   `USER_AGENT = "Karthik Raja (University Project; karthikraja.ai.project@gmail.com)"`,
   fake `SNS_TOPIC_ARN`/`SLACK_WEBHOOK_URL` placeholders (no SNS or Slack
   code exists anywhere in this module), and a fully separate `XBRL_TAGS`
   dict duplicating ~15 concepts `gaap_aliases.py` already covers, with a
   different, incompatible schema. An abandoned draft, not live config.

5. **`kpi_metrics_data.py` cannot run** - it's an Airflow DAG
   (`from airflow import DAG`), and `airflow` is not in
   `DataPipeline/environment.yml`. It also expects an output file named
   `analytical_layer_metrics_final.parquet` (line 69) that
   `run_analytical_layer_pipeline()` never produces (it writes
   `analytical_layer_metrics_last2yrs.parquet` and
   `KPI_FACT_DATA_EDGAR.parquet`) - superseded entirely by
   `run_pipeline_gh.py`.

6. **Two functions named `upload_results_to_s3`** in `analytical_layer.py`
   (lines 749 and 965, different signatures) - Python silently keeps the
   second; the first is unreachable dead code.

7. **`EXPECTED_DERIVED_LABELS` assigned twice** (line 128 as
   `list(dict.keys())`, then line 131 immediately overwritten as a set
   literal) - the first assignment is dead.

8. **A silent path override inside `run_analytical_layer_pipeline`**:
   `final_parquet_path` is set to `os.path.join(base_dir, ...)` (line
   1189), then immediately overwritten by `load_final_parquet_from_s3()`'s
   return value (line 1231), which downloads into
   `Path(__file__).parent` - i.e. inside the `src_metrics_legacy/` source
   tree itself, ignoring `base_dir` entirely. This is almost certainly why
   a stale `analytical_layer_metrics_final.parquet` was sitting directly
   in the module folder (confirmed as a strict subset of the live KPI
   data - 6,613 of 6,937 rows - missing derived ratios across most
   companies/years, i.e. an old, incomplete local run, not a fixture).

9. **`set_identity()` called at module import time** (`analytical_layer.py:24-25`)
   with a placeholder fallback (`"your-email@example.com"`) if
   `EDGAR_IDENTITY` is unset - merely importing the module can silently
   call SEC's identity-setter with garbage.

10. **Three different, disagreeing EDGAR-identity defaults** across the
    module: `"your-email@example.com"` (`kpi_metrics_data.py`),
    `"Default User &lt;default@example.com&gt;"` (`run_pipeline_gh.py:22`),
    and `config.py`'s hardcoded personal identity (unused/dead, but still
    a third convention).

11. **Data staleness/gap, confirmed by direct comparison**: the live KPI
    table (`KPI_FACT_DATA_EDGAR.parquet`, 6,937 rows, 21 CIKs, years
    2009-2025 - byte-identical across all three locations it's copied to)
    is frozen at the *original* 21-company roster. The 4 companies added
    to the sentence fact table this session - UnitedHealth Group (CIK
    731766), Northrop Grumman (1133421), Caterpillar (18230), T-Mobile US
    (1283699) - have **zero rows** here. Root cause is item 1 above:
    nothing re-derives the CIK list from a dimension table, so the KPI
    side had no way to notice the roster grew.

12. **The ML runtime side has the identical hardcoding problem**,
    independent of this module: `ModelPipeline/finrag_ml_tg1/loaders/data_loader_strategy.py`
    (lines 102, 127) and `rag_modules_src/metric_pipeline/main.py` (lines
    47-48) hardcode `finrag_dim_companies_21.parquet` and local-only KPI
    paths with no config indirection. `ml_config.yaml`'s own
    `data_ml.dimensions` block also still says `_21`, not `_25`. All three
    need updating together, once the new KPI data actually covers 25
    companies (see `PLAN.md`'s cutover sequence).

## What's genuinely good here (retained in the rebuild, not thrown away)

- **The core XBRL extraction/derivation logic** (`analytical_layer.py`,
  roughly lines 231-636): multi-alias label matching that copes with SEC's
  inconsistent tagging across companies/years, `_clean_numeric_series`
  correctly handling parenthetical-negative and comma-formatted numbers,
  and `compute_operating_income()`'s 3-tier fallback (exact tag ->
  pretax-income proxy -> manual gross-profit-minus-SG&A-minus-R&D
  reconstruction). This reflects real understanding of SEC filing quirks,
  not naive scraping.
- **The incremental-merge non-regression guard**
  (`compute_total_missing_derived`, lines 894-925): only accept a new run's
  output if derived-metric coverage is provably no worse than what's
  already there. A genuinely good safety idea for an incremental pipeline
  - currently has zero tests, which is being fixed in the rebuild.
- **`NOT_APPLICABLE_BY_CIK`'s underlying domain judgment** (e.g. no Quick
  Ratio for Mastercard, which holds no inventory) - the *mechanism* needs
  to move out of hardcoded Python, but the judgment itself is real and
  worth preserving as data.
- **`run_pipeline_gh.py`** (the live GitHub Actions entrypoint, as opposed
  to the dead `kpi_metrics_data.py` Airflow DAG) is clean and well-scoped -
  it correctly skips the S3 upload gracefully when AWS credentials aren't
  present rather than failing hard.

See `PLAN.md` for how each of these is being addressed.
