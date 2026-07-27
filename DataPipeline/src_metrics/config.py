"""
config.py - MetricsConfig: a typed, immutable data container for this
module's settings, loaded from metrics_config.yaml.

Deliberately NOT a class wrapping ETLConfig. ETLConfig
(src_aws_etl/etl/config_loader.py) already owns bucket/region/credential/
S3-client logic correctly - that's genuinely shared, project-wide state.
This module's config is just a handful of paths and settings specific to
KPI extraction; wrapping ETLConfig in a second class whose methods mostly
delegate would be exactly the "class for the sake of paths" pattern to
avoid. The orchestrator (pipeline.py) composes both directly:
ETLConfig() for bucket/credentials, MetricsConfig for everything here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

MODULE_DIR = Path(__file__).parent
REPO_ROOT = MODULE_DIR.parent.parent  # DataPipeline/src_metrics/ -> repo root
DEFAULT_CONFIG_PATH = MODULE_DIR / ".aws_config" / "metrics_config.yaml"


@dataclass(frozen=True)
class MetricsConfig:
    bucket: str
    region: str
    company_dimension_path: Path
    gaap_registry_path: Path
    domain_rules_path: Path
    kpi_facts_key: str
    archive_path: str
    archive_pattern: str
    max_backups: int
    local_mirrors: tuple[Path, ...]
    start_year: int
    end_year: int
    identity_env_var: str


def load_metrics_config(path: Path | None = None) -> MetricsConfig:
    path = path or DEFAULT_CONFIG_PATH
    with open(path) as f:
        cfg = yaml.safe_load(f)

    company_dim = cfg["company_dimension"]
    gaap = cfg["gaap_registry"]
    domain = cfg["domain_rules"]
    output = cfg["output"]
    kpi_facts = output["kpi_facts"]
    archive = output["archive"]
    edgar = cfg["edgar"]

    return MetricsConfig(
        bucket=cfg["s3"]["bucket_name"],
        region=cfg["s3"]["region"],
        company_dimension_path=REPO_ROOT / company_dim["path"] / company_dim["filename"],
        gaap_registry_path=REPO_ROOT / gaap["path"] / gaap["filename"],
        domain_rules_path=REPO_ROOT / domain["path"] / domain["filename"],
        kpi_facts_key=f"{kpi_facts['path']}/{kpi_facts['filename']}",
        archive_path=archive["path"],
        archive_pattern=archive["filename_pattern"],
        max_backups=archive["max_backups"],
        local_mirrors=tuple(REPO_ROOT / p for p in output["local_mirrors"]),
        start_year=edgar["start_year"],
        end_year=edgar["end_year"],
        identity_env_var=edgar["identity_env_var"],
    )


def get_edgar_identity(config: MetricsConfig) -> str:
    """Reads the EDGAR identity from the env var named in config. Raises
    if unset - no placeholder fallback. The legacy module had three
    different, disagreeing hardcoded defaults across its files; this
    module has exactly one source and fails loudly instead."""
    identity = os.getenv(config.identity_env_var)
    if not identity:
        raise RuntimeError(
            f"Environment variable {config.identity_env_var} is not set. "
            "SEC EDGAR requires a real identifying string (name + email) on "
            "every request - refusing to fall back to a placeholder."
        )
    return identity
