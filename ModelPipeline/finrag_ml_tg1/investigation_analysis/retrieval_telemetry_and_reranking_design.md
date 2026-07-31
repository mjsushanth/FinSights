> Collaborator artifact. Written by the research-collaborator agent. This is help offered,
> not instructions to follow and not a review. Weigh it and decide. Not part of the
> project's own documentation.

# ANALYSIS - Retrieval telemetry / recall@k+MRR harness (Item A) and Cohere Rerank 3.5 insertion (Item B)
**Date:** 2026-07-29 (UTC)
**Guidance level:** L3 WORKED for the design; L4 DIRECT for the verified external API facts (Bedrock Rerank schema, limits, pricing — those are arbitrary domain facts, no value in you deriving them). Three decisions are deliberately left framed-but-open at the end; they are judgement calls, not lookups.

**Prior work I read before answering:**
- `.claude/CLAUDE.md`, `ModelPipeline/finrag_ml_tg1/CLAUDE.md`
- `graphify query`/`explain`/`path` over `QueryOrchestrator`, `S3VectorsRetriever`, `SentenceExpander`, `ContextAssembler` (graph at `graphify-out/graph.json`)
- `rag_modules_src/synthesis_pipeline/supply_lines.py`, `orchestrator.py`, `models.py`, `query_logger.py`
- `rag_modules_src/rag_pipeline/models.py`, `s3_retriever.py`, `context_assembler.py` (L138-250), `sentence_expander.py` (signatures)
- `rag_modules_src/utilities/evaluation_metrics.py`
- `loaders/ml_config_loader.py` (public surface, `get_retrieval_config`, client factories)
- `.aws_config/ml_config.yaml` (`retrieval`, `serving_models`, `costs` blocks)
- `data_cache/qa_manual_exports/goldp3_analysis/p3_gold_test_suite_31q.json` (full schema + field distributions), `MLFlow_POC/data/gold_dataset.json`, `rag_modules_src/constants/gold_qs_constant.py`
- `data_cache/stage1_facts/finrag_fact_sentences.parquet` (schema + a live join against the gold evidence IDs)

## The short version

Both items land on **one existing file** — `synthesis_pipeline/supply_lines.py`, specifically `run_supply_line_2_rag()` — plus new modules and one config block. Item A is cheaper than you think because the plumbing already exists: `ContextMetadata.retrieval_stats` is declared, documented, and threaded all the way from `build_combined_context()` → `create_success_response()` → `_export_response()` → S3 JSON, and **nothing ever populates it**. You are filling in a pre-built socket, not adding a channel. Item B has one non-obvious wrinkle: `ContextBlock.final_score` is not in the live data path at all (the live path is `S3Hit → SentenceRecord → str`; `ContextBlock` is referenced only by its own definition and by a design contract doc), so building the reranker around it as a *pipeline type* would be a refactor — but re-using it as a *transient internal grouping inside `reranker.py`* is exactly right, and gets you a `List[SentenceRecord] -> List[SentenceRecord]` drop-in.

---

## Things I found that change the shape of the problem

I want these up front because two of them will silently corrupt your numbers if you don't know about them.

### 1. `bundle.union_hits` is not a valid ranking when there are more than 30 hits

`S3VectorsRetriever._deduplicate_hits()` (`s3_retriever.py` L458-520) sorts by distance ascending — good — then, if `len(deduped) > max_hits_before_expansion` (config: 30), hands off to `_proportional_topk()`. That function returns, at L624:

```python
sampled_hits = sampled_filtered + sampled_global
```

Two separately-sorted lists concatenated. The result is **not** globally sorted by distance. So if you compute rank as `enumerate(bundle.union_hits)`, every global-source hit gets a rank penalty of `len(sampled_filtered)` regardless of how good it was, and MRR comes out wrong — specifically, biased *down*, and biased down more for the `cross_company` / `cross_year` gold questions where global hits matter most. Which is precisely where you'd expect a reranker to help. You would misattribute the fix.

**Telemetry must recompute rank by sorting on `distance` itself**, not trust list order. One line, but it has to be a deliberate line.

### 2. `ContextAssembler.assemble()` sorts by document order, not score

`_sort_sentences()` sorts by `(company_name, report_year ASC, section_name, doc_id, sentence_pos)`. There is no score anywhere in the sort key. The consequence for Item B: **a reranker that only reorders changes literally nothing about the final context string.** The reordering is thrown away three lines later.

So in this architecture a reranker is only useful as a **selector/pruner** — it decides *what survives* into the context, not what order it appears in. This is actually the better use of a cross-encoder anyway (see the cost argument in §Item B), but it means "insert reranking" and "insert reordering" are different asks here, and you want the first one.

### 3. The gold set is real and usable, and I verified it against the live corpus

`p3_gold_test_suite_31q.json` (identical copy at `MLFlow_POC/data/` and `data_cache/qa_manual_exports/goldp3_analysis/`) is the one to use. Schema, verbatim keys:

```
question_id, cik_int, company_name, years, question_text, answer_type,
answer_text, answer_numeric, answer_unit, tolerance,
evidence_sentence_ids, evidence_spans, retrieval_scope, difficulty,
section_hints, notes, gold_version, created_by, created_at, curation_confidence
```

`evidence_sentence_ids` is your relevance label. It holds full `sentenceID` strings in the corpus's native format — e.g. `"0000034088_10-K_2008_section_8_2"` — which is directly comparable to `S3Hit.sentence_id` and `SentenceRecord.sentence_id` with **no normalisation needed**. I checked this empirically rather than assuming:

- 45 unique evidence sentence IDs across the 31 questions
- **45 / 45 resolve** in `data_cache/stage1_facts/finrag_fact_sentences.parquet` (614,787 rows)
- 31 / 31 questions have at least one evidence ID (zero unlabelled questions)

Distributions you'll want when you slice results:

| field | distribution |
| :-- | :-- |
| `len(evidence_sentence_ids)` | 1: **24 q**, 2: 2 q, 3: 2 q, 4: 3 q |
| `retrieval_scope` | `local`: 24, `cross_year`: 4, `cross_company`: 3 |
| `answer_type` | `span`: 26, `list`: 3, `boolean`: 2 |
| `gold_version` | `P3.v2`: 21, `P3.v3`: 10 |

The other two candidates are not suitable and I'd set them aside: `MLFlow_POC/data/gold_dataset.json` is 9 items with keys `query, ticker, ground_truth, expected_facts, metrics_involved` — **no sentence-level evidence IDs at all**, so it cannot support recall@k. `constants/gold_qs_constant.py` is a bare `GOLD_TEST_QUESTIONS` list of 31 question strings with no labels (and has a missing-comma bug at the second-to-last element that silently concatenates two questions into one string — worth a glance, not my business to fix).

### 4. `utilities/evaluation_metrics.py` measures *answers*, not *retrieval*

ROUGE-L, BERTScore, cosine, BLEURT, all comparing `gold_answer` to `synthesis_answer`. Nothing touches retrieved IDs. So recall@k / MRR genuinely does not exist yet — you're not duplicating anything. It does establish the house style for a metrics module (pure functions, `Dict` return, optional timing block), which I'd mirror.

### 5. `enable_variants: true` makes retrieval nondeterministic

`VariantPipeline` rephrases the query through Haiku before embedding. Same query, two runs, different variants, different hits. For an A/B of rerank-on vs rerank-off this is an uncontrolled factor sitting directly upstream of the thing you're measuring. Addressed in the experimental design section.

### 6. One discrepancy worth a glance, not elaboration

`ModelPipeline/finrag_ml_tg1/CLAUDE.md` L11-12 says the S3 Vectors index "exists but is still EMPTY" and that Stage 3 "gates all retrieval measurement." Your brief says the 614,647 vectors are live in `finrag-sentence-fact-embed-1024d`. One of the two is stale. If the index really is populated, that doc line is the thing to update; if not, Item A's harness can't run yet. Everything below is written to be correct either way.

---

# ITEM A - Retrieval telemetry + recall@k / MRR harness

## HLD

The insight that shrinks this: there is already a declared, plumbed, unused field for exactly this payload.

```
ContextMetadata.retrieval_stats : Optional[Dict]      <- models.py L78, declared
    ^ set from context_metadata.get('retrieval_stats')   <- models.py L272, wired
    ^ documented in orchestrator.py L103, L310            <- documented
    ^ build_combined_context() meta dict                  <- NEVER SETS THIS KEY
```

`meta` in `build_combined_context()` initialises `kpi_block, rag_block, kpi_entities, rag_entities, retrieval_bundle, metric_result` — no `retrieval_stats`. So the field is `None` on every response today. Populate it and the payload rides the existing rails all the way to S3:

```
run_supply_line_2_rag()                                    [existing, +2 lines]
    bundle       = retriever.retrieve(...)         S3Hits + distances
    unique_sents = expander.expand_and_deduplicate(bundle.union_hits)
    >>> telemetry = build_retrieval_telemetry(          [NEW pure function]
    >>>     query, bundle, unique_sents, stage_timings)
    context_str  = assembler.assemble(unique_sents)
    return ..., telemetry                              <- 6th tuple element

build_combined_context()                                   [existing, +1 line]
    meta["retrieval_stats"] = telemetry             <- fills the pre-built socket

           ... and from here on, zero new code required ...

create_success_response()  -> ContextMetadata.retrieval_stats   [already wired]
    -> result['metadata']['context']['retrieval_stats']
    -> QueryLogger._export_response()  -> json.dumps(result)     [already wired]
    -> s3://sentence-data-ingestion-mjs/DATA_MERGE_ASSETS/LOGS/FINRAG/responses/response_*.json
```

And separately, offline, reading those JSONs (or calling the supply line directly):

```
retrieval_metrics.py   [NEW]   telemetry dict + gold record  ->  {recall@k, mrr, ...}
notebook / script      [NEW]   loop 31 gold questions, aggregate, compare arms
```

**Deliberate choice: do not touch `QueryLogger`.** Its `_append_to_log()` is download-whole-parquet → concat one row → re-upload (L248-300), against a flat 14-column schema declared in `_empty_log_dataframe()`. Putting a variable-length list of 30 sentence IDs per query in there means (a) a nested-list Parquet column, (b) editing two methods plus the schema, and (c) that read-modify-write cost growing with every query forever. The response JSON export already gives you one immutable artifact per query with unbounded structure, for free. If you later want cheap dashboard aggregates, add **scalar** summary columns only (`n_core_hits`, `best_similarity`, `retrieval_ms`) — that's a second, separable change, and I'd defer it until you actually want the dashboard.

## LLD

### Files to ADD (2)

**`ModelPipeline/finrag_ml_tg1/rag_modules_src/utilities/retrieval_telemetry.py`**

Runs in the live path. Pure, no I/O, no AWS, no Polars. Sibling of `evaluation_metrics.py`.

```python
from typing import Any, Dict, List, Optional
from finrag_ml_tg1.rag_modules_src.rag_pipeline.models import S3Hit, SentenceRecord

def build_retrieval_telemetry(
    query: str,
    bundle: "RetrievalBundle",
    unique_sents: List[SentenceRecord],
    stage_timings_ms: Optional[Dict[str, float]] = None,
    reranked_sents: Optional[List[SentenceRecord]] = None,
    top_n_logged: int = 50,
) -> Dict[str, Any]:
    """Capture per-query retrieval provenance as a JSON-serialisable dict."""

def rank_hits_by_distance(hits: List[S3Hit]) -> List[S3Hit]:
    """Return hits sorted ascending by distance. Do NOT trust incoming order --
    S3VectorsRetriever._proportional_topk() returns filtered+global concatenated,
    not globally sorted."""
```

**`ModelPipeline/finrag_ml_tg1/rag_modules_src/utilities/retrieval_metrics.py`**

Offline scoring. Pure functions on ID lists; no AWS, no pipeline imports. Kept separate from telemetry because it depends on the gold set and never runs in the serving path.

```python
from typing import Any, Dict, List, Optional, Sequence

def recall_at_k(ranked_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    """|retrieved@k ∩ relevant| / |relevant|. Returns 0.0 if relevant is empty."""

def reciprocal_rank(ranked_ids: Sequence[str], relevant_ids: Sequence[str]) -> float:
    """1 / (1-based rank of first relevant id); 0.0 if none present."""

def hit_at_k(ranked_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    """1.0 if any relevant id appears in the top k."""

def score_query(
    telemetry: Dict[str, Any],
    gold_record: Dict[str, Any],
    ks: Sequence[int] = (1, 3, 5, 10, 20, 30),
) -> Dict[str, Any]:
    """Score one query at all three pipeline stages. Reads
    gold_record['evidence_sentence_ids'] and gold_record['retrieval_scope']."""

def aggregate(
    per_query: List[Dict[str, Any]],
    group_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Mean each metric, overall and optionally stratified (e.g. 'retrieval_scope').
    Include n per cell so small-cell noise is visible in the output itself."""

def paired_delta(
    arm_a: List[Dict[str, Any]],
    arm_b: List[Dict[str, Any]],
    metric: str,
    n_boot: int = 10_000,
    seed: int = 0,
) -> Dict[str, Any]:
    """Per-question paired difference b - a, joined on question_id.
    Returns mean delta, bootstrap 95% CI over questions, n_better/n_worse/n_tied."""
```

### Files to TOUCH (1)

**`rag_modules_src/synthesis_pipeline/supply_lines.py`** — the only existing file.

| location | change |
| :-- | :-- |
| imports (~L44) | `+1` line: import `build_retrieval_telemetry` |
| `run_supply_line_2_rag()` L206-240 | wrap the 3 existing stage calls in `time.perf_counter()`; build telemetry; add it as a 6th tuple element. Return type `Tuple[str, Any, Any, List[Any], str]` → `Tuple[str, Any, Any, List[Any], str, Dict[str, Any]]` |
| `build_combined_context()` L295 | unpack 6 instead of 5; `meta["retrieval_stats"] = telemetry` |

**Blast radius of the return-signature change.** I checked: `run_supply_line_2_rag` is called from `build_combined_context` in the same file, and that's the only production caller. Notebooks under `validation_notebooks/` may unpack it — appending to the end of the tuple is the least-breaking shape (a 5-tuple unpack raises `ValueError: too many values`, so any breakage is loud and immediate, not silent). If even that is unwelcome, the alternative is to return a small dataclass — but that's a bigger diff for no measurement benefit, so I wouldn't.

**Zero changes needed to:** `orchestrator.py`, `synthesis_pipeline/models.py`, `query_logger.py`, `s3_retriever.py`, `sentence_expander.py`, `context_assembler.py`, `ml_config_loader.py`, `ml_config.yaml`.

### Telemetry payload shape

```json
{
  "schema_version": 1,
  "query": "What operational or supply chain risks does Walmart...",
  "variant_queries": ["...", "..."],
  "timings_ms": {"embed": 210.4, "retrieve": 1840.2, "expand": 620.9,
                 "rerank": null, "assemble": 12.1, "sl2_total": 2683.6},
  "counts": {"filtered_hits": 22, "global_hits": 8, "union_hits": 30,
             "expanded_sents": 168, "core_sents": 30, "reranked_sents": null},
  "core_hits": [
    {"rank": 1, "sentence_id": "0000104169_10-K_2011_section_1A_47",
     "distance": 0.284, "similarity": 0.858, "sources": ["filtered"],
     "variant_ids": [0], "cik_int": 104169, "report_year": 2011,
     "section_name": "ITEM_1A", "sentence_pos": 47}
  ],
  "expanded_sentence_ids": ["...", "..."],
  "reranked_sentence_ids": null
}
```

Notes on specific fields, because each one is load-bearing for a metric:

- `rank` is 1-based and assigned **after** `rank_hits_by_distance()`, for the reason in §1 above.
- `similarity` mirrors `S3Hit.similarity_score()` = `max(0.0, 1.0 - distance/2.0)`. Store both it and `distance` — cheap, and it saves you re-deriving the convention when reading logs in six months.
- `sources` / `variant_ids` are Python `set`s on `S3Hit`; **cast to sorted lists** or `json.dumps` in `_export_response` will raise `TypeError: Object of type set is not JSON serializable`. This is the single most likely thing to break on first run.
- Three ID lists, not one, because they answer three different questions (§Metric design below).
- `expanded_sentence_ids` is up to ~200 strings ≈ 8 KB per query. Fine for a per-query JSON; would not be fine as a Parquet column appended to a growing file, which is the other half of the reason for not touching `QueryLogger`.

### Pseudocode — telemetry capture

*Illustration of the pattern, not an implementation.*

```python
# retrieval_telemetry.py
def build_retrieval_telemetry(query, bundle, unique_sents,
                              stage_timings_ms=None, reranked_sents=None,
                              top_n_logged=50):
    ranked = rank_hits_by_distance(bundle.union_hits)      # DO NOT trust list order

    core_hits = []
    for rank, hit in enumerate(ranked[:top_n_logged], start=1):
        core_hits.append({
            "rank": rank,
            "sentence_id": hit.sentence_id,
            "distance": round(hit.distance, 6),
            "similarity": round(hit.similarity_score(), 6),
            "sources": sorted(hit.sources),          # set -> list, JSON safety
            "variant_ids": sorted(hit.variant_ids),  # set -> list
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
            "global_hits":   len(bundle.global_hits),
            "union_hits":    len(bundle.union_hits),
            "expanded_sents": len(unique_sents),
            "core_sents":    sum(1 for s in unique_sents if s.is_core_hit),
            "reranked_sents": len(reranked_sents) if reranked_sents else None,
        },
        "core_hits": core_hits,
        "expanded_sentence_ids": [s.sentence_id for s in unique_sents],
        "reranked_sentence_ids": (
            [s.sentence_id for s in reranked_sents] if reranked_sents else None),
    }
```

```python
# supply_lines.py :: run_supply_line_2_rag  -- the +2 lines, in context
    t = {}
    t0 = time.perf_counter()
    base_embedding = rag.embedder.embed_query(query, entities)
    t["embed"] = (time.perf_counter() - t0) * 1000
    # ... same wrap around retrieve / expand / assemble ...

    telemetry = build_retrieval_telemetry(query, bundle, unique_sents, t)
    return context_block, entities, bundle, unique_sents, context_str, telemetry
```

### Metric design — and the part that decides whether the experiment means anything

**Score at three stages, not one.** They measure different components and only one of them can be improved by a reranker:

| stage | ranked ID list | what it measures |
| :-- | :-- | :-- |
| **core** | `core_hits` sorted by distance | the ANN retriever + metadata filters, alone |
| **expanded** | `expanded_sentence_ids` | what a hit-free-but-adjacent gold sentence gets rescued by; the ±3 window's contribution |
| **reranked** | `reranked_sentence_ids` | what the LLM actually sees after pruning |

The `expanded` stage exists because your gold evidence is a *single specific sentence* while your pipeline retrieves a *neighbourhood*. A gold sentence at `sentence_pos` 47 is "found" if the retriever hit `pos` 45 and the ±3 window pulled it in — that is a genuine success of the system as designed, and core-only recall would score it as a miss. Report both; the gap between them *is* the measured value of window expansion, which is a result you don't currently have.

**Now the thing that will otherwise cost you a wasted week.** Reranking cannot improve recall@K when it prunes down to K from a candidate pool of K. Formally: if the reranker selects a subset S of the candidate set C, then `recall@|C|(S) ≤ recall@|C|(C)` always. Pruning is monotone-non-increasing in recall at the full cutoff.

So:
- `recall@30` measured on the post-rerank set will be **flat or worse**, by construction. If you measure that and nothing else, you will correctly observe no improvement and incorrectly conclude the reranker is useless.
- What a cross-encoder actually buys you is **rank quality at small k** and **precision at a fixed context budget**. The metrics that should move are `MRR`, `recall@1/3/5`, and (context tokens at equal recall).
- Report `ks = (1, 3, 5, 10, 20, 30)`. State in advance that `recall@30` is the *control* — expected flat — and MRR / `recall@5` are the *treatment* metrics. Writing that down before you run is what makes the result interpretable rather than post-hoc.

**Statistical power — 31 questions is small, and I'd rather you know the number than discover it.** For a proportion metric near 0.7, the standard error on a single arm is `sqrt(0.7·0.3/31) ≈ 0.082`. A 0.71 → 0.77 move is comfortably inside noise. Two consequences:

1. **Never compare two independently-computed means.** Compare **paired per-question deltas** on the same 31 questions — pairing removes the between-question variance, which dominates here. `paired_delta()` above exists for this.
2. Report `n_better / n_worse / n_tied` alongside the mean. With n=31 that count is often more legible than a CI, and a sign test on it is honest. "MRR +0.06, 14 better / 3 worse / 14 tied" is a real finding. "MRR 0.71 → 0.77" on its own is not.

Also: with `len(evidence_sentence_ids) == 1` for 24/31 questions, `recall@k` degenerates to `hit@k` on most of the set. That's fine — just don't present them as two independent pieces of evidence.

**Stratify by `retrieval_scope`.** The mechanism prediction is that reranking helps most where many candidates compete on similar embeddings — i.e. `cross_company` (3 q) and `cross_year` (4 q), not `local` (24 q). But 3 and 4 are descriptive-only cell sizes. Report them as *direction of effect*, explicitly labelled n=3 / n=4, never as a significance claim.

### Running the harness without paying for synthesis

The natural instinct is `answer_query_batch()` (`orchestrator.py` L392) — its docstring even says "Useful for evaluation harness (P3 gold set)." I'd push back on that for *retrieval* measurement. It runs Bedrock synthesis per query, which adds 30-50s and ~$0.017 each (31 q ≈ 20-25 min, ≈ $0.53 per arm), and it conflates retrieval failure with synthesis failure. Neither is what you're measuring.

Call the supply line directly instead:

```python
# harness, illustrative
rag = init_rag_components()                      # once
for gq in gold:                                  # 31 questions
    *_, telemetry = run_supply_line_2_rag(gq["question_text"], rag)
    rows.append(score_query(telemetry, gq))
print(aggregate(rows, group_by="retrieval_scope"))
```

Retrieval-only, seconds per query, no LLM cost. Use `answer_query_batch()` separately when you want end-to-end answer quality via `evaluation_metrics.py` — that's a different experiment with a different cost profile, and keeping them separate is what lets you attribute a regression.

**Control the variant confound.** `enable_variants: true` in `ml_config.yaml` puts a nondeterministic Haiku call upstream of retrieval. Two options:
- **Simplest and what I'd do first:** run both arms with `enable_variants: false`. You lose a little absolute recall but the comparison becomes clean and cheap. Then, if the reranker wins, re-run once with variants on to confirm the effect survives.
- **If variants must stay on:** generate variants once per gold question, persist them, and inject the same variant list into both arms. This means a seam in `VariantPipeline` you don't currently have. More faithful, more work; I'd only pay for it if arm-1 shows a real effect.

---

# ITEM B - Cohere Rerank 3.5 via Bedrock

## Verified external API facts

All of the following I confirmed against AWS docs today rather than from training data, since you flagged it as a live API. Where a source disagreed with a third-party page I took the AWS page.

| fact | value |
| :-- | :-- |
| Model ID | `cohere.rerank-v3-5:0` |
| Model ARN form | `arn:aws:bedrock:{region}::foundation-model/cohere.rerank-v3-5:0` (no account ID) |
| boto3 client | **`bedrock-agent-runtime`** — *not* `bedrock-runtime` |
| Method | `client.rerank(...)` |
| `queries` | Array, **fixed number of 1 item** |
| `sources` | Array, **min 1, max 1000 items** |
| Response | `{"results": [{"index": int, "relevanceScore": float, "document": {...}}], "nextToken": str}` |
| `relevanceScore` | normalised, `[0, 1]`, higher = better |
| Model context window | **4K tokens** |
| Pagination | `nextToken` on both request and response |
| Pricing | **$2.00 per 1,000 queries**, on-demand |
| Billing unit | *"A query is a single call to the reranker model that can contain up to 100 document chunks."* CloudWatch metric: `SearchUnits` |
| IAM | needs **both** `bedrock:Rerank` and `bedrock:InvokeModel` (scoped to the rerank model ARN). Third-party model ⇒ also `aws-marketplace:ViewSubscriptions` + `aws-marketplace:Subscribe` |
| Regions (in-region) | us-east-1, us-west-2, ca-central-1, eu-central-1, ap-northeast-1. No Geo/Global cross-region routing. |
| Service tiers | Standard only (no Priority / Flex / Reserved) |

Three of these have direct design consequences and are easy to get wrong:

1. **`bedrock-agent-runtime`, not `bedrock-runtime`.** `MLConfig.get_bedrock_client()` returns a `bedrock-runtime` client and will fail with `AttributeError: 'BedrockRuntime' object has no attribute 'rerank'` if you reuse it. The model card lists `Invoke` as a supported endpoint too, but the `rerank()` convenience operation lives on the agent-runtime client and is the documented path.
2. **Billing is per-100-chunks, not per-call.** 1000 sources in one call = 10 `SearchUnits` = $0.02, not $0.002. This makes granularity a *cost* decision, not just a quality one.
3. **4K token context.** Ample for a ±3-sentence block; would be a real constraint if you ever reranked whole 10-K sections.

## HLD — where it goes, and why not where you'd expect

The retrieval tail, verified from `supply_lines.py` L206-240 (`graphify path` confirms `S3VectorsRetriever --shares_data_with--> SentenceExpander --shares_data_with--> ContextAssembler`):

```
embedder.embed_query -> filter_builder.build_filters
    -> retriever.retrieve()                -> RetrievalBundle (<=30 S3Hit, has NO text)
    -> expander.expand_and_deduplicate()   -> List[SentenceRecord] (HAS .text)
    >>> INSERT HERE
    -> assembler.assemble()                -> str
```

**Insertion point: between `expand_and_deduplicate()` and `assemble()`.** One line in `run_supply_line_2_rag()`.

Why not the other candidate — reranking `bundle.union_hits` right after `retrieve()`, which is where a textbook two-stage retriever puts it? Because `S3Hit` carries no sentence text. Check `_parse_response()` (`s3_retriever.py` L407-454): the S3 Vectors metadata gives you `sentenceID`, `embedding_id`, `cik_int`, `report_year`, `section_name`, `sic`, `sentence_pos`, `section_sentence_count` — and no `sentence`. A cross-encoder needs the text. Reranking pre-expansion therefore means a *second* Parquet join purely to fetch text, duplicating the join `SentenceExpander` is about to do anyway. That's a new data-access path, a new `DataLoader` dependency inside the reranker, and roughly double the I/O — the opposite of surgical. I ruled it out on those grounds, not on quality grounds.

Post-expansion the text is already in hand and the reranker needs **zero data access**: pure function of its inputs plus one AWS call.

### Granularity: rerank blocks, not sentences

Individually reranking each of ~170 `SentenceRecord`s would be wrong twice over. Quality: a lone sentence is a thin, context-free unit for a cross-encoder, and it discards the `is_core_hit` / neighbour structure the expander deliberately built. Cost: ~170 chunks = 2 `SearchUnits` instead of 1. And it would shred the ±3 windows, feeding the LLM a bag of disconnected sentences — actively worse context than today.

So group first, into contiguous runs of `(cik_int, report_year, section_name, doc_id)` with adjacent `sentence_pos`, rerank the runs, prune, flatten back. Realistically 10-25 such blocks from 30 hits with a ±3 window — comfortably one `SearchUnit`, and each block is a coherent paragraph-sized passage.

**And this is where `ContextBlock` earns its keep.** It already has exactly the right fields — `text`, `sentence_ids`, `base_score`, `final_score`, `core_hit_count`, `block_key()` — and its docstring literally says *"ready for reranking and assembly"* and *"final_score: Score after hybrid reranking"*. Someone designed for this and stopped. Use it as a **transient internal type inside `reranker.py`**, built from `SentenceRecord`s and discarded on the way out. Do **not** promote it to a pipeline-boundary type: it is currently dead in the live path (referenced only by its own definition and `sentence_expander_contract.py`, which is a design note), and threading it through `expander → reranker → assembler` would mean changing three modules' signatures. The whole point is that the reranker's public signature is `List[SentenceRecord] -> List[SentenceRecord]` and nothing else in the pipeline knows it exists.

One consequence of §2 to keep in view: because `assemble()` re-sorts into document order, the *order* the reranker returns is irrelevant. Only the *membership* of the returned list matters. Which means the pruning policy is the entire design surface of this feature.

### Feature flag

`MLConfig.get_retrieval_config()` (L659-674) does `return self.cfg["retrieval"]` — the **raw dict, no key whitelist**. So nesting rerank keys under the existing `retrieval:` block means new config flows through with **zero changes to `ml_config_loader.py`**. That's the cheapest possible flag.

```yaml
# .aws_config/ml_config.yaml, appended inside the existing `retrieval:` block
retrieval:
  # ... existing 16 keys unchanged ...
  enable_reranking: false          # master switch, OFF by default
  rerank_model_id: "cohere.rerank-v3-5:0"
  rerank_top_n_blocks: 8           # blocks kept (null => keep all, score-only mode)
  rerank_min_score: 0.0            # drop blocks below this relevanceScore
  rerank_max_sources: 100          # stay inside one SearchUnit; hard API cap is 1000
  rerank_cost_per_1k_queries: 2.00
```

Flag semantics I'd argue for: when `enable_reranking` is false, `init_rag_components()` sets `RAGComponents.reranker = None` and `run_supply_line_2_rag()` skips the call entirely — no client constructed, no import cost, no AWS credential path exercised. Cheaper and more honest than instantiating a reranker that no-ops, and it means a misconfigured rerank block cannot break the flag-off path.

No hardcoded resource names: model ID and region come from config (`region` via the existing `MLConfig.region`), ARN is composed at runtime.

## LLD

### Files to ADD (1)

**`rag_modules_src/rag_pipeline/reranker.py`** — currently a 0-byte placeholder, so this fills an existing slot rather than adding a file.

```python
import logging
from typing import Any, Dict, List, Optional

import boto3

from finrag_ml_tg1.rag_modules_src.rag_pipeline.models import ContextBlock, SentenceRecord

logger = logging.getLogger(__name__)


class CohereReranker:
    """Cross-encoder reranking of expanded sentence blocks via the Bedrock Rerank API.

    Groups SentenceRecords into contiguous blocks, scores each against the query
    with cohere.rerank-v3-5:0, prunes to the top N, and returns the surviving
    SentenceRecords. Degrades gracefully: any failure returns the input unchanged.
    """

    def __init__(
        self,
        retrieval_config: Dict[str, Any],
        region: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        client: Optional[Any] = None,      # injectable for tests
    ) -> None: ...

    def rerank(
        self,
        query: str,
        sentences: List[SentenceRecord],
    ) -> List[SentenceRecord]:
        """Single public entry point. Returns a pruned list, or `sentences`
        unchanged if reranking is disabled, unnecessary, or fails."""

    # --- internals ---
    def _group_into_blocks(self, sentences: List[SentenceRecord]) -> List[ContextBlock]: ...
    def _call_rerank(self, query: str, texts: List[str]) -> List[Dict[str, Any]]: ...
    def _select(self, blocks: List[ContextBlock]) -> List[ContextBlock]: ...
    def _flatten(self, blocks, by_id: Dict[str, SentenceRecord]) -> List[SentenceRecord]: ...
    def last_call_stats(self) -> Dict[str, Any]:
        """Blocks in/out, sentences in/out, search_units, est_cost_usd, latency_ms.
        Consumed by Item A's telemetry."""
```

Constructor mirrors `S3VectorsRetriever.__init__` deliberately — same `(retrieval_config, aws_*, region)` shape, and it builds its own boto3 client internally, exactly as `S3VectorsRetriever` does for `s3vectors` (L125-130). That precedent is why **`MLConfig` needs no new method**: no `get_bedrock_agent_runtime_client()`, no touch to `ml_config_loader.py`.

### Files to TOUCH (2 — one code, one config)

**`rag_modules_src/synthesis_pipeline/supply_lines.py`** — same file as Item A. Four small edits:

| location | change |
| :-- | :-- |
| imports (~L44) | `+1`: import `CohereReranker` |
| `RAGComponents` L52-61 | `+1` field: `reranker: Optional[CohereReranker] = None` (defaulted ⇒ existing constructions keep working) |
| `init_rag_components()` after L118 | `+4`: if `retrieval_cfg.get("enable_reranking")`, construct from `retrieval_cfg` + `config.region` + creds; else `None`. Add to the returned dataclass. |
| `run_supply_line_2_rag()` L225-228 | `+3`: between `expand_and_deduplicate` and `assemble`, call `rag.reranker.rerank(...)` if `rag.reranker` |

**`.aws_config/ml_config.yaml`** — the 6 keys above appended inside `retrieval:`. Config, not code.

### Explicit flag: what my design touches beyond new modules

You asked me to call this out. Full accounting:

| item | new files | existing code files | config files |
| :-- | :-- | :-- | :-- |
| A | 2 (`retrieval_telemetry.py`, `retrieval_metrics.py`) | **1** (`supply_lines.py`) | 0 |
| B | 1 (`reranker.py`, currently 0 bytes) | **1** (`supply_lines.py` — same file) | 1 (`ml_config.yaml`) |
| **combined** | **3** | **1** | **1** |

One existing code file for both items. I don't think it goes lower without giving something up, and here is the honest accounting of the two "even simpler" options I considered and rejected:

- **Skip Item A's `supply_lines.py` edit; parse the exported context `.txt` files instead.** Genuinely fewer files touched — zero. Rejected because `context_*.txt` contains formatted prose with `=== ... Sentences: X - Y ===` headers; you would be regex-reconstructing sentence IDs from a display format, with no distances and no ranks at all. MRR would be unrecoverable. Losing the primary metric to save a two-line diff is a bad trade.
- **Skip Item B's `RAGComponents` field; construct the reranker inside `run_supply_line_2_rag()` on demand.** One fewer edit *hunk*, same file count. Rejected because it builds a boto3 client on every query (`init_rag_components()` exists precisely to hoist that out) and breaks the composition-root pattern your codebase is consistent about. Worse per-query latency for a cosmetically smaller diff.

I did also find a real simplification, which is the Item A one: **not touching `QueryLogger` at all** and letting the payload ride `_export_response`. That's what keeps Item A at a single existing file.

### Pseudocode — reranker core

*Illustration of the pattern, not an implementation.*

```python
def rerank(self, query, sentences):
    if not self.enabled or len(sentences) < 2:
        return sentences

    t0 = time.perf_counter()
    try:
        blocks = self._group_into_blocks(sentences)          # ~10-25 blocks
        if len(blocks) <= 1:
            return sentences

        if len(blocks) > self.max_sources:                   # cost guard, not API limit
            blocks.sort(key=lambda b: -b.base_score)         # best-embedding-score first
            blocks = blocks[: self.max_sources]
            logger.warning("Truncated to %d blocks before rerank", self.max_sources)

        results = self._call_rerank(query, [b.text for b in blocks])
        for r in results:
            blocks[r["index"]].final_score = r["relevanceScore"]   # the dead field, alive

        kept = self._select(blocks)
        by_id = {s.sentence_id: s for s in sentences}
        out = self._flatten(kept, by_id)

        self._stats = {
            "blocks_in": len(blocks), "blocks_kept": len(kept),
            "sents_in": len(sentences), "sents_out": len(out),
            "search_units": math.ceil(len(blocks) / 100),      # billing unit, verified
            "est_cost_usd": math.ceil(len(blocks) / 100) * self.cost_per_1k / 1000,
            "latency_ms": (time.perf_counter() - t0) * 1000,
        }
        logger.info("Rerank: %d blocks -> %d kept, %d -> %d sentences, %.0f ms",
                    len(blocks), len(kept), len(sentences), len(out),
                    self._stats["latency_ms"])
        return out

    except Exception as e:
        # Same graceful-degradation contract as S3VectorsRetriever: never break the query
        logger.error("Reranking failed, passing through unreranked: %s", e, exc_info=True)
        return sentences


def _group_into_blocks(self, sentences):
    # sort by (cik_int, report_year, section_name, doc_id, sentence_pos)
    # start a new block when the group key changes OR sentence_pos is not contiguous
    # per block: text = "\n".join(s.text), sentence_ids ordered,
    #            base_score = max(similarity from parent_hit_distance),
    #            core_hit_count = sum(is_core_hit)
    ...


def _call_rerank(self, query, texts):
    model_arn = f"arn:aws:bedrock:{self.region}::foundation-model/{self.model_id}"
    resp = self.client.rerank(
        queries=[{"type": "TEXT", "textQuery": {"text": query}}],   # exactly 1
        sources=[
            {"type": "INLINE",
             "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": t}}}
            for t in texts                                          # 1..1000
        ],
        rerankingConfiguration={
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "modelConfiguration": {"modelArn": model_arn},
                "numberOfResults": len(texts),   # score all; prune locally in _select
            },
        },
    )
    return resp["results"]      # [{"index": i, "relevanceScore": s, "document": {...}}]


def _select(self, blocks):
    scored = [b for b in blocks if b.final_score >= self.min_score]
    scored.sort(key=lambda b: -b.final_score)
    return scored[: self.top_n] if self.top_n else scored
```

Two details in there worth naming, because both are easy to get wrong:

- **`numberOfResults=len(texts)`, then prune locally.** Asking the API for all scores and cutting in `_select()` costs exactly the same (billing is per-100-chunks-submitted, not per-result-returned) and gives you the full score distribution in telemetry. That distribution is what tells you whether `rerank_top_n_blocks: 8` is the right cut — you can't tune a threshold you never observed. Pushing `numberOfResults` down to 8 would save nothing and blind you.
- **`results[i]["index"]` indexes into your submitted `sources` array**, and results come back score-ordered, not input-ordered. `blocks[r["index"]].final_score = ...` is correct; `zip(blocks, results)` is a silent scrambling bug that will look like "the reranker made things randomly worse."

### Cost — and this is the argument that matters for a cost-over-latency project

Direct rerank cost, from the verified billing rule (query = up to 100 chunks, $2.00 / 1,000 queries):

| granularity | chunks | SearchUnits | cost/query |
| :-- | :-- | :-- | :-- |
| **blocks** (recommended) | 10-25 | 1 | **$0.002** |
| sentences | ~170 | 2 | $0.004 |
| pathological (1000 cap) | 1000 | 10 | $0.020 |

Against your stated ~$0.017/query baseline, block-level reranking is +$0.002 ≈ **+12%**.

But that's only the gross figure, and there's an offset that may well dominate. `serving_models` puts Haiku 4.5 at `cost_per_1k_input: 0.001`. Pruning context is therefore worth $0.001 per 1,000 input tokens removed:

| pruning | input tokens saved (est.) | LLM saving | rerank cost | net |
| :-- | :-- | :-- | :-- | :-- |
| none (score-only) | 0 | $0 | $0.002 | **+$0.002** |
| keep top 8 of ~20 blocks (~40% cut) | ~4,000 | $0.004 | $0.002 | **−$0.002** |
| keep top 5 (~60% cut) | ~6,000 | $0.006 | $0.002 | **−$0.004** |

So reranking-as-pruner is plausibly **cost-negative** — it can pay for itself and then some. That reframes it against your `CLAUDE.md` rule *"DO NOT propose latency optimizations that increase cost"*: this isn't a latency optimization at all, it's a quality change that may reduce cost.

**Label that table honestly: the token counts are ESTIMATES, not measurements.** I back-derived ~10,000 input tokens/query from your $0.017 total and the configured Haiku rates. I did not measure it. You can settle it exactly in one query, because `query_logs.parquet` already carries an `input_tokens` column (`_empty_log_dataframe()`, L630):

```python
QueryLogger().get_recent_logs(n=200).select(["input_tokens", "cost", "context_length"]).describe()
```

That is the first thing I'd check before committing to a pruning target — it converts the whole table from estimate to fact.

Latency: one extra sequential API call. I do **not** have a verified p50 for Bedrock Rerank 3.5 and won't invent one; measure it via `last_call_stats()["latency_ms"]` on the first run. Directionally it's a single small-payload inference call against a 30-50s end-to-end baseline, so I'd expect it to be lost in the noise, and any input-token reduction pulls the *other* way (less to prefill). Treat "negligible" as a hypothesis your own telemetry tests, not a claim from me.

## The ablation the two items enable together

Item A instruments; Item B is the treatment. Once both exist, the same 31 questions give you a clean 3-arm comparison, and the arms are chosen so each isolates one factor:

| arm | config | isolates |
| :-- | :-- | :-- |
| A0 baseline | `enable_reranking: false` | current system |
| A1 score-only | `true`, `rerank_top_n_blocks: null` | rerank quality with **membership held fixed** — recall is provably unchanged, so any MRR/score-distribution signal is pure ranking quality, uncontaminated by pruning |
| A2 prune | `true`, `rerank_top_n_blocks: 8` | the cost/quality trade at a real context budget |

A1 is the arm people skip and shouldn't. It separates *"can the cross-encoder tell good blocks from bad ones on 10-K prose"* from *"is my pruning threshold well chosen"* — two failure modes with completely different fixes, which a single A0-vs-A2 comparison fuses into one uninterpretable number. If A1 shows the reranker's scores don't correlate with gold evidence position, no pruning threshold will save you and you stop there, having spent almost nothing.

Hold `enable_variants` constant across all three arms (see §5). All three arms with variants off is the cheap, clean version.

---

## How I was reasoning

**What I noticed first**, and why it was the thing to notice: I grepped `retrieval_stats` expecting to find a populated field to extend, and found four references — a declaration, a read, and two docstrings — with **no writer anywhere**. That single fact collapsed Item A from "design a telemetry system" to "fill in a socket someone already wired," and it's the reason the file-touch count is 1 instead of 4. I look for this pattern early on any "add instrumentation" task: half-built plumbing is common in codebases that grew fast, and finding it is worth more than any design cleverness.

**What I ruled out immediately, and on what grounds:**
- *Extending `QueryLogger`'s Parquet schema* — its append is read-whole-file/concat/rewrite against a flat 14-column schema. A nested list column there is both a schema change and a permanent per-query cost that grows with history. And `_export_response()` already persists arbitrary nesting for free. Ruled out on cost-shape, not taste.
- *Reranking `bundle.union_hits` pre-expansion* — the textbook position, but `_parse_response()` shows `S3Hit` has no text field, so it needs a Parquet join that `SentenceExpander` is about to perform anyway. Ruled out on duplicated I/O.
- *Promoting `ContextBlock` to a pipeline type* — it's dead in the live path, so this is a three-module signature change. Ruled out on blast radius, while keeping the dataclass as an internal.
- *`answer_query_batch()` as the harness* — its own docstring recommends it for the P3 gold set, and I still think it's the wrong tool for *retrieval* measurement: it pays for synthesis you aren't measuring and confounds two failure modes. Ruled out on confound, not cost.
- *A new `MLConfig.get_bedrock_agent_runtime_client()`* — unnecessary once I saw `S3VectorsRetriever` builds its own `s3vectors` client from passed-in credentials. Following the existing precedent saved a file.

**The heuristic I actually used, stated plainly:** for a minimal-footprint addition, find the narrowest point in the data flow where all the information you need is *already in scope in one local variable*, and put everything there. For both items that point is the same three lines of `run_supply_line_2_rag()` — `bundle`, `unique_sents`, and `query` are all live and in scope simultaneously, exactly once, in the whole codebase. Anywhere earlier and you lack text; anywhere later and the sentences have been flattened into an unparseable string. That's not elegance, it's just where the information is.

**Where I was uncertain and what I checked.** I did not trust myself on the Bedrock Rerank shape — the `bedrock-agent-runtime` vs `bedrock-runtime` distinction is exactly the kind of thing training data gets wrong, and the per-100-chunks billing rule is a detail I would not have guessed (I'd have assumed per-call). Both came from AWS docs today. I also didn't trust the gold set's ID format, so I ran the join: 45/45 resolve. That check is what makes the whole harness design safe to build on — if the IDs hadn't matched I'd be writing you a normalisation-layer design instead.

**Where I'd guess but you should check:** the 10-25 block count. It follows from 30 hits × ±3 window with overlap merging, but overlap depends on how clustered hits are within a section, which is query-dependent. If it comes out above 100 you cross into a second `SearchUnit` and the cost doubles — hence `rerank_max_sources` as a guard rather than trusting the estimate. Log `blocks_in` from the first run and you'll know within one query.

## Confidence and gaps

**Well-established (verified against AWS documentation today):** every row of the Item B API table — model ID, `bedrock-agent-runtime` client, `rerank()` method, `queries` fixed at 1, `sources` 1-1000, response `results[].index`/`relevanceScore`, `nextToken`, 4K context, $2.00/1,000 queries, the "up to 100 document chunks per query" billing rule, `SearchUnits` CloudWatch metric, the `bedrock:Rerank` + `bedrock:InvokeModel` IAM pair, marketplace permissions, and the five in-region availability zones.

**Verified against this repo (I read or ran it):** `retrieval_stats` declared-but-never-written; `_proportional_topk()` returning unsorted concatenation; `ContextAssembler._sort_sentences()` having no score term; `ContextBlock`/`final_score` absent from the live path; `S3Hit` carrying no text; `get_retrieval_config()` returning the raw dict; `S3VectorsRetriever` building its own boto3 client; `evaluation_metrics.py` scoring answers only; the full gold schema and its four field distributions; **45/45 gold evidence IDs resolving in `finrag_fact_sentences.parquet`**; `serving_models` Haiku rates; the current 16-key `retrieval:` block.

**My judgement, not fact — argue with any of it:**
- Block-level over sentence-level granularity. Rests on a quality claim about cross-encoders on short inputs that I believe but have not measured *on your corpus*.
- The three-stage (core / expanded / reranked) metric decomposition.
- `rerank_top_n_blocks: 8` as a starting value. A guess to be tuned from the observed score distribution, nothing more.
- The three-arm ablation, and specifically that A1 (score-only) is worth its own run.
- That reranking is better framed as pruning than reordering *here*. This follows from §2, so it's fairly firm — but it is a claim about your architecture, not about reranking in general.

**UNVERIFIED — do not build on these without checking:**
- **Bedrock Rerank 3.5 latency.** No figure, refused to invent one. Measure it.
- **~10,000 input tokens/query.** Back-derived from $0.017 and the configured rates. The whole net-cost table depends on it. Settle it with the `input_tokens` column in `query_logs.parquet`.
- **10-25 blocks from 30 hits.** Reasoned, not measured.
- **Whether the S3 Vectors index is actually populated.** Your brief and `finrag_ml_tg1/CLAUDE.md` L11-12 disagree. Item A cannot run against an empty index.
- **Whether `bedrock:Rerank` is usable on account `mjsushanth_mlops` right now.** Cohere is a third-party model, so it needs marketplace subscription in addition to model access. `AdministratorAccess` covers the IAM actions but does *not* auto-create the marketplace subscription. Untested here — and given the Cohere Embed V4 daily-cap surprise documented in your `CLAUDE.md`, I would probe with one two-document call before designing around it.
- **Whether any notebook unpacks `run_supply_line_2_rag()`'s 5-tuple.** I confirmed `build_combined_context` is the only *production* caller; I did not scan every notebook cell. Appending to the tuple end fails loudly if so.

## Sources

- Amazon Bedrock User Guide — *Rerank 3.5 model card* (model ID `cohere.rerank-v3-5:0`, 4K context, endpoints, regions, service tiers, boto3 sample). https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-cohere-rerank-3-5.html
- Amazon Bedrock API Reference — *Rerank* (`bedrock-agent-runtime`; request/response syntax; `queries` fixed 1 item; `sources` min 1 / max 1000; `nextToken`; `results[].index` / `relevanceScore`). https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Rerank.html
- Amazon Bedrock User Guide — *Improve the relevance of query responses with a reranker model*. https://docs.aws.amazon.com/bedrock/latest/userguide/rerank.html
- Amazon Bedrock User Guide — *Pricing and search units* (verbatim: "A query is a single call to the reranker model that can contain up to 100 document chunks"; `SearchUnits` CloudWatch metric). https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-pricing.html
- Amazon Bedrock User Guide — *Permissions for reranking* (`bedrock:Rerank` + `bedrock:InvokeModel`; `aws-marketplace:ViewSubscriptions` / `Subscribe` for third-party models). https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-prereq.html
- Amazon Bedrock Pricing page — Rerank 3.5 at "$2.00" per "1,000 queries", on-demand. https://aws.amazon.com/bedrock/pricing/
- AWS ML Blog — *Cohere Rerank 3.5 is now available in Amazon Bedrock through Rerank API* (boto3 `rerank()` parameter dict). https://aws.amazon.com/blogs/machine-learning/cohere-rerank-3-5-is-now-available-in-amazon-bedrock-through-rerank-api

In-repo references (paths relative to `FinSights/`): `ModelPipeline/finrag_ml_tg1/rag_modules_src/synthesis_pipeline/supply_lines.py` (L52-129 `RAGComponents`/`init_rag_components`, L171-240 `run_supply_line_2_rag`, L249-318 `build_combined_context`); `.../synthesis_pipeline/models.py` (L61-82 `ContextMetadata`, L266-273 `create_success_response`); `.../synthesis_pipeline/query_logger.py` (L88-186 `log_query`, L217-245 `_export_response`, L248-300 `_append_to_log`, L622-639 `_empty_log_dataframe`); `.../rag_pipeline/s3_retriever.py` (L388-454 `_parse_response`, L458-520 `_deduplicate_hits`, L524-634 `_proportional_topk`); `.../rag_pipeline/models.py` (L34-69 `S3Hit`, L170-237 `ContextBlock`, L280-309 `SentenceRecord`); `.../rag_pipeline/context_assembler.py` (L138-250 `assemble`/`_sort_sentences`); `.../rag_pipeline/sentence_expander.py` (L152 `expand_and_deduplicate`); `.../loaders/ml_config_loader.py` (L458-515 client factories, L659-674 `get_retrieval_config`); `.../utilities/evaluation_metrics.py`; `.../data_cache/qa_manual_exports/goldp3_analysis/p3_gold_test_suite_31q.json`; `.../data_cache/stage1_facts/finrag_fact_sentences.parquet`; `ModelPipeline/finrag_ml_tg1/.aws_config/ml_config.yaml`.

## What I would do next, and what I would leave to you

**Ordered by leverage — each step's result changes whether the next one is worth doing:**

1. **Resolve the empty-index contradiction** (§6). Everything downstream is blocked on it and it's a one-command check.
2. **Probe `bedrock:Rerank` with a two-document call** before writing any of `reranker.py`. Third-party marketplace subscription is the likely snag and you have a documented precedent for AWS surprising you on Cohere quotas. Ten minutes now or a wasted afternoon later.
3. **Measure actual `input_tokens`** from `query_logs.parquet`. Converts the net-cost table from estimate to fact and sets your pruning target from data instead of my arithmetic.
4. **Build Item A first and run arm A0 alone.** A baseline recall@k/MRR on 31 questions is a real, publishable result on its own, and — more usefully — it tells you whether retrieval is even your bottleneck. If baseline `recall@5` is already 0.9, a reranker has almost nothing to buy and Item B drops down the queue. Sequencing A before B is the highest-value ordering decision here.
5. Then Item B, and the A0/A1/A2 ablation.

**What I'm deliberately leaving to you, because these are judgement calls and not lookups:**

- **The pruning policy.** I've given you three mechanisms (`top_n` / `min_score` / a token budget) and a config surface for the first two. Which one is right depends on whether your binding constraint is cost, context-window pressure, or answer quality — and you know that better than I do. A token budget is the most principled and the most work; `top_n` is the crudest and ships today. My weak preference is to ship `top_n`, look at the score distribution A1 gives you, and only then decide whether a budget is worth building.
- **The acceptance bar.** I've given you the machinery (paired deltas, bootstrap CI, `n_better`/`n_worse`, the power calculation showing ±0.08 on a single arm) and the warning that `recall@30` is the control rather than the treatment metric. What counts as "the reranker earned its $0.002" is your call, and it should be written down *before* arm A2 runs. My only ask: write it down first. Post-hoc thresholds on n=31 are how projects convince themselves of noise.
- **Whether to add scalar summary columns to `query_logs.parquet` later.** Depends entirely on whether you want a dashboard. Separable, deferrable, and I'd defer it.
- **Whether the block-grouping merge rule should bridge small gaps** (e.g. treat `sentence_pos` 12 and 14 as one block, filling 13). Affects block count, cost, and passage coherence. I'd start strict-contiguous because it's simpler to reason about, but this is a corpus-specific question and you've read more 10-K prose than I have.
