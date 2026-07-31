"""
Pure, in-process capture of per-query retrieval provenance.

No I/O, no AWS calls, no Polars. Consumes the same objects already live inside
run_supply_line_2_rag() (RetrievalBundle, SentenceRecord) and returns a
JSON-serializable dict that rides the existing ContextMetadata.retrieval_stats
socket (declared in synthesis_pipeline/models.py, never previously populated)
all the way through to the exported response JSON.
"""

from typing import Any, Dict, List, Optional

from finrag_ml_tg1.rag_modules_src.rag_pipeline.models import (
    RetrievalBundle,
    S3Hit,
    SentenceRecord,
)


def rank_hits_by_distance(hits: List[S3Hit]) -> List[S3Hit]:
    """
    Return hits sorted ascending by distance.

    Do NOT trust incoming list order as rank. S3VectorsRetriever._proportional_topk()
    now sorts its combined output at the source (fixed 2026-07-29), but this stays
    defensive: any future change to the retriever's internal sampling should not
    silently corrupt telemetry rank again.
    """
    return sorted(hits, key=lambda h: h.distance)


def build_retrieval_telemetry(
    query: str,
    bundle: RetrievalBundle,
    unique_sents: List[SentenceRecord],
    stage_timings_ms: Optional[Dict[str, float]] = None,
    reranked_sents: Optional[List[SentenceRecord]] = None,
    top_n_logged: int = 50,
) -> Dict[str, Any]:
    """Capture per-query retrieval provenance as a JSON-serialisable dict."""
    ranked = rank_hits_by_distance(bundle.union_hits)

    core_hits = []
    for rank, hit in enumerate(ranked[:top_n_logged], start=1):
        core_hits.append({
            "rank": rank,
            "sentence_id": hit.sentence_id,
            "distance": round(hit.distance, 6),
            "similarity": round(hit.similarity_score(), 6),
            "source": hit.source,
            "variant_id": hit.variant_id,
            "cik_int": hit.cik_int,
            "report_year": hit.report_year,
            "section_name": hit.section_name,
            "sentence_pos": hit.sentence_pos,
        })

    return {
        "schema_version": 1,
        "query": query,
        "variant_queries": list(bundle.variant_queries),
        "timings_ms": stage_timings_ms or {},
        "counts": {
            "filtered_hits": len(bundle.filtered_hits),
            "global_hits": len(bundle.global_hits),
            "union_hits": len(bundle.union_hits),
            "expanded_sents": len(unique_sents),
            "core_sents": sum(1 for s in unique_sents if s.is_core_hit),
            "reranked_sents": len(reranked_sents) if reranked_sents is not None else None,
        },
        "core_hits": core_hits,
        "expanded_sentence_ids": [s.sentence_id for s in unique_sents],
        "reranked_sentence_ids": (
            [s.sentence_id for s in reranked_sents] if reranked_sents is not None else None
        ),
    }
