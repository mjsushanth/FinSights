# src_metrics rebuild — architecture plan

**Status**: implemented and validated (2026-07-27) - all modules built,
34 unit tests passing, 2 real-network integration tests passing (Apple,
Mastercard), and a real-data parity check against the legacy production
KPI table confirmed exact-match numeric output on overlapping years
(e.g. Apple FY2024 Current Ratio: 0.867313 in both). **Not yet done**:
the full 25-company production run + S3 push (cutover step 3-4) and the
ModelPipeline hardcode fixes (step 6) - those are deliberately separate,
larger-blast-radius steps, gated on a explicit go-ahead rather than
bundled into this build-and-validate pass. See
`LEGACY_MODULE_FINDINGS.md` for the concrete, cited problems this rebuild
fixes - this document is the "what we're building instead," not a repeat
of the findings.

## Design philosophy for this rebuild

Use a class where there's real object-oriented value - state carried
across multiple method calls, or a genuine multi-step stateful workflow
(mirroring `src_aws_etl/etl/merge_pipeline.py`'s `MergePipeline`, which
holds `self.config`/`self.s3`/`self.stats` and drives a real multi-step
process). Do **not** wrap simple config/path lookups in a class just to
have a class - if something is "read three YAML fields, return them,"
that's a dataclass (a typed, immutable data container - genuinely useful
per the "typed objects" ask) or a plain function, not a class with
delegating properties. Concretely in this module:
- `Company`, `GaapTagInfo`, `DomainRule` - **dataclasses**. They represent
  real entities with fields, no behavior needed beyond that.
- `MetricsConfig` - **a dataclass**, loaded via one plain function
  (`load_metrics_config(path) -> MetricsConfig`). It does not wrap or
  subclass `ETLConfig` - the orchestrator composes both directly
  (`ETLConfig()` for bucket/credentials/S3 client, which are correctly
  shared project-wide; `MetricsConfig` for what's actually specific to
  this module - the company dimension path, output key, archive settings).
  A class whose only job is delegating to another class's properties
  would be exactly the "class for the sake of paths" pattern to avoid.
- `GaapRegistry` / domain rules - **plain functions returning a
  `dict[str, GaapTagInfo]`** (or list of `DomainRule`), not a wrapper class
  - no behavior beyond lookup is needed.
- **`MetricsPipeline`** (the orchestrator) - **a real class**. It holds
  config, the company list, and the GAAP registry as instance state set up
  once in `__init__`, then drives `fetch_facts()` -> `derive_kpis()` ->
  `merge_and_validate()` -> `push()` as methods operating on that shared
  state across a genuinely multi-step process. This is the one place in
  the module where OOP earns its keep, same as `MergePipeline`.

## Module layout

```
DataPipeline/src_metrics/
  __init__.py
  config.py            # MetricsConfig dataclass + load_metrics_config()
  models.py             # Company, GaapTagInfo, DomainRule dataclasses
  gaap_registry.py      # build_gaap_registry() -> dict[str, GaapTagInfo], from config/gaap_aliases.yaml
  domain_rules.py       # load_domain_rules() -> dict[cik, set[str]], from config/not_applicable_by_cik.yaml
  xbrl_facts.py          # SEC XBRL fetch + label/alias matching + numeric cleaning (ported, cleaned)
  derived_kpis.py        # compute_operating_income, _row_to_year_series, _sum_rows_to_year_series, etc.
  coverage.py             # compute_total_missing_derived - the non-regression guard, preserved as-is
  pipeline.py              # MetricsPipeline class - the orchestrator
  push_to_s3.py             # upload to ml_config.yaml's kpi_facts path + local-mirror sync
  run_pipeline.py           # thin CLI/CI entrypoint: builds a MetricsPipeline and calls .run()
  .aws_config/
    metrics_config.yaml
  config/
    not_applicable_by_cik.yaml
    gaap_aliases.yaml
  tests/
    test_gaap_registry.py
    test_clean_numeric_series.py
    test_row_and_sum_year_series.py
    test_compute_operating_income.py
    test_domain_rules.py
    test_coverage_guard.py
    test_metrics_config.py
    test_integration_single_company.py   # real network, opt-in, 1 company/1 year
  PLAN.md
  LEGACY_MODULE_FINDINGS.md
```

## Config: `metrics_config.yaml` + `MetricsConfig` dataclass

```yaml
s3:
  bucket_name: sentence-data-ingestion-mjs
  region: us-east-1

company_dimension:
  # Single parameter controlling the whole company universe. Growing from
  # 25 to 30/40/100 companies is a one-line edit here, never a code change.
  path: DataPipeline/data_cache/dimensions
  filename: finrag_dim_companies_25.parquet

output:
  kpi_facts:
    # Must match ModelPipeline/finrag_ml_tg1/.aws_config/ml_config.yaml's
    # s3.kpi_facts block exactly - test_metrics_config.py asserts this so
    # the two configs can't silently drift apart.
    path: DATA_MERGE_ASSETS/FINRAG_FACT_METRICS
    filename: KPI_FACT_DATA_EDGAR.parquet
  archive:
    path: DATA_MERGE_ASSETS/FINRAG_FACT_METRICS/ARCHIVE
    filename_pattern: "KPI_FACT_DATA_EDGAR_{timestamp}.parquet"
    max_backups: 3
  local_mirrors:
    - DataPipeline/data_cache/metrics_fact/KPI_FACT_DATA_EDGAR.parquet
    - ModelPipeline/finrag_ml_tg1/data_cache/metrics_fact/KPI_FACT_DATA_EDGAR.parquet

edgar:
  start_year: 2006
  end_year: 2025
  identity_env_var: EDGAR_IDENTITY   # no hardcoded personal-identity fallback - raises if unset
```

```python
@dataclass(frozen=True)
class MetricsConfig:
    bucket: str
    region: str
    company_dimension_path: Path
    kpi_facts_key: str
    archive_path: str
    archive_pattern: str
    max_backups: int
    local_mirrors: tuple[Path, ...]
    start_year: int
    end_year: int
    identity_env_var: str

def load_metrics_config(path: Path | None = None) -> MetricsConfig: ...
def get_edgar_identity(config: MetricsConfig) -> str:
    """Reads os.environ[config.identity_env_var]; raises if unset - no
    placeholder fallback, unlike the legacy module's three disagreeing
    defaults."""
```

## GAAP registry: structurally closing the missing-brace bug class

`GAAP_ALIASES` moves out of a hand-nested Python dict literal into a flat
**list** of records in `config/gaap_aliases.yaml` - a list can't silently
swallow a sibling entry the way `dict: {dict: {dict}}` did. Loaded via:

```python
@dataclass(frozen=True)
class GaapTagInfo:
    canonical_key: str
    human_label: str
    aliases: tuple[str, ...] = ()

def build_gaap_registry(records: list[dict]) -> dict[str, GaapTagInfo]:
    registry = {}
    for r in records:
        if r["tag"] in registry:
            raise ValueError(f"Duplicate GAAP tag: {r['tag']}")
        registry[r["tag"]] = GaapTagInfo(r["canonical_key"], r["human_label"], tuple(r.get("aliases", [])))
    assert len(registry) == len(records), (
        f"{len(records)} records loaded but registry has {len(registry)} entries - "
        "a record was silently dropped. This is exactly the bug class that hid "
        "4 GAAP tags in the old gaap_aliases.py."
    )
    return registry
```

A regression test asserts the 4 previously-hidden keys
(`other_liabilities_current`, `vie_activity_between_vie_and_entity_revenues`,
`equity_method_investment_gross_profit_loss`,
`net_income_loss_per_lp_unit_diluted`) are present as top-level entries.

## Domain rules: data, not Python source

`NOT_APPLICABLE_BY_CIK` moves to `config/not_applicable_by_cik.yaml` as a
**list** of `{cik, company, reason, excluded_metrics}` records - a list,
not a dict keyed by CIK, since the real duplicate-CIK bug (Eli Lilly
defined twice) is exactly the silent-last-write-wins failure a list plus
a loader-side duplicate check closes off. `reason:` replaces what's
currently a bare Python comment, so the domain judgment (e.g. "Mastercard
holds no inventory, Quick Ratio is structurally invalid") stays documented
as data, not lost. The loader raises on a duplicate CIK or an excluded-
metric label that doesn't match any known derived-metric name.

## Ported logic (from `src_metrics_legacy/analytical_layer.py`)

`xbrl_facts.py` and `derived_kpis.py` carry over the genuinely good parts
verbatim in spirit, cleaned up: label/alias matching, `_clean_numeric_series`,
`_row_to_year_series`/`_sum_rows_to_year_series`, `compute_operating_income()`'s
3-tier fallback. Every function takes explicit parameters (a CIK, a
`GaapTagInfo` registry, a company list) instead of reaching for a module-level
hardcoded constant. `coverage.py` carries over `compute_total_missing_derived`
essentially unchanged - it's already correct, it just needs real test coverage
(currently has none) and a home outside a 1300-line file.

## `MetricsPipeline` (the orchestrator - the one real class)

```python
class MetricsPipeline:
    def __init__(self, config: MetricsConfig, etl_config: ETLConfig):
        self.config = config
        self.etl = etl_config
        self.companies: list[Company] = load_companies(config.company_dimension_path)
        self.gaap_registry: dict[str, GaapTagInfo] = build_gaap_registry(...)
        self.domain_rules: dict[str, set[str]] = load_domain_rules(...)
        self.stats: dict = {}

    def fetch_facts(self) -> pl.DataFrame: ...
    def derive_kpis(self, facts: pl.DataFrame) -> pl.DataFrame: ...
    def merge_and_validate(self, new_df: pl.DataFrame) -> pl.DataFrame:
        """Downloads current production KPI table from S3 first (cloud is
        the source of truth), applies compute_total_missing_derived as a
        non-regression guard, only proceeds if coverage doesn't regress."""
    def push(self, df: pl.DataFrame) -> None:
        """Uploads to config.kpi_facts_key, then copies to both
        config.local_mirrors - the same 'S3 first, then sync local
        mirrors' pattern as MergePipeline.sync_local_data_cache(), reused
        in spirit rather than duplicated as a new mechanism."""
    def run(self) -> pl.DataFrame:
        facts = self.fetch_facts()
        derived = self.derive_kpis(facts)
        merged = self.merge_and_validate(derived)
        self.push(merged)
        return merged
```

## Test suite

Unit, no network: GAAP registry length + 4-key regression + duplicate-tag
raise; numeric-cleaning table-driven cases (`"1,234"`, `"(123)"`, em-dash
as NaN); alias-matching and "keep last per year" collapsing on synthetic
frames; all 4 operating-income fallback tiers on synthetic frames;
domain-rules duplicate-CIK/unknown-metric-label raises;
`compute_total_missing_derived` given synthetic strictly-better/-worse/
-equal coverage pairs (currently zero tests exist for the single most
important safety mechanism in the pipeline); `MetricsConfig` parses real
YAML and its `kpi_facts_key` matches `ml_config.yaml`'s value exactly.

Real-network integration (opt-in, mirroring how `src_edgar_incremental`
was validated - one real company/year before scaling): Apple (sanity-range
checks on derived ratios, not exact values, since SEC data can restate)
and Mastercard (proves domain-exclusion wiring end to end - Quick Ratio
should come back absent).

Parity test: for 2-3 CIK/year pairs already in the current production
parquet, new output must match old output within tolerance - the 4
newly-fixed GAAP metrics appearing is an expected, fine delta; anything
else blocks the cutover.

## Cutover sequence

1. Build this module complete and tested; `src_metrics_legacy/` and its
   (now repointed) CI stay untouched throughout.
2. Run the parity test against the frozen 21-company production parquet.
3. Once parity holds, run for real across all 25 companies in
   `finrag_dim_companies_25.parquet` - the first real exercise of "growing
   the roster is a config change, not a code change."
4. Push to S3 at the already-defined `ml_config.yaml` key, with
   `compute_total_missing_derived` as the non-regression guard against the
   current production file (downloaded fresh from S3 first).
5. Sync both local mirrors.
6. Only once step 5 is confirmed for all 25 companies: fix the
   ModelPipeline-side hardcodes - `loaders/data_loader_strategy.py:102`
   (dimension filename), `rag_modules_src/metric_pipeline/main.py:47-48`
   (should read from `ml_config.yaml` via `ml_config_loader.py`, not a
   second hardcoded path), and `ml_config.yaml`'s own `data_ml.dimensions`
   block (still says `_21`).
7. Delete `src_metrics_legacy/config.py` and `kpi_metrics_data.py`
   outright (confirmed dead/non-functional - see `LEGACY_MODULE_FINDINGS.md`).
   Keep `analytical_layer.py`/`gaap_aliases.py`/`Dockerfile` in
   `src_metrics_legacy/` as historical reference, matching the
   `src_legacy_bs4_scraper/` precedent.
8. Simplify `.github/workflows/src_metrics.yml`: repoint `paths:` at
   `DataPipeline/src_metrics/**`, delete the Docker build/run steps,
   replace with a direct Python step on `ubuntu-latest` (no Docker, no
   Airflow, per explicit instruction).

## Verification

- `pytest DataPipeline/src_metrics/tests/ -m "not integration"` passes.
- Integration tests pass against real EDGAR data for Apple + Mastercard.
- Parity test passes against the current 21-company production parquet.
- After the real 25-company run: row-count check confirms all 4 new
  companies (CIKs 731766, 1133421, 18230, 1283699) have nonzero rows.
- `aws s3 ls` confirms the pushed file at the exact `ml_config.yaml` path;
  both local mirrors are byte-identical to it (md5 check).
- A quick `LocalCacheLoader` smoke import confirms ModelPipeline's RAG can
  load the updated KPI file without error after the loader-path fixes.
