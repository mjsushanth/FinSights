# Reranking: Final Synthesis and Ship Decision

**Date:** 2026-07-30
**Scope:** the qualitative pass that the metric work left open — reading the actual retrieved
sentence text at different pruning levels, and personally judging the 30 generated answers from
the answer-quality run. No config or code was changed by this analysis.

**What this document adds that the others do not.** `RERANKING_IMPACT_ANALYSIS.md` and
`RERANKING_ANSWER_QUALITY_TEST.md` between them cover recall/MRR, the top-N sweep, score
calibration, token/cost savings, and one read-through of two failing answers. Everything there
is either a number or a spot check. This document reads the retrieved **text** — what is kept
and what is dropped at top-30 / 16 / 8 / 4 — and judges all ten answer triplets by hand. Two of
the conclusions below contradict prior documents; those are flagged explicitly in Sec 5.

---

## 1. Verdict

**`rerank_top_n_blocks = 8` is not fit to ship as-is.** Neither is a flat `16`, though 16 is
much closer to defensible. The flag should stay `enable_reranking: false` by default.

The reason is not the one the earlier documents converged on. The earlier framing was
"top-8 is too aggressive; it starves multi-entity questions; raise N or make N depend on entity
cardinality." My read says the pruning budget is a real but **secondary** problem, and the
entity-cardinality fix is **not sufficient and can make answers worse** (evidence in Sec 5.1).

What the text actually shows is that the binding defect sits upstream of `top_n`:

> **45.2% of the blocks surviving at top-8 come from a fiscal year the question did not ask
> about** — versus a 31.5% off-year rate in the unpruned candidate pool. For the 24 `local`
> questions (single company, single year) it is **47.4% at top-8 vs a 31.3% pool base rate**.
> Reranking does not merely fail to fix off-year contamination; it *concentrates* it, because
> off-year blocks are systematically longer (mean 5.49 vs 4.04 sentences) and score higher
> (mean 0.300 vs 0.219), and the cross-encoder never sees year metadata at all.

So roughly half of a top-8 context budget is spent on the right company discussing the right
topic in the wrong year. Tuning `N` cannot fix that: raising N admits more off-year text, and
lowering N makes the surviving set *more* off-year-concentrated, not less.

### The smallest fix, in order of increasing cost to build

1. **Do nothing to the code; leave the flag off.** This is the honest default today. The
   feature's measured benefit is a 32% cost reduction at top-8, and its measured cost is answer
   degradation on 5 of 10 gold questions (Sec 4). The project's own acceptance bar
   (`ANALYSIS_reranker_judgment_calls_2026-07-29.md` Sec 2.6) makes quality
   non-inferiority primary and cost secondary. Non-inferiority fails at top-8.

2. **If reranking must be switched on now: `rerank_top_n_blocks: 16`, `rerank_min_score: 0.05`
   — a config-only change, no code.** In my judge pass, top-16 is non-inferior to no-reranking
   on 6 of 10 questions, better on 1, worse on 3; top-8 is worse on 5. The `0.05` floor is
   supported by the existing calibration data (notebook 14: 92.6% gold-block recall at 81.8%
   block survival). This buys about half the cost saving with materially less damage. It does
   **not** fix the off-year problem and should not be described as a fix.

3. **The change I would actually argue for, which is a code change and therefore not the
   "smallest":** make the surviving set satisfy a **coverage floor keyed to the entities the
   query names**, rather than raising a global N. Concretely — keep the best-scoring block for
   each `(cik_int, report_year)` pair that `EntityAdapter` extracted, *then* fill the remaining
   budget by score. This is different from the entity-conditioned-N proposal in the guidance
   doc: that proposal enlarges N and lets score decide, which (Sec 5.1) admits wrong-year filler;
   this one spends the budget on the pairs the user asked for. `_select()` in `reranker.py` is
   the single place it goes, and `EntityExtractionResult` is already in scope at the call site
   in `run_supply_line_2_rag()`.

4. **Upstream, and the real fix:** the off-year blocks should not be in the candidate pool.
   31.5% of the pool is off-year before reranking touches anything. That is a
   `MetadataFilterBuilder` / retrieval-stage question, not a reranking question, and it would
   raise the ceiling for every arm simultaneously.

**One thing that should not be lost in the negatives:** the cross-encoder's *ranking* is good.
The gold-containing block sits at a **median normalized rank of 0.053** — top 5% of the scored
list — and is rank #1 outright for 10 of the 25 questions where gold is retrievable at all.
The reranker is not the weak component. The pruning policy and the retrieval filters are.

---

## 2. Method, and two caveats that matter for reading the rest

**Task A (text read-through).** For the gold questions I reused the cached scored-block data at
`data_cache/rerank_scored_blocks_31q.json` — the same single scored pass notebooks 13 and 14
report — and joined sentence text from `data_cache/stage1_facts/finrag_fact_sentences.parquet`.
That means zero new Bedrock spend and exact consistency with the published numbers (I
reproduced notebook 13's survival column to the digit: 38.7 / 54.8 / 58.1 / 58.1 / 61.3 / 61.3 /
64.5 / 64.5). Questions read in full: **P3V3-Q004, P3V3-Q005, P3V3-Q006, P3V2-Q007, P3V2-Q019,
P3V3-Q002**.

I then ran **two fresh custom questions about 2025 filings** (NVIDIA export controls; Eli Lilly
incretin manufacturing capacity) through live retrieval + `CohereReranker.score_blocks()` — one
Bedrock Rerank call each, no synthesis — to check that the patterns are not artifacts of the
cached gold-set draw. They are not. `report_year` does reach 2025 in Stage 1 (43,851 sentences;
range 2006-2025), verified before use.

**Caveat 1 — retrieval is not reproducible run to run, even with `enable_variants = False`.**
Comparing the notebook-13 cached pool against the notebook-15 answer-quality pool for the same
ten questions, pool membership differs: Q002 overlaps 192/206, Q005 98/111, Q003 170/187. More
consequentially, **gold coverage differs between the two draws** — Q004 has 2/3 gold IDs in the
notebook-15 pool but 1/3 in the notebook-13 pool; Q005 has 2/4 vs 1/4; Q002 has 1/4 vs 0/4.
Neither doc mentions this. It means (a) block-level analysis and answer-level analysis are not
strictly coupled, and (b) the "64.5% ceiling" in `RERANKING_IMPACT_ANALYSIS.md` Sec 7.1 is a
single-draw estimate and is probably an *under*estimate.

**Caveat 2 — the reported survival metric is a strict conjunction, which the prose does not
say.** Notebook 13 computes `gold_survived = (n_hits == len(gold_ids))`: *every* gold evidence
ID must survive. For the 7 multi-evidence questions this is a much harder test than "the gold
evidence survived," which is how the docs read. Both definitions, same data:

| top_n | strict (all gold IDs survive) | loose (≥1 gold ID survives) |
| --: | --: | --: |
| 4 | 38.7% (12/31) | 51.6% (16/31) |
| **8** | **54.8% (17/31)** | **64.5% (20/31)** |
| 16 | 58.1% (18/31) | 67.7% (21/31) |
| 30 | 64.5% (20/31) | 77.4% (24/31) |
| all | 64.5% (20/31) | **80.6% (25/31)** |

The strict metric is dominated by the retrieval ceiling, not by pruning: for 6 of the 7
multi-evidence questions the retriever surfaces only **1 or 2** of the 3-4 required gold
sentences, so those questions fail the strict test at *any* `top_n`, including no pruning at all.

| question | scope | gold IDs needed | in pool |
| :-- | :-- | --: | --: |
| P3V3-Q001 | cross_year | 4 | 2 |
| P3V3-Q002 | cross_year | 4 | 0 |
| P3V3-Q003 | cross_year | 3 | 1 |
| P3V3-Q004 | cross_company | 3 | 1 |
| P3V3-Q005 | cross_company | 4 | 1 |
| P3V3-Q006 | cross_company | 2 | 1 |
| P3V3-Q010 | cross_year | 2 | 2 |

The cleaner way to state the pruning cost, isolating it from the ceiling: of the **25** questions
where gold is reachable, pruning to top-8 loses **5** (P3V2-Q002, P3V2-Q019, P3V2-Q021,
P3V3-Q004, P3V3-Q005); top-16 loses 4; top-4 loses 9.

---

## 3. Task A — what the text actually looks like

### 3.1 The dominant pattern: year-over-year near-duplicate boilerplate eats the budget

SEC risk-factor and MD&A prose is substantially copy-pasted from one year's 10-K to the next.
The cross-encoder scores near-duplicates near-identically, so they cluster adjacently in the
ranking and consume many of the few slots a small `top_n` allows. **92.7% of blocks kept at
top-8 share a `(company, section)` with another kept block from a different year**; for `local`
questions specifically it is also 92.7%.

The cleanest example is from my fresh, non-gold-set query — *"What does Eli Lilly say in its
**2025** 10-K about manufacturing capacity expansion for its incretin products?"* Ranks 1 and 2,
both kept at top-4, verbatim:

> **[rank 1] score=0.7068 | ELI LILLY & Co | FY2022 | ITEM_7**
> "As we expand our manufacturing capacity in order to meet existing and expected demand of our
> incretin products, we have entered, and expect to continue to enter, into various agreements
> for contract manufacturing and for supply of materials."
> "The executed agreements could, under certain circumstances, require us to pay up to
> approximately **$4.5 billion** if we do not purchase specified amounts of goods or services
> over the durations of the agreements, which generally range from 2 to 8 years."

> **[rank 2] score=0.6937 | ELI LILLY & Co | FY2023 | ITEM_7**
> "As we expand our manufacturing capacity in order to meet existing and expected demand of our
> incretin products, we have entered, and expect to continue to enter, into various agreements
> for contract manufacturing and for supply of materials."
> "The executed agreements could, under certain circumstances, require us to pay up to
> approximately **$10 billion** if we do not purchase specified amounts of goods or services
> over the durations of the agreements, which generally range from 2 to 8 years."

These are the same passage from two different filings, differing in one number. Both are
genuinely on-topic — and both are the wrong year. The top **six** blocks for this query are all
FY2022/FY2023/FY2024. The first FY2025 block appears at **rank 7**, and it is the richest block
in the pool — 20 sentences, **7 core hits** — containing the actual 2025 discussion:

> **[rank 7] score=0.4626 | ELI LILLY & Co | FY2025 | ITEM_1A | cores=7**
> "Despite our ongoing efforts to meet projected worldwide demand for our products by obtaining
> additional internal and contracted manufacturing capacity, there can be no assurances that
> such capacity increases that we expect will be needed to meet future demand will be realized
> as expected or that we will meet demand in launched markets in the future."
> "Delays or challenges in operationalizing additional manufacturing capacity could limit our
> ability to capitalize on demand for our products."

**At `top_n = 4`, a question explicitly about the 2025 10-K returns zero FY2025 sentences.** At
top-8 the correct-year block survives by one position. That is the pruning policy working
almost entirely by luck.

The contrast case, same run: the NVIDIA 2025 export-controls query behaves well — ranks 1 and 2
are FY2025 Item 1A with 5 and 7 core hits and scores of 0.759 / 0.730, far above anything in the
gold cross-company set. When the query is a single company on a topic with distinctive
vocabulary, top-4 is sufficient. The failure is specific to topics whose language repeats across
years.

### 3.2 What gets dropped going 16 → 8 → 4, and whether it is safe

Mostly the dropped material is safe. Going from 16 to 8 on **P3V2-Q007** and the local questions
generally cuts genuine filler. The unsafe drops are concentrated and have a shape.

**P3V3-Q004** — *"In their 2009 Form 10-K risk-factor disclosures, how do Radian Group, Netflix
and Mastercard each describe their exposure to data protection, information security and
customer privacy risks?"* The top-8 is **8/8 Mastercard**; top-16 is **15/16 Mastercard**. The
top three blocks are Mastercard FY2022, FY2023 and FY2024 — near-identical text, wrong year:

> **[rank 2] score=0.2129 | Mastercard | FY2023** — "Damage to our reputation or that of our
> brands resulting from an account data breach of either our systems and networks or the systems
> and networks of our customers, merchants and other third parties could decrease the use and
> acceptance of our products and services." / "Such events could also slow or reverse the trend
> toward electronic payments."

> **[rank 3] score=0.2033 | Mastercard | FY2024** — "Damage to our reputation or brands resulting
> from an account data breach of our systems and networks or those of our customers, merchants
> and other third parties could decrease the use and acceptance of our products and services." /
> "Such events could also slow or reverse the trend toward electronic payments."

Meanwhile the single most on-point sentence in the entire pool — the labelled Netflix gold
evidence, which *is* the answer to a third of the question — sits at **rank 28 of 42**:

> **[rank 28] score=0.0334 | NETFLIX INC | FY2009 | ITEM_1A**
> "We are not insured against any losses or expenses that arise from a disruption to our business
> due to earthquakes and may not have adequate insurance to cover losses and expenses from other
> natural disasters."
> **\*GOLD\*** "Privacy concerns could limit our ability to leverage our subscriber data and our
> disclosure of or unauthorized access to subscriber data could adversely impact our business and
> reputation."
> "In the ordinary course of business and in particular in connection with providing our personal
> movie recommendations, we collect and utilize data supplied by our subscribers."

Two things are visible at once. The gold sentence is diluted — its block *opens* with an
earthquake-insurance sentence, and the cross-encoder scores the concatenation. And it scores
**6× lower** than wrong-year Mastercard boilerplate.

Worse, Radian's genuinely relevant FY2009 Item 1A blocks are ranked **40, 41 and 42 of 42** —
dead last, below every wrong-year Mastercard block. The only Radian content in the top 30 is a
FY2020 Item 7 block about COVID-19 mortgage defaults (rank 18): wrong year *and* wrong section.
**No value of `top_n` below ~40 gives this question Radian evidence.** That is a scoring failure,
not a budget failure, and it is a stronger statement than the prior docs make.

Also at rank 5 — kept at top-8, ahead of everything above — a pure cross-reference stub with no
informational content whatsoever:

> **[rank 5] score=0.1331 | Mastercard | FY2009**
> "See "Risk Factors-Legal and Regulatory Risks" in Part I, Item 1A."

That single navigational fragment outscores the Netflix gold sentence 4:1.

**P3V3-Q005** — *"For 2010, how do Walmart, Apple, Microsoft and Icahn Enterprises describe
their exposure to liquidity and credit-related risks in their Item 1A risk-factor discussions?"*
The highest-scoring block in the pool (0.4074) is not about liquidity or credit at all:

> **[rank 1] score=0.4074 | ICAHN ENTERPRISES L.P. | FY2010 | ITEM_1A | pos 1**
> "Risk Factors Risks Relating to Our Structure Our general partner and its control person could
> exercise their influence over us to your detriment."
> "Mr. Icahn, through affiliates, owns 100% of Icahn Enterprises GP, our general partner, and
> approximately 92.6% of our outstanding depositary units as of December 31, 2010..."

That is a governance risk. It ranks first for a liquidity/credit question. Note `pos 1` — it is
the *first sentence of the section*, so it carries the literal section-header text "Risk
Factors". The query says "Item 1A risk-factor discussions". Rank 7 is the same artifact for
Apple:

> **[rank 7] score=0.1774 | Apple Inc. | FY2010 | ITEM_1A | pos 1**
> "Risk Factors Because of the following factors, as well as other factors affecting the
> Company's financial condition and operating results, past financial performance should not be
> considered to be a reliable indicator of future performance..."

Content-free section preamble, kept at top-8. This looks like a systematic interaction between
how this project phrases queries (naming the SEC item) and the fact that position-1 sentences
carry section headings — worth knowing about, and cheap to test.

The genuinely responsive Apple block is rank 4, and it is good:

> **[rank 4] score=0.2408 | Apple Inc. | FY2010 | ITEM_1A**
> "The Company's exposure to credit and collectability risk on its trade receivables are
> increased in certain international markets and its ability to mitigate such risks may be
> limited."

And the decisive structural fact for this question: **Microsoft appears in the pool only as
FY2016, 2017, 2019, 2021, 2022, 2023, 2024 and 2025 Item 7 / Item 1 blocks. There is not one
Microsoft FY2010 Item 1A block in the entire 44-block pool.** Seven of those Microsoft blocks
are near-verbatim copies of the same MD&A currency paragraph:

> **[ranks 13, 15, 17, 19, 20, 21, 26] | MICROSOFT CORP | FY2016/2025/2022/2021/2019/2017/2024 | ITEM_7**
> "Many of these revenue and expenses are denominated in currencies other than the U.S. dollar."
> "As a result, changes in foreign exchange rates may significantly affect revenue and expenses."
> ...

This is why raising `top_n` to 16 "covers all four companies" for Q005 in a purely nominal sense
while making the *answer* worse — see Sec 5.1.

### 3.3 What the cross-encoder systematically over- and under-values in 10-K prose

From the read, and each checked against the 910-block dataset:

| pattern | evidence |
| :-- | :-- |
| **Over-values length.** Longer blocks score higher, monotonically. | Pearson r = **+0.285** (n=910). Mean score by block length: 1 sentence **0.161**, 2-3 **0.247**, 4-7 **0.292**, 8+ **0.364**. A lone gold sentence in a 1-sentence block competes against 8-sentence boilerplate agglomerations. |
| **Blind to fiscal year.** It scores text; `report_year` is never in the input. | Off-target-year blocks are longer (5.49 vs 4.04 sentences) and score higher (0.300 vs 0.219). Off-year share rises from 31.5% of the pool to **45.2%** of top-8. |
| **Over-values cross-references and section headers.** Navigational fragments and Item-1A preambles score in the top 8. | Q004 rank 5 ("See "Risk Factors-Legal and Regulatory Risks"…", 0.1331); Q005 ranks 1 and 7, both `pos 1` header sentences. |
| **Under-values single-sentence blocks, which is where sharp numeric facts live.** | 321 of 910 blocks are single-sentence, mean score 0.161. The 3 gold blocks that are single sentences average **0.193** — they would be pruned at essentially any `top_n`. |
| **Cannot deduplicate.** Near-identical passages get near-identical scores and therefore adjacent ranks. | 92.7% of top-8 blocks share `(company, section)` with another kept block from a different year. |

**A confound I tested and had to abandon.** I expected the gold/non-gold score separation
reported in `RERANKING_IMPACT_ANALYSIS.md` Sec 7.2 (0.518 vs 0.236) to be largely a length
artifact, since gold blocks are much longer on average (9.11 vs 4.36 sentences) and length
correlates with score. Controlling for length, it survives clearly:

| block length | gold mean | non-gold mean | gap |
| :-- | --: | --: | --: |
| 1 sentence | 0.193 (n=3) | 0.160 (n=318) | +0.033 |
| 2-3 | 0.359 (n=5) | 0.242 (n=135) | +0.117 |
| 4-7 | 0.611 (n=8) | 0.285 (n=364) | **+0.326** |
| 8+ | 0.610 (n=11) | 0.323 (n=66) | **+0.288** |

So the cross-encoder is doing real relevance discrimination on this corpus, not just counting
words. The length bias is real and additive, not the whole story. Sec 7.2's conclusion stands;
my hypothesis was wrong and I am recording that rather than quietly dropping it. The one place
it nearly vanishes is the 1-sentence bucket (+0.033), which is consistent with the
under-valuation row above.

---

## 4. Task B — LLM-as-judge on the 30 real answers

I read all ten `(gold, A, B, C)` triplets from
`validation_notebooks/15_reranking_answer_quality_scored_30q.json` and judged each config
against the question's gold `answer_text` on content coverage and factual calibration.
A = no rerank, B = top-16, C = top-8.

| # | question | scope | B vs A | C vs A | reasoning |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Q001 | Walmart LT debt 2018-2020 | cross_year | **same** | **same** | All three hit all three gold points (2018 higher-rate extinguishment, 2019 Flipkart, 2020 general-corporate + short-term paydown); C is tightest at 14k vs 24k chars with no content loss. |
| Q002 | Meta regulatory/AI risks over time | cross_year | **worse** | **worse** | Question asks "over time"; A spans FY2020-2025, B FY2021-2025, C only **FY2023-2025**. All three get privacy-restricts-ad-data and the EU AI Act; all three miss the FCPA point (the 2019 filing was never retrieved) and all three wrongly infer Meta does not disclose anti-corruption risk rather than flagging a retrieval gap. C loses half the temporal range the question is about. |
| Q003 | J&J COVID consumer/infectious 2022-2024 | cross_year | **same** | **better** | C correctly places the consumer-franchise tailwind in **2022**, matching gold; A and B both mis-assign it to 2023, and B additionally drifts into out-of-range FY2025 material. |
| Q004 | Radian/Netflix/Mastercard privacy 2009 | cross_company | **worse** | **worse** | A is the only config to answer all three companies, and it quotes the Radian and Netflix gold content near-verbatim — 3/3. C answers Mastercard only and honestly declines the rest. B is the worst outcome: it asserts Radian "made no mention of data protection, information security, or customer privacy risks" and then builds a confident business-model rationalisation on that false premise. |
| Q005 | Walmart/Apple/MSFT/Icahn liquidity 2010 | cross_company | **worse** | **worse** | A captures two gold points exactly (Apple's investment-portfolio credit quality; Icahn's cascading-institution default risk). B loses both, keeps only Icahn's covenant language, and states Microsoft's **2010** risk factors "did not prominently feature liquidity or credit risk" while citing FY2016 MD&A — a confident false-absence claim built on wrong-year evidence. C keeps Apple's gold point and honestly declines Walmart and Microsoft. |
| Q006 | Exxon/Lilly licensing + drug programs 2023 | cross_company | **same** | **worse** | A and B both hit both gold points (Exxon's ~$155M licensing revenue; Lilly's 340B/government pricing pressure). C gets Exxon but explicitly states "the provided excerpts do not contain explicit discussion of U.S. drug programs" — it loses the entire second half of the question. See Sec 5.2. |
| Q007 | Tesla Adjusted EBITDA 2022 | local | **same** | **worse** | A and B give the gold definition cleanly. C opens by claiming the 2022 definition is not in context, pivots to the **2025** 10-K definition, then contradicts itself by supplying the 2022 definition anyway — self-inconsistent and year-confused. |
| Q008 | Icahn Adjusted EBITDA 2011 | local | **same** | **better** | C is the **only** config that actually answers: it gives the full definition including gold's "discontinued operations and gains or losses on extinguishment of debt". A and B both hedge that the definition is not in the provided context. Aggressive pruning helped here. |
| Q009 | J&J infectious disease / COVID vaccine 2024 | local | **same** | **same** | All three answer "yes" correctly with the verbatim "primarily driven by a decline in COVID-19 vaccine revenue" attribution. C is marginally the cleanest. |
| Q010 | Meta other income / FX 2015-2016 | cross_year | **better** | **better** | Gold specifically notes one year increased and the other decreased. C is the only config that separates 2014-vs-2013, 2015-vs-2014 and 2016-vs-2015 correctly and so captures that contrast; B fixes A's year-attribution slip on the $87M figure. |

**Tally.** B (top-16) vs A: **1 better, 6 same, 3 worse.** C (top-8) vs A: **3 better, 2 same,
5 worse.**

**The pattern is not random, and it is more useful than "top-8 is too aggressive."** C's five
losses are all *breadth* questions — four cross-scope (Q002, Q004, Q005, Q006) plus Q007, where
it lost the target year. C's three wins (Q008, Q010, Q003) are all questions where the answer is
**one precise fact or attribution**, and stripping distractors let the model find it. So:

> Aggressive pruning helps when the answer is a single fact, and hurts when the answer must span
> multiple entities, years, or sub-topics. A single global `top_n` cannot serve both, which is
> the strongest argument in this whole body of work for conditioning the budget on the query —
> just not on entity count alone (Sec 5.1).

**The automated metrics do not merely miss this; on several questions they invert it.**
`RERANKING_ANSWER_QUALITY_TEST.md` Sec 5 flags that cosine/ROUGE-L cannot see incompleteness.
It is worse than that:

- **Q004:** ROUGE-L ranks C **highest** (0.118 vs A 0.079). C answers one of three companies.
- **Q005:** cosine ranks C **highest** (0.736 vs A 0.639). C declines two of four companies; A
  gets two gold points exactly.
- **Q002:** cosine ranks C **highest** (0.763 vs A 0.732). C covers three years of a six-year span.
- **Q010:** ROUGE-L ranks C **lowest** (0.088) on the one question where I judge C clearly best.

On this sample the automated metrics are close to uninformative about answer quality, and
occasionally anti-correlated with it. They are fine as cost/context instrumentation and should
not be used as a quality gate.

---

## 5. Where my read disagrees with, or complicates, prior conclusions

### 5.1 The entity-cardinality-conditioned `top_n` would not fix Q005, and top-16 made Q005 *worse*

`RERANKING_ANSWER_QUALITY_TEST.md` Sec 6 recommends "either raise the floor for multi-entity
queries or implement the entity-cardinality-conditioned `top_n`", and Sec 5 supports it by noting
that top-16 recovers entity coverage. Block-level, the coverage claim is true — distinct CIKs
surviving for Q005 go 2 (top-4), 2 (top-8), 3 (top-12), **4 (top-16)**.

But Microsoft's coverage at top-16 is supplied entirely by **FY2016 and FY2025 Item 7 currency
and seasonality boilerplate**. There is no Microsoft FY2010 Item 1A block in the pool at all.
And the answer text shows what the model does with that filler — config B, Q005, verbatim:

> "Microsoft's 2010 risk factor discussion similarly did not prominently feature liquidity or
> credit risk disclosures in the provided narrative sections. The company's MD&A discussion
> addressed foreign exchange exposure and seasonality but did not highlight material concerns
> about debt refinancing, credit availability, or liquidity constraints. **This pattern is
> consistent with Microsoft's strong balance sheet and cash generation capabilities during the
> 2010 period.**"

It has taken FY2016-2025 MD&A text, concluded something about FY2010 risk factors, and offered a
confident rationalisation. Gold says Microsoft's 2010 filing *does* discuss tax and regulatory
effects on cash flows. B does the same for Walmart. Config C, on the same question, simply says
it lacks Walmart and Microsoft data.

**So the entity-coverage framing has a failure mode of its own: satisfying an entity-count floor
with whatever blocks are available converts an honest refusal into a confident false negative.**
Between an answer that omits two companies and flags the omission, and one that covers all four
by fabricating absence claims from wrong-year evidence, the first is safer. This is why my
recommendation in Sec 1 is a coverage floor over `(company, year)` pairs rather than a raised N —
and why coverage must be satisfiable from *on-target* evidence or not claimed at all.

### 5.2 P3V3-Q006 does **not** show "the pattern not triggering" — top-8 damages it too

`RERANKING_ANSWER_QUALITY_TEST.md` Sec 5 states that Q006 "shows the pattern *not* triggering:
at top-8, 59 of 179 expanded sentences survived pruning — enough to keep both companies'
evidence — and the answer addresses both companies with no hedging (cosine spread across configs
for Q006 was only 0.018, the smallest of any cross-scope question)."

Reading config C's Q006 answer, it hedges extensively and fails half the question:

> "…though the filings do not explicitly connect these to broader revenue themes or **discuss
> U.S. drug programs in the excerpts available**."

> "**The provided excerpts do not contain explicit discussion of U.S. drug programs** or their
> effects on Eli Lilly's revenue in the 2023 filing."

Gold's second bullet is precisely the 340B/government-pricing point. A and B both deliver it;
C loses it. Q006 is therefore damaged at top-8 as well — so **all three `cross_company`
questions degrade at top-8, not two of three.**

The reason the earlier read missed it is that the diagnostic used was entity coverage plus
cosine spread. Both companies *were* present, and cosine barely moved (0.766/0.784/0.770), so
the question looked clean. The loss was **topical within an entity**, not entity-level: Lilly
content survived, but the drug-pricing subset of it did not. Entity coverage is not a sufficient
safety check, and the small cosine spread here is another instance of Sec 4's metric blindness
rather than evidence of no harm.

### 5.3 The `recall@5` / MRR flatness across the sweep is structural, not a finding about the cross-encoder

`RERANKING_IMPACT_ANALYSIS.md` Sec 7.1 reads the flat `recall@5` (0.137 at every `top_n`) as
"the cross-encoder's own ranking quality doesn't change with N, only how much of the same ranked
list survives." That interpretation is right but understates it: the flatness is a near-tautology
of how the metric is built. `kept_ids` is assembled from blocks already sorted by score
descending, so the *first five sentence IDs are identical for every `top_n` ≥ 1*. `recall@5`
cannot vary. `recall@30` likewise only moves between N=4 (27.9 sentences kept on average, fewer
than 30) and N ≥ 8, which is exactly what the table shows (0.406 → 0.470, then constant). Neither
column carries information about the pruning choice, and neither should be cited as evidence
about it.

### 5.4 Gate 0's bar was not achievable, so "below bar" overstates the reranker's weakness

`RERANKING_IMPACT_ANALYSIS.md` Sec 3 reports Gate 0 at 15/31 (48%) against a bar of ≥24/31 (77%)
and reads it as "below bar — moderate signal, not strong." My block-level equivalent reproduces
15/31 exactly: the gold-containing block is in the top 3 by score for 15 of 31 questions.

But gold is present in the candidate pool for only **25 of 31** questions. A ≥24/31 top-3 bar
therefore required the reranker to place gold in the top 3 for 24 of the 25 questions where that
is even possible — 96% conditional accuracy. The bar was mis-specified against a ceiling nobody
had measured yet (it was written before the harness ran, which is the right order to write bars
in, but it means the number needs re-reading now that the ceiling is known).

Conditional on reachability, the reranker's ranking is **strong**: 15/25 = 60% in the top 3,
10/25 at rank #1, and a **median normalized rank of 0.053**. Only three questions put gold in the
bottom half of the list (P3V3-Q005 at 0.791, P3V2-Q019 at 0.674, P3V3-Q004 at 0.659). Sec 7.2's
more optimistic calibration reading is the better-calibrated one, and Sec 3's "below bar" line
should not be read as evidence that the cross-encoder is weak on this corpus.

### 5.5 What holds up unchanged

Stated plainly, because most of it does:

- **Pruner-not-reorderer.** Verified again in `reranker.py` and `context_assembler.py`. Only
  membership reaches the LLM. Correct.
- **Token and cost savings.** Real and large (61% median context reduction, 32% cost at top-8).
  Not disputed.
- **The aggregate answer-quality null result.** Consistent with my judge pass at the *aggregate*
  level — B is 1 better / 6 same / 3 worse. There is no uniform effect. The action is in the tails.
- **The correction in `RERANKING_IMPACT_ANALYSIS.md`** (the struck-through 31/31 claim) is sound,
  and keeping the error visible was the right call. My only addition is Caveat 2 in Sec 2 about
  what the replacement number measures.
- **`min_score` earning its keep** (Sec 7.2, contra the guidance doc's prediction of 0.0
  permanently). My length/score data supports this independently: a small floor preferentially
  removes short, low-scoring blocks, and the ones it removes are overwhelmingly non-gold.
- **Strict-contiguous block grouping** (guidance doc Sec 3). It holds, though for a different
  reason than argued: the concern there was pruning resolution. The stronger reason from this
  data is that merging *lengthens* blocks, and length inflates score (r = +0.285), so bridging
  would amplify the existing bias toward long boilerplate agglomerations. The recommended
  max-block-size split would work *with* that grain, not against it.
- **The n=31 / n=10 power warnings.** Everything in Sec 4 is a described observation on ten
  questions, not a statistical claim, for exactly the reasons already documented.

---

## 6. Confidence and gaps

**Verified — I ran it or read it directly:**
- Notebook 13's survival column reproduced exactly from the cached blocks (38.7 / 54.8 / 58.1 /
  58.1 / 61.3 / 61.3 / 64.5 / 64.5%), and notebook 14's 910 blocks / 27 gold-containing / 12.0%
  overlap figure. The published numbers are honest summaries of what the code computed.
- `gold_survived` in notebook 13 is the strict conjunction `n_hits == len(gold_ids)` (read from
  source). Both survival definitions in Sec 2 are my own computation on the same data.
- Gold reachable in the pool for 25/31 questions; per-question gold-block ranks; the 5 questions
  lost to pruning at top-8; median normalized gold-block rank 0.053.
- Off-target-year rates (45.2% at top-8 overall; 47.4% for `local`; 31.5% pool base), redundancy
  rates, block-length/score correlation (+0.285), the length-controlled gold/non-gold table, and
  the on-year vs off-year length and score comparison. All computed from
  `rerank_scored_blocks_31q.json` (910 blocks).
- Every quoted sentence in Sec 3 — joined from Stage 1 parquet by `sentenceID`, or printed
  directly from the live `score_blocks()` run for the two fresh 2025 queries.
- Microsoft has zero FY2010 Item 1A blocks in the Q005 pool; Radian's FY2009 Item 1A blocks rank
  40-42 of 42 in the Q004 pool; Q004's top-8 is 8/8 Mastercard.
- Retrieval non-determinism between the notebook-13 and notebook-15 draws, including the
  differing gold coverage (Q004 2/3 vs 1/3; Q005 2/4 vs 1/4; Q002 1/4 vs 0/4).
- Stage 1 covers `report_year` 2006-2025, 43,851 sentences in 2025.
- All 30 answer texts read in full; the config-B Q005 and config-C Q006 quotations are verbatim.

**My judgement, argue with it:**
- Every cell of the Sec 4 judge table. Ten questions, one judge, no blinding — I knew which
  config produced which answer while judging, which is a real bias risk I cannot retroactively
  remove. The direction I would most suspect in myself is over-penalising C's refusals; note
  that on Q005 and Q004 I nonetheless judged C's *honest* refusal less damaging than B's
  confident false-absence claims, which runs against that bias.
- That "top-8 is not fit to ship" follows from 5-worse-of-10. Someone weighting the 32% cost
  saving more heavily could read the same table as acceptable.
- That the off-year contamination is the *binding* defect rather than one defect among several.
- That the section-header artifact (Q005 ranks 1 and 7, both `pos 1`) is a systematic
  query-phrasing interaction. Two instances is suggestive, not established.
- The coverage-floor design in Sec 1 item 3. Sketched, not prototyped, not measured.
- Reading Q008 as a case where pruning genuinely *helped* rather than got lucky.

**Unresolved / not measured — do not build on these:**
- **Whether the off-year rate is stable across retrieval draws.** Given Caveat 1, every number
  in Sec 3.3 comes from a single draw of the candidate pool. The direction is consistent across
  N = 4, 8, 16 and reproduced qualitatively on two fresh queries, but the magnitudes are one
  sample and blocks are correlated within question.
- **Whether a coverage floor would actually improve answers.** It would need its own run with
  real synthesis. My Sec 5.1 evidence says *nominal* entity coverage can hurt; it does not
  establish that *on-target* coverage helps.
- **Why the two retrieval draws differ.** Not diagnosed. Could be S3 Vectors ANN
  approximation, `_proportional_topk()` sampling, or something else. It affects the
  reproducibility of every retrieval measurement in this workstream and is worth ten minutes.
- **Whether top-16 + `min_score: 0.05` is actually non-inferior.** Never run as a config. My
  Sec 1 item 2 recommendation composes a measured `top_n` with a `min_score` measured separately
  in notebook 14; the combination is untested.
- **`local`-question behaviour at scale.** I read the text for only two of 24 `local` questions
  in depth (P3V2-Q007, P3V2-Q019). The off-year statistic covers all of them; the qualitative
  read does not.
- **Whether Q004's Radian ranking failure is representative.** It is the single worst scoring
  failure I found and I have one instance of it.
- **BERTScore and BLEURT** remain uncomputed (packages absent; installing them was out of scope
  for this pass, as for the previous one). Given Sec 4's finding that cosine and ROUGE-L are
  near-uninformative here, I would not expect two more reference-similarity metrics to change
  the picture — but that is an expectation, not a result.
- **Latency.** `last_call_stats()["latency_ms"]` exists and I did not collect a p50/p95 across
  the runs I made.

**One process note.** The graphify graph at `graphify-out/graph.json` is stale for this
workstream: `reranker.py` appears as an isolated node with no edges, `CohereReranker` is not in
the graph at all, and `graphify path "reranker.py" "supply_lines.py"` finds no path. It oriented
me correctly on the retrieval pipeline (`S3VectorsRetriever` → `SentenceExpander` →
`ContextAssembler`, `run_supply_line_2_rag`, `init_rag_components`) but cannot see the reranking
feature. A `graphify update .` would fix it and is free.
