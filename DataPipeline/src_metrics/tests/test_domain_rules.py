import tempfile
from pathlib import Path

import pytest
import yaml

from domain_rules import excluded_metrics_for, load_domain_rules

EXPECTED_LABELS = {"Quick Ratio", "Current Ratio", "Free Cash Flow"}


def _write_yaml(records) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.safe_dump(records, tmp)
    tmp.close()
    return Path(tmp.name)


def test_load_domain_rules_valid_fixture():
    path = _write_yaml([
        {"cik": "0001141391", "company": "Mastercard", "reason": "no inventory",
         "excluded_metrics": ["Quick Ratio"]},
    ])
    rules = load_domain_rules(path, EXPECTED_LABELS)
    assert excluded_metrics_for(rules, "0001141391") == {"Quick Ratio"}
    assert excluded_metrics_for(rules, "0000000000") == set()  # unknown CIK -> no exclusions


def test_load_domain_rules_raises_on_duplicate_cik():
    path = _write_yaml([
        {"cik": "0000059478", "company": "Eli Lilly", "reason": "x", "excluded_metrics": ["Current Ratio"]},
        {"cik": "0000059478", "company": "Eli Lilly", "reason": "x", "excluded_metrics": ["Free Cash Flow"]},
    ])
    with pytest.raises(ValueError, match="Duplicate CIK"):
        load_domain_rules(path, EXPECTED_LABELS)


def test_load_domain_rules_raises_on_unknown_metric_label():
    path = _write_yaml([
        {"cik": "0001141391", "company": "Mastercard", "reason": "x",
         "excluded_metrics": ["Quikc Ratio"]},  # typo
    ])
    with pytest.raises(ValueError, match="unknown metric label"):
        load_domain_rules(path, EXPECTED_LABELS)
