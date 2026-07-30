"""
Cross-encoder reranking of expanded sentence blocks via Bedrock Rerank (Cohere
Rerank 3.5). See guidance/retrieval_telemetry_and_reranking_design.md and
guidance/ANALYSIS_reranker_judgment_calls_2026-07-29.md for the full design and
the reasoning behind the defaults used here.

Insertion point: between SentenceExpander.expand_and_deduplicate() and
ContextAssembler.assemble() in run_supply_line_2_rag(). Because
ContextAssembler always re-sorts into document order regardless of any
relevance ranking, reordering alone has zero effect on the final context --
the only lever that matters here is PRUNING (dropping low-relevance blocks
entirely), so this module groups sentences into blocks and prunes blocks,
never reorders sentences for delivery.

Grouping is strict-contiguous: a block never bridges a gap in sentence_pos.
Bridging trades pruning resolution (the only lever this feature has) for
passage coherence the generator cannot actually perceive (each sentence is
already rendered as its own paragraph downstream) -- see the ANALYSIS doc
Sec 3 for the full argument and the interval-arithmetic derivation showing
"bridge a 1-sentence gap" actually means "merge two blocks whose core hits
are 8 positions apart" under the existing +/-3 window.
"""

import logging
import math
import time
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config

from finrag_ml_tg1.rag_modules_src.rag_pipeline.models import ContextBlock, SentenceRecord

logger = logging.getLogger(__name__)


class CohereReranker:
    """
    Groups SentenceRecords into contiguous blocks, scores each against the
    query with cohere.rerank-v3-5:0 via bedrock-agent-runtime, prunes to the
    top N (with a score floor), and returns the surviving SentenceRecords in
    their original relative order. Degrades gracefully: any failure returns
    the input sentences unchanged rather than breaking the query.
    """

    def __init__(
        self,
        retrieval_config: Dict[str, Any],
        region: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        client: Optional[Any] = None,
    ) -> None:
        self.region = region
        self.model_id = retrieval_config.get("rerank_model_id", "cohere.rerank-v3-5:0")
        self.top_n = retrieval_config.get("rerank_top_n_blocks", 8)
        self.min_score = retrieval_config.get("rerank_min_score", 0.0)
        self.max_sources = retrieval_config.get("rerank_max_sources", 100)
        self.cost_per_1k = retrieval_config.get("rerank_cost_per_1k_queries", 2.00)

        # Builds its own client, same precedent as S3VectorsRetriever -- no new
        # MLConfig method needed.
        self.client = client or boto3.client(
            "bedrock-agent-runtime",
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        )

        self._stats: Dict[str, Any] = {}

    def last_call_stats(self) -> Dict[str, Any]:
        """Blocks in/out, sentences in/out, search_units, est_cost_usd, latency_ms."""
        return dict(self._stats)

    def rerank(self, query: str, sentences: List[SentenceRecord]) -> List[SentenceRecord]:
        """Single public entry point. Returns a pruned list, or `sentences`
        unchanged if reranking is unnecessary or fails."""
        if len(sentences) < 2:
            return sentences

        t0 = time.perf_counter()
        try:
            blocks = self.score_blocks(query, sentences)
            if blocks is None:
                return sentences

            kept = self._select(blocks)
            by_id = {s.sentence_id: s for s in sentences}
            out = self._flatten(kept, by_id)

            self._stats = {
                "blocks_in": len(blocks),
                "blocks_kept": len(kept),
                "sents_in": len(sentences),
                "sents_out": len(out),
                "search_units": math.ceil(len(blocks) / 100),
                "est_cost_usd": math.ceil(len(blocks) / 100) * self.cost_per_1k / 1000,
                "latency_ms": (time.perf_counter() - t0) * 1000,
            }
            logger.info(
                "Rerank: %d blocks -> %d kept, %d -> %d sentences, %.0f ms",
                len(blocks), len(kept), len(sentences), len(out), self._stats["latency_ms"],
            )
            return out

        except Exception as e:
            # Same graceful-degradation contract as S3VectorsRetriever: never break the query.
            logger.error("Reranking failed, passing through unreranked: %s", e, exc_info=True)
            self._stats = {"error": str(e), "latency_ms": (time.perf_counter() - t0) * 1000}
            return sentences

    def score_blocks(self, query: str, sentences: List[SentenceRecord]) -> Optional[List[ContextBlock]]:
        """
        Group + score ALL candidate blocks against the query, with final_score set,
        but WITHOUT pruning/selection. One Bedrock Rerank call regardless of caller's
        eventual cutoff -- lets analysis code (e.g. a top-N sweep or score-distribution
        check) simulate arbitrary top_n/min_score choices from a single scored pass,
        with no repeat API calls. Returns None if there's nothing to score (fewer than
        2 blocks), signalling the caller should pass sentences through unchanged.
        """
        blocks = self._group_into_blocks(sentences)
        if len(blocks) <= 1:
            return None

        if len(blocks) > self.max_sources:
            blocks.sort(key=lambda b: -b.base_score)
            blocks = blocks[: self.max_sources]
            logger.warning("Truncated to %d blocks before rerank (cost guard, not API limit)",
                            self.max_sources)

        results = self._call_rerank(query, [b.text for b in blocks])
        for r in results:
            blocks[r["index"]].final_score = r["relevanceScore"]
        return blocks

    def _group_into_blocks(self, sentences: List[SentenceRecord]) -> List[ContextBlock]:
        """
        Group into contiguous runs within (cik_int, report_year, section_name),
        ordered by sentence_pos. Strict-contiguous: a new block starts whenever
        the group key changes OR sentence_pos is not exactly prev_pos + 1.
        """
        ordered = sorted(
            sentences,
            key=lambda s: (s.cik_int, s.report_year, s.section_name, s.sentence_pos),
        )

        blocks: List[ContextBlock] = []
        current: List[SentenceRecord] = []

        def flush():
            if not current:
                return
            similarities = [max(0.0, 1.0 - s.parent_hit_distance / 2.0) for s in current]
            sources: set = set()
            variant_ids: set = set()
            for s in current:
                sources |= s.sources
                variant_ids |= s.variant_ids
            blocks.append(ContextBlock(
                doc_id=current[0].doc_id,
                cik_int=current[0].cik_int,
                report_year=current[0].report_year,
                sec_item_canonical=current[0].section_name,
                company_name=current[0].company_name,
                text="\n".join(s.text for s in current),
                sentence_ids=[s.sentence_id for s in current],
                base_score=max(similarities),
                final_score=0.0,
                sources=sources,
                variant_ids=variant_ids,
                core_hit_count=sum(1 for s in current if s.is_core_hit),
            ))

        prev_key = None
        prev_pos = None
        for s in ordered:
            key = (s.cik_int, s.report_year, s.section_name)
            if key != prev_key or (prev_pos is not None and s.sentence_pos != prev_pos + 1):
                flush()
                current = []
            current.append(s)
            prev_key = key
            prev_pos = s.sentence_pos
        flush()

        return blocks

    def _call_rerank(self, query: str, texts: List[str]) -> List[Dict[str, Any]]:
        model_arn = f"arn:aws:bedrock:{self.region}::foundation-model/{self.model_id}"
        resp = self.client.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": query}}],
            sources=[
                {"type": "INLINE",
                 "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": t}}}
                for t in texts
            ],
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {"modelArn": model_arn},
                    "numberOfResults": len(texts),
                },
            },
        )
        return resp["results"]

    def _select(self, blocks: List[ContextBlock]) -> List[ContextBlock]:
        scored = [b for b in blocks if b.final_score >= self.min_score]
        scored.sort(key=lambda b: -b.final_score)
        return scored[: self.top_n] if self.top_n else scored

    def _flatten(
        self,
        blocks: List[ContextBlock],
        by_id: Dict[str, SentenceRecord],
    ) -> List[SentenceRecord]:
        out: List[SentenceRecord] = []
        for block in blocks:
            for sid in block.sentence_ids:
                rec = by_id.get(sid)
                if rec is not None:
                    out.append(rec)
        return out
