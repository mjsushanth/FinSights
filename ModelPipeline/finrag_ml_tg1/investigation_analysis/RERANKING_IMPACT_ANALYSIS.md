# Reranking Impact Analysis

**Status:** built, wired, smoke-tested, and measured across a 3-arm ablation plus a top-N
sweep and score-calibration check (Sec 7). Not yet shipped (`enable_reranking: false` by
default). Token savings: **not yet measured** -- see the open item at the end.

**Correction (2026-07-30):** Sec 3 originally claimed "gold-evidence survival under A2
pruning: 31/31 (100%)". That was wrong -- it compared `recall@30`, which silently truncates
to the first 30 sentences of whatever list it's given, against a pruned set that actually
contained ~51 sentences at `top_n=8`. Anything surviving pruning past position 30 was
invisible to that check. The correct, full-membership survival rate (Sec 7) is **54.8%** at
`top_n=8`, not 100%. Left the original wrong text below struck through rather than deleted,
so the mistake and its correction are both part of the record.

## 1. Philosophy: why a reranker, and why *pruner* not *reorderer*

Retrieval today produces a broad candidate pool on purpose: ~30 ANN hits, expanded by a
+/-3 sentence window into 150-200+ raw sentence records, deduplicated down to a smaller
unique set (observed 160-190 sentences per query). A cross-encoder (Cohere Rerank 3.5,
via Bedrock) scores each candidate *jointly* with the query -- richer than the bi-encoder
similarity that produced the candidate pool in the first place, but too expensive to run
over the whole corpus, which is why it only ever sees the already-retrieved pool.

**Critical architecture fact, verified in code, not assumed:** `ContextAssembler._sort_sentences()`
always re-sorts the surviving sentences into document order (company, year, section, position)
before they reach the LLM -- regardless of any relevance ranking a reranker computes. So a
reranker that only *reorders* changes nothing about the final context string; the only lever
that has any effect here is **pruning** -- deciding which sentences survive at all. This is
why `reranker.py` groups sentences into contiguous blocks and prunes blocks, and never
attempts to hand back a relevance-ordered list for delivery.

Grouping is **strict-contiguous** (a block never bridges a gap in `sentence_pos`) rather than
bridging small gaps, on the argument that bridging trades away pruning resolution -- the one
thing this feature can actually affect -- for passage coherence the generator can't perceive
anyway (each sentence is already rendered as its own paragraph downstream). See
`ANALYSIS_reranker_judgment_calls_2026-07-29.md` Sec 3 for the full derivation.

Default config shipped: `rerank_top_n_blocks: 8`, `rerank_min_score: 0.0`, out of a typical
10-25 blocks formed from ~30 hits.

## 2. Actions taken

- `rag_pipeline/reranker.py` -- `CohereReranker`: groups `SentenceRecord`s into contiguous
  blocks, scores all of them in one `bedrock-agent-runtime` call (`cohere.rerank-v3-5:0`),
  prunes by top-N + score floor, flattens back to `SentenceRecord`s. Graceful degradation:
  any failure returns the unpruned input rather than breaking the query.
- Config added under the existing `retrieval:` block in `ml_config.yaml` --
  `enable_reranking` (default `false`), `rerank_top_n_blocks`, `rerank_min_score`,
  `rerank_max_sources`, `rerank_cost_per_1k_queries`.
- Wired into `synthesis_pipeline/supply_lines.py`: `RAGComponents.reranker` (`Optional`,
  `None` unless the flag is on -- no client constructed, no AWS credential path exercised
  when off), called between `expand_and_deduplicate()` and `assemble()`.
- Retrieval telemetry (`utilities/retrieval_telemetry.py`, `utilities/retrieval_metrics.py`)
  built first, specifically so this analysis could be measured rather than guessed at --
  before this work, no retrieval-quality metric existed anywhere in the codebase.
- Two pre-existing bugs in `SentenceExpander` were found and fixed along the way (surfaced
  by building the telemetry harness, unrelated to reranking itself): a window-bound clamp
  against the wrong field silently dropped hits during expansion, and a lower-bound
  off-by-one excluded hits whose `sentence_pos == 0`. Both fixed; see the code comments in
  `sentence_expander.py` for the exact mechanism.

## 3. What was measured: 3-arm ablation, 31 gold questions

| Arm | Config | What it isolates |
| :-- | :-- | :-- |
| A0 | no reranker | current shipped system |
| A1 | `top_n=None, min_score=0.0` | cross-encoder scoring quality, membership *unchanged* |
| A2 | `top_n=8, min_score=0.0` | the real, shipped pruning config |

**Confirmed by direct inspection, not assumed:** A0 and A1 have identical membership (166
sentences, same set, for a sample query) -- A1 only reorders. This makes A1 vs A2 the clean,
production-relevant comparison, since A0 vs A1's apparent difference is a reordering effect
that (per Sec 1) never reaches the LLM anyway.

**Results:**

| Metric | A0 (no rerank) | A1 (score-only) | A2 (pruned top-8) |
| :-- | :-- | :-- | :-- |
| `recall@5` | 0.043 | 0.137 | 0.137 |
| `recall@30` | 0.059 | 0.470 | 0.470 |
| `MRR` | 0.029 | 0.076 | 0.074 |

(A0's low `recall@30` relative to A1/A2 is the reordering artifact above -- A0's list isn't
score-sorted, so its first-30 slice is close to arbitrary. A1 vs A2, side by side, is the
number that matters: **essentially flat**.)

- ~~**Gold-evidence survival under A2 pruning: 31/31 (100%).** No gold sentence that the system
  found at all was lost to pruning, across the whole gold set. This is the primary
  safety/non-inferiority endpoint from `ANALYSIS_reranker_judgment_calls_2026-07-29.md` Sec 2.6
  (bar was >=30/31), and it passes cleanly.~~ **WRONG, see the correction notice at the top and
  Sec 7 -- this compared `recall@30`, an implicit-truncation-to-30 metric, against a pruned set
  that actually held ~51 sentences. Real survival at `top_n=8` is 54.8%, not 100%.**
- **Gate 0 (does the gold-containing block rank near the top of A1's score-sorted list):
  15/31 (48%),** via a crude proxy (first gold hit within the top ~24 of ~160+ scored
  sentences). The doc's bar was >=24/31 (77%). This is below bar -- moderate signal, not strong.

## 4. Why it likely didn't move the needle much here -- candidate explanations, not a single verdict

None of these are proven individually; they're the working hypotheses, roughly in order of
how much I'd weight them:

1. **Underpowered sample.** `ANALYSIS_reranker_judgment_calls_2026-07-29.md` Sec 2.2 computed
   the minimum MRR effect detectable at n=31 (80% power) as roughly +0.07 to +0.13. The
   observed A1-vs-A2 MRR change (-0.002, and even the A0-vs-A2 combined change of +0.045) sits
   at or below that floor. "Flat" here is consistent with "too small a sample to see a real but
   modest effect," not proof of zero effect.
2. **Financial 10-K prose may genuinely have weak lexical separability at the sentence level** --
   the corpus's own documented failure mode (`RETRIEVAL_IMPROVEMENT_STUDY.md` Sec 2.1, "boilerplate
   crowding") is that definitions, cross-references, and forward-looking-statement boilerplate are
   *textually* similar to genuine answers. A general-purpose cross-encoder (not finance-tuned) may
   not sharply separate these either, which is one plausible reading of the 48% Gate 0 rate.
3. **Block granularity may dilute the signal.** A relevant single sentence merged into a
   multi-sentence block gets one averaged-ish score for the whole block; if the block also
   contains lower-relevance neighbor sentences, the score may not cleanly reflect the one good
   sentence buried inside it. Not measured directly yet -- see investigation plan, item 6.
4. **Published results elsewhere are much more positive, worth noting as a contrast rather than a
   contradiction.** A financial-RAG-specific study (Enhancing Financial Report Question-Answering:
   A RAG System with Reranking Analysis, arXiv 2603.16877, FinDER benchmark, 1,500 queries) reports
   reranking raising "correctness >=8/10" scores from 33.5% to 49.0%. That's a much larger, properly-
   powered study on a similar domain, and it measured *answer quality*, not retrieval-stage recall/MRR
   proxies. The gap between that result and this one is exactly why the investigation plan below
   proposes a real answer-quality comparison, not just more retrieval-metric measurement.
5. **The reordering benefit that *did* show up (A0->A1) is architecturally inert here.** Whether
   or not the cross-encoder is "good," this pipeline can currently only benefit from *pruning*, not
   ranking. If a future change let `ContextAssembler` respect relevance order (e.g., primacy/recency-
   aware placement, motivated by the "Lost in the Middle" position-sensitivity literature already
   cited in the design docs), the same cross-encoder scores might have a real, currently-invisible
   payoff. Out of scope for this analysis, flagged for later.

## 5. Token savings

**Not yet measured.** This requires comparing real `input_tokens` from `answer_query()` with
reranking on (top-8) vs off, on the same queries -- the same methodology already used once this
session to get the ~17,000 tokens/query baseline (see `EMBEDDING_INPUT_TYPE_ASYMMETRY.md`-adjacent
pre-flight work). Deliberately deferred pending the deeper investigation plan below, since the
project owner flagged the pruning aggressiveness (top-8) itself as an open question worth
investigating before spending more on this specific number.

## 6. Open question flagged by the project owner, not yet resolved

Is `top_n=8` too aggressive for a boilerplate-heavy financial corpus, where giving the LLM more
context might be safe or even beneficial rather than harmful? The literature is genuinely mixed
here -- some published RAG ablations show accuracy peaking around keeping very few (k=2-4) documents
and degrading with more due to "increased distraction," while other work (the contested Cuconasu
"Power of Noise" result and its 2026 non-replication) suggests the effect is highly setup-dependent
and not a general law. This is exactly the kind of question that needs this corpus's own data, not
someone else's benchmark -- see the deep investigation plan for how to actually answer it before
changing the default.

## 7. Top-N sweep and score-calibration check (notebooks 13, 14)

Both reuse a single scored-blocks pass per question (`CohereReranker.score_blocks()` scores
every candidate block once, billing/latency independent of the eventual cutoff) -- no repeat
Bedrock Rerank calls across the whole sweep or the calibration analysis. Raw data cached at
`data_cache/rerank_scored_blocks_31q.json`.

### 7.1 Top-N sweep (notebook 13) -- corrected gold-survival numbers

| top_n (blocks) | avg sentences kept | gold survival (true, full-membership) | recall@5 | MRR |
| --: | --: | --: | --: | --: |
| 4 | 27.9 | 38.7% | 0.137 | 0.068 |
| **8 (shipped)** | **50.9** | **54.8%** | 0.137 | 0.074 |
| 12 | 72.4 | 58.1% | 0.137 | 0.074 |
| 16 | 93.0 | 58.1% | 0.137 | 0.074 |
| 20 | 108.4 | 61.3% | 0.137 | 0.075 |
| 24 | 118.7 | 61.3% | 0.137 | 0.075 |
| 30 | 125.8 | 64.5% | 0.137 | 0.076 |
| all (~29 blocks avg) | 132.1 | 64.5% | 0.137 | 0.076 |

Reading this straight: the project owner's concern that `top_n=8` is more aggressive than it
looked is **correct** -- real survival there is 54.8%, and 16 only buys +3.3 points for roughly
double the tokens. But the ceiling matters just as much: even **zero pruning** (all ~29 blocks
kept) only reaches 64.5% survival. That remaining ~35% gap is a retrieval-stage ceiling
(consistent with the ~54% core-stage `recall@30` from the original baseline, Sec 3) -- evidence
the retriever itself never surfaced for those questions, which no amount of generosity at the
reranker stage can recover. `recall@5`/MRR are flat across the entire sweep: the cross-encoder's
own ranking quality doesn't change with N, only how much of the same ranked list survives.

### 7.2 Score-distribution / calibration check (notebook 14)

Across 910 scored blocks (27 gold-containing, 883 not):

| | gold-containing blocks (n=27) | non-gold blocks (n=883) |
| :-- | --: | --: |
| mean score | 0.518 | 0.236 |
| median score | 0.518 | 0.158 |
| p10 / p90 | 0.091 / 0.874 | 0.029 / 0.551 |

Only **12.0%** of non-gold blocks score at or above the median gold-block score -- real,
meaningful separation, more optimistic than Gate 0's 48% pass rate suggested (Sec 3). Read
together: the cross-encoder's central tendency clearly favors gold blocks, but the tails
overlap enough (some gold blocks score as low as 0.09; some non-gold blocks score as high as
0.55) that any single query can still land on the wrong side of a fixed cutoff -- consistent
with both findings being true at once rather than contradictory.

**Correction to Sec 1's `min_score` assumption:** the threshold sweep shows a modest floor is
more useful than expected. At `min_score=0.05`: 92.6% gold-block recall for only 81.8% overall
block survival (cuts ~18% of clearly-weak blocks almost for free). At `min_score=0.1`: 88.9%
gold recall, 64.2% survival. `ANALYSIS_reranker_judgment_calls_2026-07-29.md` Sec 1.6
predicted `min_score` would "sit at 0.0 permanently" -- this corpus-specific data says a small
non-zero floor (0.05-0.1) is worth piloting alongside (not instead of) a top-N cutoff, since it
adapts to how many blocks are *actually* competitive per query rather than a fixed count.
