"""
Offline retrieval-quality scoring against the gold set.

Pure functions on ID lists; no AWS, no pipeline imports. Kept separate from
retrieval_telemetry.py because this depends on the gold set and never runs in
the serving path.
"""

import random
from typing import Any, Dict, List, Optional, Sequence


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    """|retrieved@k intersect relevant| / |relevant|. Returns 0.0 if relevant is empty."""
    if not relevant_ids:
        return 0.0
    top_k = set(ranked_ids[:k])
    hits = sum(1 for r in relevant_ids if r in top_k)
    return hits / len(relevant_ids)


def reciprocal_rank(ranked_ids: Sequence[str], relevant_ids: Sequence[str]) -> float:
    """1 / (1-based rank of first relevant id); 0.0 if none present."""
    relevant = set(relevant_ids)
    for i, rid in enumerate(ranked_ids, start=1):
        if rid in relevant:
            return 1.0 / i
    return 0.0


def hit_at_k(ranked_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    """1.0 if any relevant id appears in the top k, else 0.0."""
    relevant = set(relevant_ids)
    return 1.0 if any(rid in relevant for rid in ranked_ids[:k]) else 0.0


def score_query(
    telemetry: Dict[str, Any],
    gold_record: Dict[str, Any],
    ks: Sequence[int] = (1, 3, 5, 10, 20, 30),
) -> Dict[str, Any]:
    """
    Score one query at all three pipeline stages: core (ANN retrieval only),
    expanded (post window-expansion), reranked (post pruning, if present).

    Reads gold_record['evidence_sentence_ids'] and gold_record['retrieval_scope'].
    """
    relevant = gold_record["evidence_sentence_ids"]
    core_ids = [h["sentence_id"] for h in telemetry["core_hits"]]
    expanded_ids = telemetry["expanded_sentence_ids"]
    reranked_ids = telemetry.get("reranked_sentence_ids")

    row: Dict[str, Any] = {
        "question_id": gold_record.get("question_id"),
        "retrieval_scope": gold_record.get("retrieval_scope"),
        "n_evidence": len(relevant),
    }

    for stage_name, ids in (
        ("core", core_ids),
        ("expanded", expanded_ids),
        ("reranked", reranked_ids),
    ):
        if ids is None:
            for k in ks:
                row[f"{stage_name}_recall@{k}"] = None
            row[f"{stage_name}_mrr"] = None
            continue
        for k in ks:
            row[f"{stage_name}_recall@{k}"] = recall_at_k(ids, relevant, k)
        row[f"{stage_name}_mrr"] = reciprocal_rank(ids, relevant)

    return row


def aggregate(
    per_query: List[Dict[str, Any]],
    group_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Mean each numeric metric, overall and optionally stratified (e.g. 'retrieval_scope').
    Includes n per cell so small-cell noise is visible in the output itself.
    """
    def _mean_block(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {"n": 0}
        numeric_keys = [
            k for k, v in rows[0].items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        out: Dict[str, Any] = {"n": len(rows)}
        for k in numeric_keys:
            vals = [r[k] for r in rows if r.get(k) is not None]
            out[k] = sum(vals) / len(vals) if vals else None
        return out

    result: Dict[str, Any] = {"overall": _mean_block(per_query)}

    if group_by:
        groups: Dict[Any, List[Dict[str, Any]]] = {}
        for row in per_query:
            key = row.get(group_by)
            groups.setdefault(key, []).append(row)
        result[f"by_{group_by}"] = {
            str(key): _mean_block(rows) for key, rows in groups.items()
        }

    return result


def paired_delta(
    arm_a: List[Dict[str, Any]],
    arm_b: List[Dict[str, Any]],
    metric: str,
    n_boot: int = 10_000,
    seed: int = 0,
) -> Dict[str, Any]:
    """
    Per-question paired difference b - a, joined on question_id.
    Returns mean delta, bootstrap 95% CI over questions, n_better/n_worse/n_tied.
    """
    by_id_a = {r["question_id"]: r for r in arm_a}
    by_id_b = {r["question_id"]: r for r in arm_b}
    common_ids = sorted(set(by_id_a) & set(by_id_b))

    deltas = []
    for qid in common_ids:
        va = by_id_a[qid].get(metric)
        vb = by_id_b[qid].get(metric)
        if va is None or vb is None:
            continue
        deltas.append(vb - va)

    if not deltas:
        return {
            "n": 0, "mean_delta": None, "ci_95": (None, None),
            "n_better": 0, "n_worse": 0, "n_tied": 0,
        }

    n_better = sum(1 for d in deltas if d > 0)
    n_worse = sum(1 for d in deltas if d < 0)
    n_tied = sum(1 for d in deltas if d == 0)

    rng = random.Random(seed)
    n = len(deltas)
    boot_means = []
    for _ in range(n_boot):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lo = boot_means[int(0.025 * n_boot)]
    hi = boot_means[int(0.975 * n_boot) - 1]

    return {
        "n": n,
        "mean_delta": sum(deltas) / n,
        "ci_95": (lo, hi),
        "n_better": n_better,
        "n_worse": n_worse,
        "n_tied": n_tied,
    }
