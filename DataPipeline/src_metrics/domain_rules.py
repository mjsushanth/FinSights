"""
domain_rules.py - loads per-company ratio-suppression rules from
config/not_applicable_by_cik.yaml.

The legacy module (src_metrics_legacy/analytical_layer.py's
NOT_APPLICABLE_BY_CIK) stored this as a dict literal keyed by raw CIK
string - a real bug there: CIK "0000059478" (Eli Lilly) was defined twice,
and a dict literal silently keeps the last occurrence. Moving to a list
source format plus an explicit duplicate check here closes that off, and
also catches a metric-label typo (a rule excluding a metric name that
doesn't match any known derived metric would previously just silently do
nothing).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from models import DomainRule


def load_domain_rules(path: Path, expected_labels: set[str]) -> dict[str, DomainRule]:
    with open(path) as f:
        records = yaml.safe_load(f)

    rules: dict[str, DomainRule] = {}
    for r in records:
        cik = r["cik"]
        if cik in rules:
            raise ValueError(f"Duplicate CIK in domain rules: {cik}")

        excluded = tuple(r["excluded_metrics"])
        unknown = set(excluded) - expected_labels
        if unknown:
            raise ValueError(
                f"Domain rule for CIK {cik} ({r['company']}) excludes unknown "
                f"metric label(s): {unknown} - check for a typo against the "
                f"real derived-metric label set."
            )

        rules[cik] = DomainRule(
            cik=cik,
            company=r["company"],
            reason=r["reason"].strip(),
            excluded_metrics=excluded,
        )

    return rules


def excluded_metrics_for(rules: dict[str, DomainRule], cik: str) -> set[str]:
    rule = rules.get(cik)
    return set(rule.excluded_metrics) if rule else set()
