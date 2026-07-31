# Reranking Answer-Quality Test: Does Reranking Change the Final Answer?

**Status:** run once, real end-to-end synthesis, 30 calls, $0.492 actual spend. Answers the
gap `RERANKING_IMPACT_ANALYSIS.md` explicitly left open: everything measured there was a
retrieval-stage proxy metric (recall@k, MRR on sentence-ID lists). This document measures
the thing a user actually sees -- the generated answer -- for the first time.

Notebook: `validation_notebooks/15_Reranking_AnswerQuality_E2E.ipynb` (executed in place;
raw results in `15_reranking_answer_quality_results_30q.json`, scored results in
`15_reranking_answer_quality_scored_30q.json`, both in the same directory).

## 1. Method

Real `answer_query()`-equivalent synthesis (real AWS Bedrock Claude Haiku 4.5 calls, no
mocking) on the 10 `gold_version == "P3.v3"` questions from
`MLFlow_POC/data/p3_gold_test_suite_31q.json`, at three configs:

| Config | `enable_reranking` | `rerank_top_n_blocks` | What it is |
| :-- | :-- | :-- | :-- |
| **A** | `false` | n/a | current shipped default (reranking off) |
| **B** | `true` | `16` | reranking on, looser prune |
| **C** | `true` | `8` | reranking on, shipped default prune when the flag is on |

30 calls total (10 questions x 3 configs), all succeeded (0 errors, all `stop_reason ==
"end_turn"`, no truncated responses). Actual total cost: **$0.492**.

`answer_query()` itself has no parameter to swap retrieval config, and editing
`ml_config.yaml` on disk was unsafe (another process was concurrently reading `MLConfig()`
for unrelated work). Verified empirically first (see notebook Step 1) that `MLConfig()` is
**not** a singleton -- every call re-reads the YAML fresh -- so the safe path was a
hand-built mirror of `init_rag_components()`/`answer_query()` that takes a config object
with an in-memory-only override applied to its own `.cfg['retrieval']` dict, never written
to disk, never shared with any other process. Everything downstream of config construction
(`build_combined_context()`, `PromptLoader`, `BedrockClient.invoke()`,
`create_success_response()`) is the unmodified production code path. `QueryLogger`
persistence was deliberately skipped to avoid writing into the shared query-log store while
other work was running concurrently in this repo -- this has no effect on any metric
reported here.

## 2. Metrics used, and an honest gap

`rag_modules_src/utilities/evaluation_metrics.py` defines `evaluate_answer()` with ROUGE-L,
BERTScore, cosine similarity, and BLEURT. Its actual signature was read from source, not
guessed. It requires `bert_score`, `rouge_score`, `sentence_transformers`, and (optionally)
`bleurt`.

**Checked empirically across every environment on this machine** (`finsights_revival`,
`mjs_mlcvdl_unified_m5`, `finsight-venv`, `base`): `bert_score`, `rouge_score`, and `bleurt`
are installed in **none** of them, and no `BLEURT-20` checkpoint exists anywhere on disk
(first use would need a ~2GB download on top of the missing package). All three are listed
in `environments/requirements.txt` as intended dev-only dependencies, so this is a genuine
environment gap, not an invented requirement -- but installing new packages is outside this
session's authority (hard guardrail: no new software installs without explicit sign-off),
so `evaluate_answer()` could not actually be called.

What this analysis computes instead, **with zero new installs**:

- **Cosine similarity** -- via `sentence_transformers` (already installed), using the same
  model constant `evaluation_metrics.py` uses (`all-MiniLM-L6-v2`) and the same
  `util.cos_sim` call. Not an approximation -- the identical computation for this one metric.
- **ROUGE-L** -- reimplemented via the standard LCS-based F-measure (same algorithm
  `rouge_score.rouge_scorer` uses for `'rougeL'`), word-tokenized, lowercased, **without**
  Porter stemming (the packaged scorer runs `use_stemmer=True`). Scores here will read
  slightly lower than the packaged metric would report for that reason.
- **BERTScore F1**: not computed (package not installed).
- **BLEURT**: not computed (package not installed, no checkpoint present, and independently
  the slowest of the four per `RETRIEVAL_IMPROVEMENT_STUDY.md`, ~7.2s/pair -- two independent
  reasons to skip it here, not one).

This gap is reported plainly rather than papered over. Everything below should be read as
"cosine similarity + a ROUGE-L approximation," not the full 4-metric stack.

**Sample-size caveat, stated up front:** n=10 per config (30 total) is smaller than the
n=31 retrieval-stage ablation that `ANALYSIS_reranker_judgment_calls_2026-07-29.md`
Sec 2.2 already flagged as underpowered for anything but a large effect. Nothing below is a
statistically defensible claim -- it is a description of what happened on these 10
questions, plus one mechanism that is directly traceable to specific retrieval counts, not
inferred from an average.

## 3. Aggregate comparison

| Config | n | avg ROUGE-L | avg cosine sim | avg context length (chars) | avg input tokens | avg output tokens | total cost |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| A (no rerank) | 10 | 0.101 | 0.762 | 35,905 | 13,108 | 1,318 | $0.1970 |
| B (rerank, top-16) | 10 | 0.105 | 0.732 | 25,015 | 10,689 | 1,124 | $0.1631 |
| C (rerank, top-8) | 10 | 0.112 | 0.771 | 14,314 | 8,140 | 1,010 | $0.1319 |

Context-length reduction vs. A (per-question, not just the aggregate mean):

| | median reduction | mean reduction |
| :-- | --: | --: |
| B (top-16) vs A | 33.0% | 30.7% |
| C (top-8) vs A | 61.0% | 61.2% |

Cost reduction vs. A:

| | median reduction | mean reduction |
| :-- | --: | --: |
| B (top-16) vs A | 16.9% | 16.2% |
| C (top-8) vs A | 31.6% | 32.5% |

This is the token-savings number `RERANKING_IMPACT_ANALYSIS.md` Sec 5 explicitly left as
"not yet measured." Now measured: **reranking cuts context substantially (30-60%+ depending
on top_n) and cost meaningfully (16-33%)**, comfortably clearing the guidance doc's own
secondary-benefit bar (Sec 2.6: "median per-question context token reduction >=30%") for
both B and C.

## 4. Did reranking change answer quality?

**At the aggregate level: no clear, consistent direction, in either config.** Average
cosine similarity moves from 0.762 (A) to 0.732 (B) to 0.771 (C) -- a dip-then-recover
pattern with no monotonic story, and a spread (0.039) that is well within what 10 noisy
per-question scores would produce by chance. Average ROUGE-L nudges up slightly and
monotonically (0.101 -> 0.105 -> 0.112) with more aggressive pruning, but the absolute
differences (0.011 total) are small relative to per-question variance (individual
ROUGE-L values range 0.049 to 0.220 across the whole run). Reading this next to the
already-published retrieval-stage result -- "flat" recall/MRR between A1 and A2 in
`RERANKING_IMPACT_ANALYSIS.md` -- the answer-level result is consistent with it: **no
meaningful uniform quality change detected.** That is a legitimate, useful finding, not a
failure to find something.

**Top-16 vs top-8: no consistent winner either.** C (top-8) actually scores fractionally
*higher* than B (top-16) on both metrics in this run's aggregate -- but see Sec 5 below for
why that average is misleading for a specific, important subset of questions.

## 5. Where it did matter: multi-entity cross-company questions at top-8

Breaking the aggregate down by `retrieval_scope`, the flat aggregate story hides one real,
mechanistically-explained divergence. The three largest per-question cosine-similarity
spreads across configs were:

| question_id | scope | # named entities | cos(A) | cos(B) | cos(C) | spread |
| :-- | :-- | --: | --: | --: | --: | --: |
| P3V3-Q004 | cross_company | 3 companies | 0.788 | 0.637 | 0.727 | 0.151 |
| P3V3-Q002 | cross_year | (1 company, 4 years) | 0.732 | 0.639 | 0.763 | 0.124 |
| P3V3-Q005 | cross_company | 4 companies | 0.639 | 0.636 | 0.736 | 0.100 |

Pulling the actual retrieval counts for Q004 and Q005 (from `retrieval_stats.counts` in the
scored JSON) explains what happened, and it lines up exactly with the theoretical floor
already derived in `ANALYSIS_reranker_judgment_calls_2026-07-29.md` Sec 1.3: *"A
fixed N < 4 is guaranteed to fail at least one gold question no matter how good the
reranker is"* for cross-scope questions needing that many distinct (company, year, section)
groups.

**P3V3-Q005** (4 named companies: Walmart, Apple, Microsoft, Icahn Enterprises) --
`expanded_sents` available after retrieval: 112. Reranked survivors: **29** at top-16, just
**10** at top-8. At top-8, the surviving evidence covered only 2 of the 4 companies asked
about, and the model said so explicitly:

> **Config C (top-8), P3V3-Q005:** "I appreciate your question, but I must note a
> significant data limitation that prevents a complete response. The provided dataset
> contains Item 1A Risk Factors sections only for Apple Inc. and Icahn Enterprises L.P. for
> fiscal 2010. Risk factor discussions for Walmart and Microsoft during this period are not
> included in the available data, making a comprehensive four-company comparison
> impossible."

Compare to the same question at no reranking:

> **Config A (no rerank), P3V3-Q005:** "The four companies disclosed materially different
> liquidity and credit risk exposures in their 2010 Item 1A risk factor discussions,
> reflecting their distinct business models and financial structures. Apple's liquidity and
> credit risk discussion centered on operational disruption and counterparty exposure rather
> than direct solvency concerns..." *(continues addressing all four companies)*

**P3V3-Q004** (3 named companies: Radian Group, Netflix, Mastercard) --
`expanded_sents` available: 115. Reranked survivors: 69 at top-16, **35** at top-8. Again,
top-8 dropped evidence for two of the three companies:

> **Config C (top-8), P3V3-Q004:** "I appreciate your question, but I need to clarify a
> significant scope limitation with the data provided to me. The dataset I have access to
> contains only Mastercard's risk factor disclosures from their 2009 Form 10-K filing. I do
> not have any SEC 10-K filing data for Radian Group or Netflix from 2009 or any other
> period."

> **Config A (no rerank), P3V3-Q004:** "The three companies disclosed materially different
> approaches to data protection and privacy risks in their 2009 Form 10-K filings...
> Mastercard emphasized regulatory compliance and third-party dependencies, Netflix focused
> on subscriber data leverage and reputational concerns, while Radian Group addressed
> information security more narrowly within a broader litigation context." *(continues
> addressing all three)*

By contrast, **P3V3-Q006** (also `cross_company`, but only 2 named entities: Exxon Mobil and
Eli Lilly) shows the pattern *not* triggering: at top-8, 59 of 179 expanded sentences
survived pruning -- enough to keep both companies' evidence -- and the answer addresses both
companies with no hedging (cosine spread across configs for Q006 was only 0.018, the
smallest of any cross-scope question in the set).

**The mechanism, stated plainly:** `rerank_top_n_blocks=8` is a fixed cutoff applied
regardless of how many distinct companies/years a question names. For a question naming 3-4
entities, 8 surviving blocks is not enough headroom for the cross-encoder's imperfect
scoring to guarantee at least one surviving block per entity -- so entities silently drop
out of the context, and the model (correctly, and to its credit) says it cannot answer for
the missing ones rather than fabricating. This is exactly the failure mode
`ANALYSIS_reranker_judgment_calls_2026-07-29.md` Sec 1.3 predicted from evidence
labels alone, now confirmed at the answer level in production. Top-16 gave enough headroom
for Q006 (2 entities) but was still tight for Q004/Q005 (3-4 entities) -- consistent with the
guidance doc's argument that a *fixed* N is the wrong shape for this problem, and that N
should scale with the number of named entities (Sec 1.5's `n_groups`-conditioned proposal),
not stay flat at 8 or even 16.

**A blind spot in the automated metrics themselves is also worth flagging.** The
`cross_company` aggregate cosine average at C (0.744) was actually the *highest* of the
three configs (Sec 3's by-scope breakdown), because "correctly declines to answer for 2 of 4
companies, but answers well for the other 2" still overlaps substantially with a gold answer
that covers all 4. Cosine similarity (and ROUGE-L) do not clearly penalize incompleteness the
way a human grader checking "did it address all 4 companies asked about" would. The aggregate
numbers in Sec 3-4 should not be read as clearing this failure mode -- they simply cannot see
it. The concrete examples in this section are the actual evidence for the entity-starvation
problem, not the aggregate score.

## 6. Bottom line

- **No meaningful, consistent answer-quality difference detected between reranking on/off at
  the aggregate level**, on this 10-question sample. Consistent with the "flat" result
  already reported at the retrieval-proxy-metric level in `RERANKING_IMPACT_ANALYSIS.md`.
- **Token/cost savings are real and substantial**: median context reduction 33% (top-16) to
  61% (top-8); median cost reduction 17% (top-16) to 32% (top-8). This closes the "not yet
  measured" item from `RERANKING_IMPACT_ANALYSIS.md` Sec 5.
- **Top-16 vs top-8 shows no consistent aggregate winner**, but this masks a real, specific
  failure mode: **`rerank_top_n_blocks=8` can silently starve cross-company questions naming
  3+ entities of evidence for some of those entities**, causing explicit (honest, non-
  hallucinated) refusal for the missing ones rather than a uniformly worse-scored answer.
  This is not visible in the aggregate cosine/ROUGE-L numbers and would not have been caught
  without reading actual answer text. It directly corroborates, at the answer level, the
  entity-cardinality argument already made on structural/label grounds in
  `ANALYSIS_reranker_judgment_calls_2026-07-29.md` Sec 1.3 and 1.5.
- **Recommendation implied by this evidence** (not a decision made here): if
  `rerank_top_n_blocks` is shipped as a fixed constant, 8 is too tight for the
  3-4-named-entity tail of `cross_company` questions specifically; either raise the floor for
  multi-entity queries or implement the entity-cardinality-conditioned `top_n` already
  proposed in the guidance doc, before shipping reranking with a flat top-8 default.
- n=10 means none of this should be treated as more than a strong, well-explained anecdote at
  the individual-question level (Sec 5) plus a directionally-flat aggregate (Sec 3-4) -- both
  are worth recording, neither is a proof.
