import pytest

from gaap_registry import build_gaap_registry
from models import GaapTagInfo

# The 4 tags that were silently hidden by a missing-brace bug in the
# legacy src_metrics_legacy/gaap_aliases.py - regression test.
PREVIOUSLY_HIDDEN_KEYS = {
    "other_liabilities_current",
    "vie_activity_between_vie_and_entity_revenues",
    "equity_method_investment_gross_profit_loss",
    "net_income_loss_per_lp_unit_diluted",
}


def test_build_gaap_registry_basic():
    records = [
        {"tag": "NetIncomeLoss", "canonical_key": "net_income", "human_label": "Net Income", "aliases": ["NI"]},
        {"tag": "Assets", "canonical_key": "total_assets", "human_label": "Total Assets"},
    ]
    registry = build_gaap_registry(records)
    assert len(registry) == 2
    assert registry["NetIncomeLoss"] == GaapTagInfo("net_income", "Net Income", ("NI",))
    assert registry["Assets"].aliases == ()


def test_build_gaap_registry_raises_on_duplicate_tag():
    records = [
        {"tag": "Assets", "canonical_key": "a", "human_label": "A"},
        {"tag": "Assets", "canonical_key": "b", "human_label": "B"},
    ]
    with pytest.raises(ValueError, match="Duplicate GAAP tag"):
        build_gaap_registry(records)


def test_real_gaap_aliases_yaml_has_no_hidden_entries():
    """The actual regression test: load the real config/gaap_aliases.yaml
    and confirm the 4 previously-nested-and-lost keys are present as real,
    top-level canonical_key values."""
    import yaml

    from config import load_metrics_config

    config = load_metrics_config()
    with open(config.gaap_registry_path) as f:
        records = yaml.safe_load(f)

    registry = build_gaap_registry(records)
    canonical_keys = {info.canonical_key for info in registry.values()}

    missing = PREVIOUSLY_HIDDEN_KEYS - canonical_keys
    assert not missing, f"Previously-hidden GAAP keys still missing: {missing}"
