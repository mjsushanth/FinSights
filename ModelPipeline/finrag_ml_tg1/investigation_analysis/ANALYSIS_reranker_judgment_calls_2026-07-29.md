> Collaborator artifact. Written by the research-collaborator agent. This is help offered,
> not instructions to follow and not a review. Weigh it and decide. Not part of the
> project's own documentation.
>
> Note: the agent's own sandbox blocked it from writing this file directly; the main
> session placed it here verbatim on the agent's explicit request, unedited.

# ANALYSIS - Three judgment calls for the reranker design (pruning policy, acceptance bar, block-merge rule)
**Date:** 2026-07-29 (UTC)
**Guidance level:** L3 WORKED — full reasoning, since the request was explicitly "I don't have the grounding to make these calls yet."

**Mode: ANALYSIS. Guidance level: L3 WORKED** — you asked for the mental models, so the reasoning is laid out rather than compressed. Arbitrary facts (library defaults, what Cohere's docs actually say, what the truncation literature found) are handed over at L4.

---

## The short version

The gold set has a structure the earlier design doc missed. **The 7 multi-evidence questions are exactly the 7 `cross_company`/`cross_year` questions, and the 24 single-evidence questions are exactly the 24 `local` ones — a perfect partition.** That collapses Q1 from "pick a pruning mechanism" into "N is a function of how many (company, year) pairs the query names," which `EntityAdapter` already computes and which needs no threshold calibration and no learned model. For Q2, the power arithmetic says n=31 detects roughly a +0.10 MRR move at 80% power and nothing smaller, so a significance-based ship gate is not conservative, it is broken — the right frame is non-inferiority on quality plus superiority on cost. For Q3, a ±3 window means "bridge a 1-sentence gap" is secretly "merge two blocks whose cores are 8 positions apart," and merging reduces pruning resolution, which is the only lever you have. Keep strict-contiguous; the question is probably closable with one histogram.

---

## §0 Names first, so you can go read for yourself

| your question | field's name | entry points |
| :-- | :-- | :-- |
| how many candidates go *into* the reranker | **Ranked List Truncation (RLT)** / cutoff prediction | Arampatzis/Kamps/Robertson SIGIR 2009; Bahri *Choppy* SIGIR 2020; Meng SIGIR 2024 |
| how many blocks come *out* | **context pruning / compression** | *Provence* ICLR 2025; RECOMP; LLMLingua |
| grouping sentences into units | **passage construction / retrieval granularity** | Callan SIGIR 1994; Kaszkiel & Zobel JASIST 2001; *Dense X Retrieval* EMNLP 2024 |
| how many questions to prove anything | **topic set size design / statistical power in IR** | Webber CIKM 2008; Sakai, Springer 2018 |
| which test on paired deltas | **significance testing in IR** | Smucker CIKM 2007; Urbano SIGIR 2019; Urbano SIGIR 2026 |
| "flat is fine, ship it" | **equivalence / non-inferiority (TOST)** | Lakens 2017 |

Two of these do real work below: RLT is *not* your problem, and "non-inferiority" is what makes Q2 tractable.

---

# Q1 - Pruning policy

## 1.1 Separate two truncations that look identical and are not

```
retrieve -> [TRUNCATION 1] -> rerank -> [TRUNCATION 2] -> generate
            "how many candidates       "how many survivors
             do I pay to score?"        does the LLM see?"
            objective: cost/latency    objective: answer quality
            literature: RLT            literature: context pruning
            YOURS: irrelevant.         YOURS: this is the whole feature.
              30 hits -> 10-25 blocks
              = 1 SearchUnit = $0.002
```

Sending 25 blocks instead of 8 costs the same $0.002. So: there is no reason to truncate before reranking and every reason to score all blocks and prune after — which is the principled justification for the design doc's `numberOfResults=len(texts)`.

## 1.2 What is actually established practice

**Every production framework ships fixed top-N at the rerank stage, and most ship only that.** Verified today:

- **LlamaIndex** — all reranker postprocessors (`CohereRerank`, `SentenceTransformerRerank`, `LLMRerank`, `JinaRerank`) expose `top_n` and nothing else. Score thresholding exists but at the *embedding* stage (`SimilarityPostprocessor`, default 0.7).
- **LangChain** — `CohereRerank.top_n: Optional[int] = 3` (read from source). No threshold parameter on the class at all.
- **Anthropic's Contextual Retrieval** — retrieve top 150, rerank, keep **top 20**, fixed. Reported top-20 retrieval failure rate 5.7% -> 1.9% (67% reduction).

**Cohere's own docs say the score is not comparable across queries.** Verbatim: scores are "normalized to be in the range `[0, 1]`", but "you can't assume that a document with a relevance score of `0.9109375` is *twice* as relevant as one with a relevance score of `0.04421997`," and "The score is query dependent." So a threshold needs per-corpus calibration, and the vendor says so explicitly. Their calibration protocol: 30-50 representative queries, borderline-relevant pairs, average the scores.

**The truncation literature's own verdict on fixed cutoffs: surprisingly hard to beat.** Meng et al. (SIGIR 2024) reproduced the supervised family (BiCut, Choppy, AttnCut, MtCut) and found: "supervised RLT methods do not demonstrate a clear advantage over their unsupervised counterparts; potential fixed re-ranking depths can closely approximate the effectiveness/efficiency trade-off achieved by supervised methods" and "a fixed re-ranking depth of 20 can already yield an excellent effectiveness/efficiency trade-off." But — honest other half — *oracle* per-query cutoffs beat every fixed cutoff with statistical significance. The headroom for adaptivity is real; what doesn't exist is a deployable learned method that captures it.

**Provence** (ICLR 2025) — sentence-level pruner, removes 50-80% of input with minimal quality drop, using a fixed threshold reported transferable across datasets — but that transferability was *trained into* the model. Cohere Rerank 3.5 was not trained for calibrated absolute scores.

**Counterweight:** *DPS* (arXiv 2508.09497) reports optimal fixed K is strongly dataset-dependent, with "a sharp drop beyond optimal values." Keep-everything is not safe.

## 1.3 The corpus fact that actually decides this

Cross-tabulated `retrieval_scope` against evidence count on all 31 gold questions — **perfect separation:**

| `retrieval_scope` | n_ev=1 | 2 | 3 | 4 | total |
| :-- | :-- | :-- | :-- | :-- | :-- |
| `local` | **24** | 0 | 0 | 0 | 24 |
| `cross_year` | 0 | 1 | 1 | 2 | 4 |
| `cross_company` | 0 | 1 | 1 | 1 | 3 |

A block never spans two `(cik, year, section)` groups by construction. So a question whose evidence spans *k* distinct groups requires at least *k* surviving blocks. Checked the distinct-group counts per cross-scope question: they range 2-4, with `P3V3-Q005` needing 4.

**A fixed N < 4 is guaranteed to fail at least one gold question no matter how good the reranker is** — a hard floor derived from labels, not a guess. `rerank_top_n_blocks: 8` was never really a guess: it's ~2x the hard floor, the right slack for an imperfect scorer.

## 1.4 Failure modes, grounded in this pipeline

**(a) Fixed top-N:** bites the 7 cross-scope questions (cliff at N=4) and is simultaneously too generous for the 24 local ones (7 distractor blocks admitted when 1 was needed).

**(b) Score threshold:** (1) calibration drift across answer types (26 span/3 list/2 boolean) — can't calibrate 3 thresholds on 31 questions; (2) empty-context catastrophe if all blocks fall below threshold — need a floor `k_min` regardless, at which point threshold-alone has quietly become top-N-with-a-threshold; (3) threshold couples to block size, since the cross-encoder scores the whole block — same evidence sentence scores differently depending purely on how the merge rule grouped it (a Q1<->Q3 coupling worth knowing about).

**(c) Token budget:** you asked specifically about the ±3-window interaction, and it's real — block sizes vary (window clamping + overlap merging), so a greedy "add by score until cap" has a systematic size bias either toward or against short blocks depending on the ordering rule, neither defensible on relevance grounds. And the deeper objection: a token budget solves a constraint that isn't binding — Haiku's window isn't binding at these context sizes, and cost isn't binding either (the whole feature moves ±$0.004/query). The binding constraint is answer quality via distractor suppression, which top-N already targets directly.

## 1.5 The reframe that dissolves the problem

`EntityExtractionResult` already carries `companies.ciks_int` and `years.years`, live in `run_supply_line_2_rag()`. So N can be conditioned on entity cardinality — a query-adaptive cutoff that costs nothing, needs no training data, and is grounded in a structural fact (blocks can't span companies/years), not a learned score distribution:

```python
# ILLUSTRATION only.
n_groups = max(1, len(entities.companies.ciks_int)) * max(1, len(entities.years.years))
top_n    = min(max_blocks, base_n + slack * n_groups)
```

Caveats: `n_groups` is an entity count, not a needed-evidence count (over-admits, which is the safe direction), and this is "validated" on 7 questions, which isn't real validation — check specifically whether the adapter's `n_groups` matches the label-derived distinct-key counts for those 7 (a 20-minute check).

## 1.6 Recommendation

**Ship `top_n` with a score floor, set both numbers from measurement, not guessing.**

1. Mechanism: `keep = [b for b in blocks if rank(b) <= N and b.score >= min_score]`, with a hard guarantee of at least `max(1, n_groups)` blocks. `min_score: 0.0` gives pure top-N on day one.
2. **Calibrate from gold-block rank, not Cohere's borderline-pair protocol** — you have labels, which is strictly more information. From arm A1 (score-only, membership unchanged), compute per-question rank/score of the block containing the gold sentence. N := ~90-95th percentile of gold-block rank, floored at 4. min_score := ~5th percentile of gold-block scores, then sanity check what fraction of non-gold blocks it also admits.
3. Make N a function of `n_groups` — but ship the constant first, add conditioning as a separately-measurable second change.
4. Drop the token budget for now; revisit only if `max_hits_before_expansion` grows past 30.

Genuinely unsure: whether `min_score` ever earns its keep — expect it to sit at 0.0 permanently, but build it anyway since it makes the distribution visible.

One structural note: because `_sort_sentences()` has no score term, the best block can never be placed first — the lost-in-the-middle position effect (Liu et al., TACL 2024) is uncontrolled here. That argues for fewer blocks with more force than in a score-ordered pipeline, since there's no way to protect the good one by position.

---

# Q2 - The acceptance bar

## 2.1 What is established about the test

- **Use the paired t-test on per-question deltas.** Urbano, Lima & Hanjalic (SIGIR 2019) found it well-behaved on both Type I rate and power, even for small samples.
- **Do not use the Wilcoxon signed-rank test.** Urbano SIGIR 2026, title: *Stop Using the Wilcoxon Test: Myth, Misconception and Misuse in IR Research*. Quoted: it "easily loses control of its Type I error rate in IR settings."
- **The sign test is valid but weak** (not what Urbano 2026 attacks) — report `n_better`/`n_worse`/`n_tied` as description, don't gate on a sign test.

## 2.2 The power arithmetic

For a paired design: `MDE = (z_(1-a/2) + z_(1-b)) . sd_d / sqrt(n)`. At alpha=0.05, power=0.80, n=31: `MDE = 0.503 . sd_d` (Cohen's d ~ 0.50 — a medium effect, and nothing smaller is detectable).

Modeling sd_d for MRR (fraction of questions whose first-gold-hit rank changes, times typical |delta RR|):

| p (fraction affected) | typical |delta RR| | sd_d | **MDE on MRR** |
| :-- | :-- | :-- | :-- |
| 0.2 | 0.3 | 0.134 | **0.068** |
| 0.3 | 0.4 | 0.219 | **0.110** |
| 0.4 | 0.4 | 0.253 | **0.127** |
| 0.5 | 0.5 | 0.354 | **0.178** |

**You need roughly +0.07 to +0.13 MRR to reach p<0.05 at 80% power.** A cross-encoder producing a genuine +0.04 will read "not significant" with high probability. **Do not make significance on MRR the ship gate** — it rejects real improvements most of the time.

Sign-test reference (exact binomial, one-sided p<=0.05): m=17 discordant pairs needs k>=14 wins ("14 better/3 worse/14 tied" is significant, p~0.006).

## 2.3 What n=31 cannot show about safety

If A2 gives zero regressions (31/31 gold sentences survive), the exact one-sided 95% upper bound on the true regression rate is `1 - 0.05^(1/31) = 9.2%`. **A perfect 31/31 is consistent with a true harm rate as high as 9.2%.** You cannot demonstrate safety at this n, only fail to detect harm roughly one query in eleven — write that next to any "0 regressions" result, and keep the reranking flag default-off with graceful degradation regardless of the result.

## 2.4 The frame that makes this tractable

This is a **non-inferiority** problem (clinical-trial framing, TOST/Lakens 2017), not a superiority problem: show the new arm isn't worse by more than a pre-specified margin delta, and win on a secondary dimension (tokens/cost). Critically: **"p > 0.05" is not evidence of equivalence** — only a CI that excludes the pre-specified delta licenses "close enough." The margin must be named *before* the run.

Also pre-specify which metric is primary. Because `assemble()` discards rank order, the delivered quantity isn't a ranking, it's a (set, size) pair — "was the gold sentence in the context, and how big was the context." MRR at the reranked stage is a legitimate mechanism check but not what the user receives; make gold-evidence-survival and token reduction the primary endpoints instead.

## 2.5 The n=3 and n=4 subgroups

**Cannot support any inferential claim** — one question flipping moves an n=3 "mean" by 0.33. What they *can* do: a qualitative, per-question walkthrough (7 rows: question_id, n_groups_required, n_blocks_kept, gold_survived, delta_RR), explicitly labelled "descriptive, n=7, not evidence." Worth more than any statistic on them, because it's about mechanism, not sample size.

## 2.6 A concrete bar to write down (starting point — move the numbers, keep the structure)

> **Gate 0 (kills the feature cheaply, ~$0.07):** on arm A1 only, the block containing gold evidence must rank top-3 by relevanceScore for >=24/31 questions.
>
> **Primary — safety, non-inferiority:** gold-evidence survival >=30/31 overall, 0 regressions among the 24 `local` questions. Pre-specified margin delta=0.05 on paired-mean-delta of `recall@5` at the reranked stage; ship requires bootstrap 95% CI lower bound above -0.05.
>
> **Secondary — benefit:** median per-question context token reduction >=30%, measured from the real `input_tokens` column.
>
> **Reported, NOT gated:** paired delta-MRR with bootstrap CI and n_better/n_worse/n_tied; recall@1/3/5/10/20/30 at all 3 stages; the 7-question cross-scope table; blocks_in distribution; rerank latency p50/p95.
>
> **Acknowledged limitation recorded with the result:** 0/31 regressions bounds the true rate only at ~9.2% (95%, one-sided).

## 2.7 "No significant difference" — which of three cases applies depends on the cost result

| cost result | quality CI | decision |
| :-- | :-- | :-- |
| cost-negative | tight, excludes delta | **ship**, recorded as "shipped on cost grounds, quality non-inferior, no quality improvement demonstrated" |
| cost-negative | wide, cannot exclude delta | **don't ship the aggressive prune** — ship score-only (A1) telemetry, or shelve |
| cost-neutral/positive | flat | **don't ship** |

## 2.8 The highest-leverage move isn't a statistical choice — it's more labels

MDE scales as 1/sqrt(n): 31->100 questions cuts MRR MDE from ~0.11 to ~0.06 (close to what a decent reranker actually produces). No test choice gets you that, only labels do. A hybrid approach (keep the 31 hand-curated as held-out "hard," add ~70 semi-automatically generated as the powered set) is more defensible than replacing one with the other — known bias: LLM-generated questions skew toward what an LLM finds answerable.

---

# Q3 - The block-merge rule

## 3.1 What the passage-construction literature says

- **Kaszkiel & Zobel (JASIST 2001):** "arbitrary passages" (overlapping fixed-length fragments ignoring document structure) work well and robustly. Passage boundaries don't need to respect discourse structure — robustness comes from overlap, not coherence. Your ±3 overlapping window already fits this tradition.
- **Dense X Retrieval (EMNLP 2024):** finer units (propositions/sentences) outperform passage-level units at a fixed compute budget — directionally *against* enlarging units with filler.
- **Provence (ICLR 2025):** sentence-level pruning, 50-80% removal with minimal quality loss — evidence generators cope fine with non-contiguous sentence sets.
- **Cuconasu et al. (SIGIR 2024):** near-miss non-relevant passages hurt LLM effectiveness — directly relevant to bridged filler, which is exactly "high-scoring but not answer-bearing" text. Caveat: a 2026 reproduction study found the *complementary* "noise helps" claim from the same paper is fragile/setting-dependent; I could not confirm whether it also overturns the "near-miss hurts" finding specifically. Treat as suggestive, not settled.
- **LlamaIndex's `AutoMergingRetriever`** (the closest deployed precedent) merges on a **density** criterion (>50% of a parent's children already retrieved), not a gap-size rule. No principled small gap-size default exists in the literature — any specific number (bridge 1 but not 2+) is intuition, mine included.

## 3.2 The derivation that reframes the question

A hit at position p covers `[p-3, p+3]`; the next hit at q merges under strict contiguity iff `q - p <= 7`. **Gap-of-1 only occurs at exactly `q - p = 8`.** So "bridge a 1-sentence gap" is precisely "merge two blocks whose *core hits* are 8 sentences apart" — a much less appealing proposition than "fill a one-sentence hole." Converting a window-plus-gap rule into explicit position arithmetic is what flipped this from "sounds harmless" to "actually a specific, checkable claim."

## 3.3 The architectural argument (decisive, and specific to this pipeline)

Because `_sort_sentences()` has no score term, the reranker's only lever is pruning, and pruning is all-or-nothing per block. **Merging trades pruning resolution for passage coherence — and pruning resolution is the entire value proposition here.** In a pipeline where reranked order actually reached the LLM, coherent larger passages would be more attractive (better score -> better position). Here the score only buys keep/drop, so granularity dominates.

Also: the bigger real threat to pruning resolution isn't gaps, it's **over-long blocks from window overlap** (three hits 4 apart merge into one 15-sentence, one-decision block) — that happens with zero gap-bridging. A **max-block-size split** targets this actual failure mode; a gap rule doesn't.

## 3.4 What the generator actually sees

Verified in `_format_with_headers()`: every sentence becomes its own paragraph, blank-line separated — no contiguity signal at all. So bridging gaps doesn't make the LLM's context more coherent; the only consumer that could benefit is the cross-encoder's single combined score, and per §3.3, finer blocks are probably worth more at prune time than a marginally better score. (Side note: `_build_header()`'s "Sentences: X - Y" range header would become literally accurate under bridging — the only genuinely appealing argument for it, and cheaper to fix in the header than the merge rule.)

## 3.5 Recommendation

**Keep strict-contiguous. Add a max-block-size split instead of a gap bridge. Check empirically before treating this as a live judgment call at all:** histogram within-`(cik, year, section)` position gaps between consecutive hits across the 31 gold questions' telemetry (available from arm A0). Expectation (not measurement): gap-of-1 (`Δpos=8` exactly) will be rare, since it needs two of <=30 hits landing in the same group at precisely 8 apart. If it's zero or near-zero across 31 questions, the question closes empirically rather than by judgment.

Instrument for this going forward: `blocks_in` distribution per query, sentences/tokens per block (max especially — Cohere Rerank 3.5 reportedly splits documents into ~4093-token chunks internally, worth knowing about), the within-group gap histogram, and count of any pure-neighbor-fill blocks with zero core hits (would indicate a bug).

---

## Sources

**Pruning / truncation:** Meng et al., *Ranked List Truncation for LLM-based Re-Ranking*, SIGIR 2024 (arXiv:2404.18185); Arampatzis/Kamps/Robertson, SIGIR 2009; Bahri et al. *Choppy*, SIGIR 2020 (arXiv:2004.13012); Chirkova et al. *Provence*, ICLR 2025 (arXiv:2501.16214); *Dynamic Passage Selector*, arXiv:2508.09497; Cohere *Best Practices for Using Rerank* (docs.cohere.com/docs/reranking-best-practices); Anthropic *Introducing Contextual Retrieval* (anthropic.com/news/contextual-retrieval); LangChain Cohere `rerank.py` source; LlamaIndex node postprocessor docs.

**Statistics / evaluation:** Urbano/Lima/Hanjalic, SIGIR 2019 (arXiv:1905.11096); Urbano, *Stop Using the Wilcoxon Test*, SIGIR 2026 (arXiv:2604.25349); Smucker/Allan/Carterette, CIKM 2007; Carterette, ACM TOIS 2012; Sakai, *Laboratory Experiments in IR*, Springer 2018; Sakai, SIGIR 2016 tutorial; Webber/Moffat/Zobel, CIKM 2008; Lakens, SPPS 2017.

**Passage construction / granularity / noise:** Callan, SIGIR 1994; Kaszkiel & Zobel, JASIST 2001; Chen et al. *Dense X Retrieval*, EMNLP 2024 (arXiv:2312.06648); Cuconasu et al. *The Power of Noise*, SIGIR 2024 (arXiv:2401.14887); *The Powerless Noise*, SIGIR 2026 (arXiv:2607.03615); LlamaIndex `AutoMergingRetriever` source.

**In-repo:** `retrieval_telemetry_and_reranking_design.md`; `ModelPipeline/finrag_ml_tg1/rag_modules_src/rag_pipeline/sentence_expander.py`; `.../rag_pipeline/context_assembler.py`; `.../entity_adapter/entity_adapter.py`; `.../data_cache/qa_manual_exports/goldp3_analysis/p3_gold_test_suite_31q.json`.

## What I would do next

1. Check `EntityAdapter`'s `n_groups` against the label-derived distinct-key counts for the 7 cross-scope questions (~20 min, no AWS calls) — §1.5's recommendation stands or falls on this.
2. Write the acceptance bar down (edit §2.6 to numbers you believe) before running A2.
3. Run Gate 0 (mechanism check on A1) before writing any pruning logic (~$0.07).
4. Histogram within-group position gaps from A0 telemetry — probably closes Q3 empirically.
5. Log `blocks_in`/tokens-per-block on the first real run.
6. Set N and `min_score` from gold-block rank/score percentiles, not from 8 and 0.0.

Left deliberately to you: the exact numbers in §2.6 (encode a risk appetite only you can set); whether to invest in more gold questions (§2.8); whether entity-conditioned N is worth the extra complexity over a shipped constant; whether the `_build_header()` range-over-gappy-group display issue is worth touching.
