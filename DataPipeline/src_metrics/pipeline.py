"""
pipeline.py - MetricsPipeline: the one real class in this module.

Every other piece of src_metrics is plain data (dataclasses in models.py)
or plain functions (gaap_registry.py, domain_rules.py, xbrl_facts.py,
derived_kpis.py, coverage.py, push_to_s3.py). This class exists because it
genuinely needs to be one: it holds config/companies/registry/rules as
state set up once, then drives a real multi-step, stateful workflow
(fetch -> derive -> merge-and-validate -> push) across that state -
the same shape as src_aws_etl/etl/merge_pipeline.py's MergePipeline.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import polars as pl
from edgar import set_identity

PROJECT_ROOT = Path(__file__).parent.parent  # DataPipeline/
sys.path.insert(0, str(PROJECT_ROOT))

from src_aws_etl.etl.config_loader import ETLConfig

from config import MetricsConfig, get_edgar_identity, load_metrics_config
from coverage import find_regressed_keys
from derived_kpis import EXPECTED_DERIVED_LABELS, compute_core_kpis_for_company
from domain_rules import load_domain_rules
from gaap_registry import load_gaap_registry
from models import Company, load_companies
from push_to_s3 import push_kpi_facts, read_current_kpi_facts
from xbrl_facts import fetch_10k_facts


class MetricsPipeline:
    def __init__(self, config: MetricsConfig | None = None, etl: ETLConfig | None = None):
        self.config = config or load_metrics_config()
        self.etl = etl or ETLConfig()

        self.companies: list[Company] = load_companies(self.config.company_dimension_path)
        self.gaap_registry = load_gaap_registry(self.config.gaap_registry_path)
        self.domain_rules = load_domain_rules(self.config.domain_rules_path, EXPECTED_DERIVED_LABELS)

        set_identity(get_edgar_identity(self.config))
        self.stats: dict = {}

    def fetch_facts(self, companies: list[Company] | None = None, between: float = 1.5,
                     n_years_derived: int = 2) -> pl.DataFrame:
        """For each company: GAAP facts (fetch_10k_facts, controlled by
        config.start_year/end_year) + derived KPIs (last n_years_derived
        10-Ks). Concatenates into one long-format frame."""
        companies = companies if companies is not None else self.companies
        frames = []

        for i, company in enumerate(companies, start=1):
            print(f"[{i}/{len(companies)}] {company.name} (CIK {company.cik})")
            try:
                df_gaap = fetch_10k_facts(
                    company.cik, self.gaap_registry, self.config.start_year, self.config.end_year
                )
                df_kpis = compute_core_kpis_for_company(company.cik, n_years=n_years_derived)
                if not df_gaap.empty:
                    frames.append(df_gaap)
                if not df_kpis.empty:
                    frames.append(df_kpis)
            except Exception as e:
                print(f"  error for {company.cik}: {e}")
            time.sleep(between)

        if not frames:
            raise RuntimeError("No data collected for any company.")

        combined = pd.concat(frames, ignore_index=True)
        return pl.from_pandas(combined)

    def merge_and_validate(self, new_df: pl.DataFrame) -> pl.DataFrame:
        """Downloads the current production KPI table from S3 (cloud is
        the source of truth), merges in the new data (new rows replace old
        ones for the same cik+year+metric_label), and only proceeds if no
        existing (cik, year) pair's derived-metric coverage got worse
        (find_regressed_keys) - a brand-new year (naturally partial, e.g.
        a just-filed FY2025) is not held to this check, since there was
        nothing there before for it to regress from."""
        current = read_current_kpi_facts(self.config, self.etl)

        if current is None:
            merged = new_df
        else:
            key_cols = ["cik", "year", "metric_label", "metric_type"]
            replaced_keys = new_df.select(key_cols).unique()
            base = current.join(replaced_keys, on=key_cols, how="anti")
            merged = pl.concat([base, new_df], how="vertical")

            regressions = find_regressed_keys(
                current.to_pandas(), merged.to_pandas(), self.domain_rules, EXPECTED_DERIVED_LABELS
            )
            print(f"Coverage check: {len(regressions)} (cik, year) pair(s) with regressed coverage")
            if regressions:
                for r in regressions[:10]:
                    print(f"  {r['cik']} {r['year']}: {r['old_missing']} -> {r['new_missing']} missing "
                          f"(lost: {r['lost_metrics']})")
                raise ValueError(
                    f"Refusing to merge: {len(regressions)} existing (cik, year) pair(s) would lose "
                    "derived-metric coverage. Investigate before overwriting the production table."
                )

        self.stats["rows"] = merged.height
        self.stats["companies"] = merged["cik"].n_unique()
        return merged

    def push(self, df: pl.DataFrame) -> None:
        push_kpi_facts(df, self.config, self.etl)

    def run(self, companies: list[Company] | None = None) -> pl.DataFrame:
        facts = self.fetch_facts(companies=companies)
        merged = self.merge_and_validate(facts)
        self.push(merged)
        print(f"\nDone. {self.stats['rows']:,} rows, {self.stats['companies']} companies.")
        return merged
