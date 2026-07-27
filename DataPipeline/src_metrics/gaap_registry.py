"""
gaap_registry.py - loads the GAAP tag -> alias registry from
config/gaap_aliases.yaml.

The legacy module (src_metrics_legacy/gaap_aliases.py) stored this as a
hand-nested Python dict literal - a missing closing brace silently nested
4 intended top-level entries inside a sibling entry, so those 4 GAAP
concepts were never queried from EDGAR at all. Moving the source data to a
flat YAML *list* makes that exact bug class structurally impossible (a
list can't silently swallow a sibling the way `dict: {dict: {dict}}` can -
a YAML indentation mistake is a parse error, not silent nesting), and
build_gaap_registry()'s count assertion below is a second, independent
guard against the same failure mode recurring in a different form.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from models import GaapTagInfo


def build_gaap_registry(records: list[dict]) -> dict[str, GaapTagInfo]:
    registry: dict[str, GaapTagInfo] = {}
    for r in records:
        if r["tag"] in registry:
            raise ValueError(f"Duplicate GAAP tag in registry source: {r['tag']}")
        registry[r["tag"]] = GaapTagInfo(
            canonical_key=r["canonical_key"],
            human_label=r["human_label"],
            aliases=tuple(r.get("aliases") or []),
        )

    assert len(registry) == len(records), (
        f"{len(records)} records loaded but registry has {len(registry)} entries - "
        "a record was silently dropped. This is exactly the bug class that hid "
        "4 GAAP tags in the old gaap_aliases.py - investigate before proceeding."
    )
    return registry


def load_gaap_registry(path: Path) -> dict[str, GaapTagInfo]:
    with open(path) as f:
        records = yaml.safe_load(f)
    return build_gaap_registry(records)
