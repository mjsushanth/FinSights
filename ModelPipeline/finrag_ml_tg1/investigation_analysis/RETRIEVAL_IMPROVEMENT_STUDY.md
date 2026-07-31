# Retrieval Improvement Study — Sparse, Hybrid, Reranking

**Date:** 2026-07-29 · **Scope:** read-only code + evidence study, no code written, no paid API calls
**Question asked:** does FinSights need (a) sparse/lexical retrieval, (b) hybrid fusion, (c) cross-encoder reranking?

Every claim below is tagged **[V]** verified (I read it / measured it) or **[I]** inferred.
External facts carry source URLs. No number here is invented.

---

**Note on deployment history:** Lambda was researched extensively throughout this study but never
deployed to production; ECS Fargate was the only deployment that ever served real traffic. Any
Lambda-specific constraint discussed below (cold starts, package size, etc.) is historical reasoning
from that research, not a live limitation of the running system.

---

## 0. Executive answer

| Option | Verdict | One-line reason |
|---|---|---|
| **(a) Sparse / BM25 retrieval path** | **SKIP the retrieval path. Add a narrow lexical *gate* instead.** | The dominant failure mode is *boilerplate crowding*, and boilerplate is exactly what has the highest lexical overlap. BM25 would amplify the disease. Your own gold labels were picked by a lexical selector and it chose the wrong sentence in at least 5 of 31 cases — that is a measured indictment of lexical-only matching *in this corpus*. |
| **(b) Hybrid fusion (RRF / score norm)** | **SKIP.** | Nothing to fuse. Your 5 retrieval calls already share one score space, so RRF adds no information; and you have no second ranked list until BM25 exists. The fusion you actually need is *entity/year quota allocation*, not rank fusion. |
| **(c) Cross-encoder reranking — Cohere Rerank 3.5** | **DO IT — but 4th in line, and via Bedrock, not the Cohere key.** | The measured similarity band across your top-45 candidates is **0.674–0.737** — 0.063 wide, zero rejections at any threshold. There is nothing left to discriminate on. A cross-encoder is the only tool that reads the query and the sentence together. And paired with context trimming it is **cost-neutral to cost-negative**, so it does not violate your cost rule. |

**Highest-value recommendation is none of the three.** It is a weekend batch: three retrieval-correctness
bugs (§3) plus a recall@k harness on ground truth you already own (§7). ~2 developer-days, **$0**,
and it is a hard prerequisite for claiming any of (a)/(b)/(c) helped.

**Correction to the premise you handed me:** you do not need the Cohere production API key.
Bedrock exposes Cohere Rerank 3.5 natively as `cohere.rerank-v3-5:0` via the `bedrock-agent-runtime`
client's `Rerank` operation, **supported in us-east-1** (your region), at **$2.00 per 1,000 queries**
where one query = up to 100 document chunks. Same boto3, same IAM, no key management, no new dependency. **[V]**
Sources: <https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-supported.html> ·
<https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Rerank.html> ·
<https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-pricing.html> · <https://aws.amazon.com/bedrock/pricing/>

---

## 1. What retrieval actually does today (traced in code)

### 1.1 The live path

`answer_query()` → `build_combined_context()` → two supply lines → Bedrock.
Composition root: `synthesis_pipeline/supply_lines.py:64` `init_rag_components()` **[V]**

```
query
 ├── SL1 (KPI)  supply_lines.py:135  run_supply_line_1_kpi()
 │     EntityAdapter.extract()  →  MetricPipeline.process()  →  format_analytical_compact()
 └── SL2 (RAG)  supply_lines.py:171  run_supply_line_2_rag()
       :207  EntityAdapter.extract(query)
       :210  QueryEmbedderV2.embed_query(query, entities)          -> 1024-d
       :213  MetadataFilterBuilder.build_filters(entities)         -> "filtered" filter
       :214  MetadataFilterBuilder.build_global_filters(entities)  -> "global" filter
       :217  S3VectorsRetriever.retrieve(...)                      -> 5 QueryVectors calls
       :225  SentenceExpander.expand_and_deduplicate(union_hits)   -> +/-3 sentence windows
       :228  ContextAssembler.assemble(unique_sents)               -> headered string
merge  supply_lines.py:249  build_combined_context()
```

### 1.2 The five S3 Vectors calls

`rag_pipeline/s3_retriever.py:225-253` **[V]**

| Call | Embedding | Filter | topK | Config anchor |
|---|---|---|---|---|
| 1 | base query | filtered | **30** | `ml_config.yaml:359` |
| 2 | base query | global | **15** | `ml_config.yaml:360` |
| 3–5 | variant 1–3 | filtered **only** (`global_filters=None`, `s3_retriever.py:248`) | **15** each | `ml_config.yaml:361`, `:339` |

Up to **90 raw hits** → dedup by `(sentence_id, embedding_id)` (`:486`) → sorted by distance (`:507`)
→ hard cap **30** via `_proportional_topk` (`:517`, `max_hits_before_expansion: 30`, `ml_config.yaml:380`)
at **70/30 filtered/global** (`ml_config.yaml:381-382`). **[V]**

Then `SentenceExpander` expands each of the 30 hits by ±3 sentences (`ml_config.yaml:364`) →
~210 records → dedup → **80–199 sentences** in practice (measured, §2.1). **[V]**

`min_similarity: 0.3` is applied in `_parse_response` as `similarity = 1.0 - distance/2.0`
(`s3_retriever.py:412-414`). The config comment at `ml_config.yaml:384-388` already concedes
"for normal queries, threshold=0.3 rejects nothing useful" — confirmed empirically in §2.4. **[V]**

### 1.3 How metadata filters are built

`rag_pipeline/metadata_filters.py` **[V]**

| Filter | Conditions | Anchor |
|---|---|---|
| **filtered** | `cik_int` ($eq/$in) AND `report_year` ($eq/$in, prefers `past_years`) AND `section_name` ($eq or `$or`-list), `$and`-wrapped | `:94-143` |
| **global** | `cik_int` (if any) AND **`report_year >= recent_year_threshold` — hardcoded 2015, entity years ignored** | `:165-176` |

`_extract_section_list` (`:188`) pulls `sections.items` + `sections.primary`.
Section canonicalisation ("Item 1A" → `ITEM_1A`) happens upstream in
`entity_adapter/section_extractor.py:57-62` via `SECTION_ITEM_PATTERNS` regexes, with a
priority order `ITEM_7 > ITEM_8 > ITEM_1A > ITEM_1 > ITEM_7A` (`:39-46`). Risk keywords
also force `ITEM_1A` as a candidate (`:92-95`). **[V]**

### 1.4 The variant subsystem — what it actually contributes

`rag_pipeline/variant_pipeline.py:120` + `variant_generator.py:59` **[V]**
Haiku 4.5 (`ml_config.yaml:336`), `count: 3`, `temperature: 0.7`, `max_tokens: 150`.
Prompt (`ml_config.yaml:346-352`): *"Rephrase this financial query 3 different ways while preserving
the exact intent and entities. Keep the same companies, years, and sections mentioned."*

Per variant: re-extract entities (`variant_pipeline.py:204`) then re-embed (`:208`).
So per query: **1 Haiku call + 4 Cohere embed calls + 5 QueryVectors calls.**

**This is multi-query retrieval, and it is strictly dense-side.** The prompt explicitly instructs
the model to *preserve* entities and phrasing anchors, which means variants land in nearly the
same neighbourhood as the base query. It cannot introduce a lexical signal the dense encoder lacks,
because every variant is consumed only as a 1024-d vector. **[I]**

Worse, it inherits the base query's filter. All three variant calls use the *same* `filtered_filters`
(`s3_retriever.py:246`), so **if the filtered call returns zero, all three variants return zero too** —
and that is exactly what was logged (§2.3). The 3 Haiku calls are then pure waste.

### 1.5 What the LLM finally sees

`build_combined_context()` (`supply_lines.py:249-318`) concatenates, in order: **[V]**

```
[SL1 KPI block]        format_analytical_compact()
(blank line)
[SL2 header]           "NARRATIVE CONTEXT - SEC FILINGS"   supply_lines.py:231-236
[SL2 body]             ContextAssembler.assemble()
[footer]               "USER QUESTION" + query             supply_lines.py:310-315
```

`ContextAssembler` sorts by `(company_name, report_year ASC, section_name, doc_id, sentence_pos)`
(`context_assembler.py:242-248`) and emits a header on every `(company, year, doc, section)` change
(`:277`, `:354-360`):

```
=== [XOM] EXXON MOBIL CORP | FY 2016 | Doc: 0000034088_10-K_2016 | Item 15: Exhibits and Financial Statement Schedules | Sentences: ..._23 - ..._46 ===
```

**Critically: there is no score, no rank, and no relevance signal in the context.** `context_assembler.py:46`
says so outright — *"No scores, no metadata, clean provenance only"* — and `:52` *"No topK limiting"*.
Distance is thrown away at assembly. The LLM receives 80–199 sentences in chronological order with no
indication of which ones the retriever thought mattered. **[V]** That is a real cost: the ranking
work upstream is discarded before the only component that could use it.

`rag_pipeline/reranker.py` exists and is **0 bytes** — a placeholder never filled
(`sentence_expander_contract.py:480` "Empty placeholder (future)"). `ContextBlock` already carries
`base_score` and `final_score  # After reranking` (`rag_pipeline/models.py:201-202`). The slot was
designed and left empty. **[V]**

---

## 2. Evidence of failure modes

### 2.1 Boilerplate crowding — the dominant, measured problem

I measured the 25 real exported contexts in `rag_modules_src/exports/contexts/` **[V]**:

| Metric | Value |
|---|---|
| Contexts analysed | 25 |
| Median sentences per context | **100** (range 74–199) |
| Median context size | **21,119 chars** (range 15,210–52,082) |
| Mean **exact-duplicate** sentences per context | **22.0** |
| Mean near-duplicate (60-char prefix) | **28.6** |
| **Mean near-duplicate rate** | **22.7% of the context** |

And in the corpus itself (`data_cache/stage1_facts/finrag_fact_sentences.parquet`, 614,787 rows) **[V]**:

| Metric | Value |
|---|---|
| Unique sentence **texts** | 338,869 of 614,787 |
| **Exact-duplicate text rate** | **44.9%** |
| Distinct texts appearing >1x | 98,825 |
| ...of which cross-**company** | only 827 (12,708 occurrences, 2.1%) |

So the redundancy is overwhelmingly **one company repeating a sentence verbatim across filing years**.
Top offender: *"Because of its inherent limitations, internal control over financial reporting may not prevent..."*
— 424 occurrences across all 25 companies. **[V]**

**Root cause, in code:** the final dedup key is
`(sentence_id, cik_int, report_year, section_name)` — `sentence_expander.py:517`. Purely identity-based.
The same verbatim sentence in FY2016 and FY2017 has two different `sentence_id`s, so it survives twice.
Both instances also score near-identically in cosine space, so they arrive adjacent in the ranking and
consume two of your 30 slots. **Nothing in the pipeline ever compares sentence text.** **[V]**

This matches the framework doc's own diagnosis, `validation_notebooks/06_Gold_Test_Framework.md:159-162` **[V]**:
> "**ITEM_1A Boilerplate Dominance** — templated language ... **Cosine similarity approaches 0.95+ for
> boilerplate, drowning out true local context.** *Example*: Walmart ITEM_1A sentence #78 retrieved
> Microsoft #142, Apple #204, Tesla #95 before Walmart #77."

### 2.2 ITEM_15 is not leakage — it is mis-sectioned real content (CORRECTED)

`ml_config.yaml:222` sets `exclude_sections: [ITEM_15, ITEM_16]`, exposed as
`MLConfig.exclude_sections` (`loaders/ml_config_loader.py:293`), **printed** (`:946`), and used as a
filter **nowhere**. **[V]** ITEM_16 does not exist in the corpus at all (0 rows). **[V]**

My first pass called ITEM_15 "boilerplate leakage" because the Exxon exports are full of
"FREQUENTLY USED TERMS" and auditor language. **That reading was wrong.** On inspection: **[V]**

| Company | ITEM_15 sentences | ITEM_7 (MD&A) | ITEM_8 (Fin. Stmts) |
|---|---|---|---|
| EXXON MOBIL | **8,212** | 663 | 546 |
| ORACLE | **8,531** | — | — |
| NVIDIA | **6,528** | — | — |
| COSTCO | 2,470 | — | — |
| NETFLIX | 2,428 | — | — |

ITEM_15 has the **highest `likely_kpi` rate of any section (24.9%)**, above ITEM_7 (24.2%) and
ITEM_8 (19.7%). **[V]** Sampled ITEM_15 `likely_kpi` sentences are real financials, not boilerplate:

> *"Index to Financial Statements MANAGEMENT'S DISCUSSION AND ANALYSIS ... Upstream earnings for 2006 totaled $26,230 million"*
> *"Net income for 2006 included a $410 million gain from the recognition of tax benefits related to historical investments in non-U.S. assets."*

Only **4,952 of 36,949 (13.4%)** ITEM_15 sentences match auditor/exhibit boilerplate patterns
(`PCAOB|Report of Independent|we conducted our audit|Exhibit|incorporated by reference`). **[V]**

**Cause:** filers like Exxon, Oracle and NVIDIA incorporate the whole financial section into Item 15
by reference, and the section parser followed the document structure faithfully. Exxon's real MD&A
lives in ITEM_15, not ITEM_7.

**Two consequences:**

1. **`exclude_sections` must never be switched on.** Enforcing it would delete the majority of
   Exxon's, Oracle's and NVIDIA's financial narrative. Its being dead code was a lucky accident.
   **Comment the key out and annotate why.**
2. **Section-filter exposure — RETRACTED as a separate recommendation.** I first suggested making
   `section_name` a "soft boost" instead of a hard `$and`. **That was wrong on two counts and I
   withdraw it:**

   - **`$and` is the correct operator and the correct design.** `build_filters` composes a
     conjunctive predicate, which is exactly what "company X, year Y, section Z" means. Deterministic
     and right. There is also no alternative: **S3 Vectors offers ANN + metadata filtering only —
     there is no scoring hook, no boost primitive, no soft weighting.** "Soft boost" is not
     implementable inside a `QueryVectors` call. My phrasing implied a capability the service
     does not have.
   - **The architecture already has the escape hatch.** `build_global_filters`
     (`metadata_filters.py:160-186`) deliberately includes **only** `cik_int` and `report_year` —
     **no `section_name`**. **[V]** The global call *is* the unsectioned relaxation. The two-call
     filtered+global design already covers the mis-sectioned-filer case by construction.

   The residual exposure is real but it is **not a new bug** — it is bug §3.2 wearing a different
   hat. If an Exxon question filters to ITEM_7+ITEM_8, the filtered call searches 1,209 sentences
   instead of the 8,212 holding the answer; the global call is supposed to rescue it, **and can only
   do so if its year floor is not broken.** Fixing §3.2 fixes this. **No separate work item.**

### 2.3 The filtered path and all three variants returning zero — logged, live

`02_LLMEval_Notebooks/09_ITest_LLM_Serves_P3.ipynb` cell 5, query = P3V3-Q001
(Walmart long-term debt 2018–2020) **[V]**:

```
  ✓ Base query: 15 raw hits
→ Retrieving 3 variant queries (filtered only)...
  ✓ Variant 1: 0 hits
  ✓ Variant 2: 0 hits
  ✓ Variant 3: 0 hits
  • Filtered: 0 hits
  • Global:   15 hits
```

The filtered call and all three paid Haiku variants returned `{"vectors":[]}`. The entire
multi-path architecture collapsed to the single unfiltered global call, which then hit
`_proportional_topk` **edge case 2** (`s3_retriever.py:567-572`) and took everything from global.

Recall against the gold labels for that question (**[V]** log data, **[I]** my arithmetic):
gold = `2018_section_7_142`, `2018_section_7_224`, `2019_section_7_209`, `2020_section_7_219`.
Retrieved core hits: 1× 2018, 2× 2019, **12× 2020**.
→ **core recall@15 = 2/4 = 50%**; 3/4 = 75% after window expansion; `2018_section_7_142` unrecoverable
(nearest 2018 hit is 82 positions away). One 2018 sentence retrieved for a three-year question.

### 2.4 The score distribution is flat — this is the reranking argument

`08_RAGArch_DesignNotes.ipynb` cell 17 **[V]**, verbatim:
> ```
> All thresholds (0.0 → 0.5): 45 hits, NO rejections
> Similarity range: [0.674, 0.737]   Mean: 0.693, Median: 0.687
> Zero hits below 0.6 similarity, Zero hits above 0.8 similarity
> no "long tail" of weak matches to filter out AT ALL.
> ```

Your top-45 candidates occupy a **0.063-wide** band. Cosine similarity carries essentially **zero
ordering information** at this granularity. No threshold, no min-max normalisation, and no rank
fusion can extract signal that is not there. Only a model that reads the query *and* the candidate
jointly can. This single measurement is the strongest evidence in the repo for a cross-encoder.

### 2.5 The only recorded retrieval metrics are damning

`validation_notebooks/05_GoldP1P2_TestSuite.ipynb` cells 9 & 12, 60 anchors **[V]**:

| Regime | Self@1 | **Hit@1** | Hit@3 | Hit@5 | MRR@30 |
|---|---|---|---|---|---|
| P1 filtered | 96.7% | **0.0%** | 58.3% | 66.7% | 0.311 |
| P1 open | **58.3%** | **0.0%** | **0.0%** | **0.0%** | 0.036 |
| P2 filtered (covered) | 100% | **0.0%** | 75.0% | 80.0% | 0.379 |
| P2 open (covered) | 62.5% | **0.0%** | 0.0% | **2.5%** | 0.032 |

**Hit@1 = 0.0% in every regime, both phases.** The nearest non-self neighbour is never a gold
neighbour. And open-regime `Self@1` of 58.3% means that **~40% of the time, unfiltered search does not
return the query sentence itself at rank 1** — duplicate boilerplate outranks the exact sentence.
That is §2.1 showing up as a metric.

Caveat: this anchor task is a synthetic neighbour-retrieval probe, not the production query path;
every "hardest case" row is Exxon (`cik=34088`) and 36 of 60 anchors sit in <10-sentence sections.
Unrepresentative sample. **[V]**

**Also: the summary doc does not match the notebook.** `06_Gold_Test_Framework.md:99-101` reports
P1 filtered Hit@1 **45.0%** and open Hit@1/3/5 **21.7%/46.7%/61.0%** where the notebook recorded
**0.0%** across the board; `:251` claims P2 coverage 91.7% vs the notebook's 66.7%; `:256` claims
open Hit@5 61.8% vs 2.5%. Divergences up to **60 percentage points**. The doc also cites a
"6-month retrospective Feb–July 2024", an "April 2024 P1 incident", "Q1 2025 BERTScore 0.834", and
"cross-year Hit@5 61%→79%" — **none of which have any backing artifact in the repo.** **[V]**
Treat `06_Gold_Test_Framework.md` numbers as unreliable and the notebook outputs as ground truth.

### 2.6 Wrong-year context — 35% of exported queries

I checked all 23 response exports, comparing extracted years against `| FY nnnn |` headers
actually present in the delivered context **[V]**:

| | count |
|---|---|
| Exports where the asked year is **entirely absent** from the context | **8 / 23 (35%)** |
| Asked years in those failures | 2008 (×2), 2009 (×3), 2011, 2022 (×2) |
| Year range present in **every** context | 2016–2020 only |

At the time these ran the index covered 2016–2020, so part of this is old-corpus coverage. **But the
code-level cause is independent and survives the revival** — see §3.2. The new corpus spans
**2006–2025** and **23.8% of it (146,203 sentences) is pre-2015** **[V]**, i.e. permanently invisible
to the global call.

Grounding held up well: the LLM refused or explicitly flagged the year gap in every case, e.g.
*"the narrative context I have access to only includes excerpts from ExxonMobil's 10-K filings for
fiscal years 2016 through 2020"* (`response_20251120T015127.json`). The prompt is doing its job. **[V]**

### 2.7 Multi-company starvation — deterministic

| Export | Asked | Blocks retrieved | Missing entirely |
|---|---|---|---|
| `...T002411` | MSFT, NVDA | MSFT **3**, NVDA **10** | — |
| `...T130446` / `T013735` / `T014649` | MA, NFLX, RDN | MA 4, RDN 2, **NFLX 0** | **NFLX** |

**[V]** Netflix received **zero** context in all three runs. Cause: the filter is
`cik_int {"$in": [3 ciks]}` with a single global topK — ANN returns the globally best 30 regardless
of company, so a company whose sentences are slightly further from the query gets nothing. There is
no per-entity budget anywhere in `s3_retriever.py`. The MSFT/NVDA split (3 vs 10) shows the same
imbalance in milder form. **[V]** Only 3 of 31 gold questions are `cross_company`, but two of them
have 3–4 companies — so this affects 100% of the multi-company gold set.

### 2.8 No retrieval telemetry exists

`synthesis_pipeline/query_logger.py:88-176` logs exactly: `timestamp, query, model_id, input_tokens,
output_tokens, total_tokens, cost, context_length, processing_time_ms, error, error_type, stage,
context_file, response_file`. **No hit counts, no retrieved sentence IDs, no distances, no
per-source breakdown, no variant queries.** **[V]**

`retrieval_stats` is declared in the API contract (`serving/backend/models.py:86`) and is **`null`
in every response export I opened**. **[V]** So a filtered call returning 0 hits is invisible: it is
not an error, and `10_ITest_LLM_Log_Analytics.ipynb` accordingly reports `Failed Queries: 0` across
59 logged queries. **You currently cannot detect the §2.3 failure in production.**

### 2.9 What was measured vs. what was not

| Measured | Never computed |
|---|---|
| Self@1 / Hit@1,3,5 / MRR@30 on a 60-anchor synthetic probe | **recall@k / nDCG@k / MRR against `evidence_sentence_ids`** |
| ROUGE-L, BERTScore-F1, BLEURT, cosine — on **6** questions | Any per-question retrieval pass/fail on the 31q suite |
| Latency, tokens, cost | Any BM25 / sparse / hybrid baseline (**zero runs**) |
| S3 Vectors filter-grammar conformance | Any reranker run |
| Entity extraction across adversarial queries | Numeric-answer accuracy (`tolerance` is null in every suite used) |

**[V]** And the headline "31-question suite, BERTScore 0.826" in `06_Gold_Test_Framework.md:936-939,1160`
is actually **n=6** — `11_ITest_AnsScoring.ipynb` cells 8-9 evaluated P3V3-Q001, P3V2-Q006, P3V3-Q004,
P3V3-Q007, P3V3-Q002, P3V2-Q001 and nothing else. The derived difficulty and scope tier tables in that
doc cannot have been computed. **[V]**

---

## 3. Three bugs that outrank all three options

These are not enhancements. They are defects in the existing dense path, and each is larger than
the expected gain from a reranker.

### 3.1 The query is embedded as a *document* — BUG, free to fix

`QueryEmbedderV2` sends `input_type` from the **corpus** model block: **[V]**

- `ml_config.yaml:214` — `cohere_embed_v4: { ..., input_type: search_document }`
- `utilities/query_embedder_v2.py:66` — `input_type=model_cfg["input_type"]`
- `utilities/query_embedder_v2.py:226` — `"input_type": self.cfg.input_type,   # e.g. "search_document" or "search_query"`

So **user queries are embedded with `input_type="search_document"`.** Cohere's docs are explicit:
*"the search query should be embedded by setting `input_type="search_query"` [and] the text passages
that are being searched over should be embedded with `input_type="search_document"`"* — the embeddings
are "optimized for different types of inputs."
Source: <https://docs.cohere.com/docs/embeddings> **[V]**

The intent was right and got lost in a config refactor: `ml_config.yaml:266` is commented
*"## query_embedding - user submission query uses exactly this config"* and `:272` sets
`input_type: search_query` — but that whole `rag_orchestrator` block is flagged as legacy/superseded
in `CLAUDE.md` and **is not read by the live path**. The deprecated block has the correct value;
the live block has the wrong one. **[V]**
(The older `utilities/query_embedder.py:44` also defaulted correctly to `search_query`; V2 regressed it.)

#### 3.1.1 What `input_type` actually is — and why "same model both sides" is not the same claim

Two separate requirements get conflated here. **You are right about the first and it is not in
dispute:**

| Requirement | Rule | Your status |
|---|---|---|
| **Same model, same dimensionality** | Mandatory. Query and corpus vectors must come from `cohere.embed-v4:0` at 1024-d or the cosine numbers are meaningless. | **Correct already.** Both sides use `cohere.embed-v4:0`, `output_dimension: 1024` (`query_embedder_v2.py:228`, and the dim is asserted at `:210-214`). |
| **Same `input_type`** | **Must be *different*.** `search_document` for the corpus, `search_query` for the query. | **Wrong.** Both sides send `search_document`. |

`input_type` is **not** a model selector. It is a per-call task instruction. Cohere v3/v4 are trained
as **asymmetric dual-encoders**: one shared set of weights, but the input is tagged with the task so
the model projects into the right "view". The API reference is explicit that the parameter is
*required* for v3 and newer and enumerates `search_document` = "vector database storage",
`search_query` = "querying vector databases".
Source: <https://docs.cohere.com/reference/embed> · <https://docs.cohere.com/docs/embeddings> **[V]**

Concretely, the training objective differs:

- **`search_document` ↔ `search_document`** is optimised for *"is this passage like that passage?"* —
  a **symmetric** similarity. Good for dedup and clustering.
- **`search_query` → `search_document`** is optimised for *"does this passage **answer** this
  question?"* — an **asymmetric** relevance. That is retrieval.

A question and its answer are usually *not* textually similar. "What was Exxon's 2008 revenue?" and
"Total revenues and other income were $477,359 million" share almost no vocabulary and have opposite
grammatical shape. The asymmetric objective is what bridges that gap. Send `search_document` on the
query side and you have asked the model the wrong question — you get *"find text that resembles my
query as a piece of prose"* rather than *"find text that answers it."*

#### 3.1.2 Why I think this is *your* bug, not a generic nitpick

The predicted symptom of symmetric-similarity-on-an-asymmetric-task is that retrieval returns text
that **talks about** the topic instead of text that **states** the fact — definitions, cross-references,
section headers, meta-commentary. That is precisely the pattern all over your artifacts:

| Observation | Anchor |
|---|---|
| Exxon revenue query returned *"Reference is made to the following in the Financial Section of this report"* | `09_ITest_LLM_Serves_P3.ipynb` cell 2 (author's own bad-question note) |
| J&J "cash flow from operations" query returned the **auditor's opinion boilerplate** | ibid. |
| Eli Lilly "net income" query returned *"A 5 percent change in the valuation allowance would result in a change in net income of ~$25 million"* | ibid. |
| Apple EPS query returned *"The following table sets forth the computation of basic and diluted earnings per share"* — the **header**, not the value | `p3_gold_test_suite_31q.json` P3V2-Q005 |
| Retrieved contexts dominated by *"FREQUENTLY USED TERMS"*, *"FORWARD-LOOKING STATEMENTS"*, ROCE **definitions** | 25 exports in `rag_modules_src/exports/contexts/` |
| Open-regime `Self@1` only 58.3% — near-duplicate prose outranks the exact sentence | `05_GoldP1P2_TestSuite.ipynb` cell 12 |

Every one of those is "topically adjacent prose beat the actual answer." The author diagnosed these
as *gold curation* faults. Some are. But the **retriever produced those sentences in the first
place**, and a symmetric query encoder is a mechanism that explains it. **[I] — this is a hypothesis
that fits the evidence, not a proven cause.** It is also cheap and decisive to test, which is why it
is #1.

#### 3.1.3 What you do NOT have to redo

**Your corpus embeddings are correct. Do not re-embed anything.** `search_document` is the right
value for the 614,787 corpus sentences, and that is what `embedding_generation.py:315` sends via
`MLConfig.bedrock_input_type` (`ml_config_loader.py:225-228`). The in-flight Bin 3 job is fine.
**Only the single query-side call changes.** Zero re-embedding cost, no re-upload, no index rebuild.

The fix is a config-shape change, not an edit to `ml_config.yaml:214` (which correctly describes the
corpus): give `EmbeddingRuntimeConfig` a separate query-side `input_type` defaulting to
`search_query`, so `query_embedder_v2.py:66` stops borrowing the document-side value. The
already-correct value sits unused at `ml_config.yaml:272`.

**Effort: ~15 minutes. Cost: $0. Latency: 0.** Do not skip this before benchmarking anything else —
every retrieval measurement you take today is taken on a mis-specified query encoder. I am **not**
claiming a magnitude; Cohere documents the correct usage but does not publish the penalty for
getting it wrong. It must be A/B'd, and §7 is how.

### 3.2 The global filter throws away the requested year — BUG

`metadata_filters.py:176`:
```python
conditions.append({"report_year": {"$gte": self.recent_year_threshold}})   # hardcoded 2015
```
`build_global_filters` never reads `entities.years`. **[V]** Consequences on the *new* 2006–2025 corpus:

- **23.8% of the corpus (146,203 sentences) can never be reached by a global call.** **[V]**
- For any pre-2015 question, the global call returns *definitionally wrong-year* content, and
  `global_proportion: 0.30` guarantees it **9 of 30 slots**. **[V]**
- If the filtered call is thin or empty, `_proportional_topk` edge case 2 (`s3_retriever.py:567-572`)
  hands the **entire** context to those wrong years. That is §2.3 + §2.6 combined.
- **12 of 31 gold questions (39%) target pre-2015 years** — P3V2-Q001, Q002, Q005, Q010, Q012, Q013,
  Q019, Q020, Q021, P3V3-Q004, Q005, Q008. **[V]** You cannot evaluate 39% of your suite until this
  is fixed.

**Fix:** make the global filter *relax around* the requested years rather than replace them —
e.g. `report_year $in [y-2 .. y+2]` when years were extracted, falling back to the 2015 floor only
when no year was found. The "temporal diversity" rationale (`s3_retriever.py:6`) is preserved;
the wrong-era leak is not. **Effort: ~1 hour. Cost: $0.**

### 3.3 Dedup never looks at text — BUG-adjacent

Covered in §2.1. Fix: add a normalised-text key to `_deduplicate_sentences`
(`sentence_expander.py:517`), collapse to the best-scoring instance, and record the collapsed years
in provenance so the LLM still learns "this language is unchanged FY2016–FY2020" — which for
cross-year questions is *the answer*, not noise.

**Effort: ~2 hours. Cost: $0. Reclaims ~23% of the context window** (measured, §2.1) — which
directly reduces LLM input tokens, i.e. it *cuts* your dominant cost line.

Also worth 10 minutes: actually enforce `exclude_sections` (§2.2), or delete the config key.
Right now it is a lie in the config file.

---

## 4. Verdicts on the three options

Cost baselines used throughout, all **[V]**:
LLM synthesis is **~98% of variable per-query cost** (`S3Vect_QueryCost.md:249` — *"Vector Costs:
Still <2% of total"*). Recorded medians from the 23 response exports: Haiku 4.5 **$0.00896**
(median 5,388 input tokens), Sonnet 4.5 **$0.02697** (5,566 input tokens). `PIPELINE_LATENCY_ANALYSIS.md:37-39`
records a heavier average shape: 13,842 in / 1,960 out → **$0.024**. S3 Vectors ~$0.0003–0.00045/query
(`S3Vect_QueryCost.md:169-173`). Variant generation ~$0.0001 (`IMPLEMENTATION_GUIDE.md:246`).
Pipeline overhead is a constant **7.2s**, LLM is **71.6%** of latency, P50 **27.9s**
(`PIPELINE_LATENCY_ANALYSIS.md:16-21,36`).

### 4.1 (a) Sparse / lexical retrieval alongside dense

**Verdict: SKIP as a retrieval path. Add a narrow lexical gate instead.**

| | |
|---|---|
| Expected quality gain | **Low, possibly negative,** as a co-equal retrieval path |
| Added cost / query | **$0** (local) |
| Added latency | ~20–50ms query (`08_RAGArch_DesignNotes.ipynb` cell 3, author's own estimate) + index build |
| Effort | 2–3 dev-days for a real hybrid path; **0.5 day** for the narrow gate |
| Variant interaction | Genuinely complementary in principle — variants are dense-only |

**Why I am arguing against the full path**, and this is where I disagree with the repo's own
`06_Gold_Test_Framework.md:171` ("BM25 fusion: lexical overlap complements embedding similarity"):

1. **Your dominant failure mode is high-lexical-overlap boilerplate.** 44.9% exact-duplicate text
   (§2.1); *"may materially and adversely affect our business..."* identical across companies
   (`06_Gold_Test_Framework.md:159`). BM25 scores that boilerplate *highly*, and dedup by identity
   won't catch it. BM25 makes §2.1 worse, not better. **[I]**, from **[V]** measurements.
2. **You have a natural experiment showing lexical selection fails on this corpus.** Your gold
   evidence was picked by regex keyword matching (`Net Income: (?i)\bnet (income|loss)\b`,
   `06_Gold_Test_Framework.md:488`) and it chose wrong at least 5 times — the author's own note in
   `09_ITest_LLM_Serves_P3.ipynb` cell 2 lists P3V2-Q001, Q002, Q004, Q010, Q011 as bad because
   *"'cash flow from operations' but answer is auditor's opinion boilerplate"*, *"'net income' but
   answer discusses valuation allowance sensitivity"*, *"'total revenue' but answer is a
   cross-reference statement"*. **[V]** That is BM25's failure mode, demonstrated on your data.
3. **Financial-domain specifics are already handled structurally, not lexically.** Tickers → CIK,
   years, "Item 1A" → `ITEM_1A` are all resolved by `EntityAdapter` into **metadata filters**
   (§1.3), which is strictly stronger than BM25 term matching for those tokens. BM25 would be
   re-solving a solved problem.
4. **Deployment friction.** A 36 MB index plus build time lands in Lambda cold-start, and a local
   parquet read structurally bypasses the DataLoader pattern that `CLAUDE.md:165` says never to bypass.

**Where dense genuinely *is* weak and lexical genuinely helps** — narrow and worth 0.5 day:

| Weakness | Compensated by EntityAdapter/filters? | Lexical helps? |
|---|---|---|
| Ticker "NVDA", company name | **Yes** — `cik_int` filter | No need |
| Year "2021", ranges, "fiscal 2018-2020" | **Yes** — `report_year` filter + `year_extractor.py:33-36,151-196` range patterns | No need |
| "Item 1A", "Risk Factors" | **Yes** — `SECTION_ITEM_PATTERNS` → `section_name` filter | No need |
| Canonical metric names | **Yes** — `MetricAdapter` → `income_stmt_Revenue` etc. | No need |
| **Abbreviation ≠ expansion** ("EBITDA" vs "Earnings before interest, taxes, depreciation, and amortization") | **No** | **Yes** |
| **Exact numeric values** ("$7.9 billion", "18%") | **No** | **Yes** |
| **Quoted line-item names** ("Other income/(expense), net") | **No** | **Yes** |

The EBITDA case is not hypothetical — it is your team's own top-severity error in
`errors-failure-finsights.pdf`: *"the retrieval model does not match equivalent phrasing (e.g.,
"Earnings before interest, taxes, depreciation, and amortization" ≠ "EBITDA")"*, severity **High**. **[V]**
And two gold questions are exactly this shape: P3V3-Q007 (Tesla Adjusted EBITDA 2022),
P3V3-Q008 (Icahn Adjusted EBITDA 2011), plus P3V3-Q010 (quoted "Other income/(expense), net"). **[V]**

**Recommended narrow form:** when the query contains a quoted phrase, an all-caps abbreviation
(≥3 letters), or a numeric literal, run one `rank_bm25` pass over the *already metadata-filtered*
slice and union up to 5 hits into the candidate pool before reranking. `rank_bm25` is **already an
uncommented dependency and already installed** (`environments/requirements.txt:78`) **[V]**, and only
17.4% of the corpus has `has_numbers=True` (107,066 rows) **[V]** so the numeric slice is small.
This is a **precision gate**, not a second retriever. Note DuckDB is **not** installed and is absent
from every requirements file despite prose claims — so `rank_bm25` over Polars is the lower-friction
path, not DuckDB FTS. **[V]**

### 4.2 (b) Hybrid fusion

**Verdict: SKIP. And if you ever do add BM25, use RRF — never score normalisation.**

| | |
|---|---|
| Expected quality gain | **~0 today** |
| Added cost / latency | 0 / ~0 |
| Effort | 1 day to build, indefinite to tune |
| Variant interaction | Would sit on top of the variant fan-out; adds a second tuning surface |

Three reasons:

1. **There is no second list.** Fusion needs two rankings from different scoring functions. You have
   five calls from **one** encoder against **one** index — `_deduplicate_hits` already merges them by
   taking min-distance and aggregating provenance (`s3_retriever.py:494-502`). RRF over five
   same-space lists is a no-op dressed as sophistication.
2. **Your existing merge is already smarter than naive fusion**, and for a documented reason. The
   author's note in `08_RAGArch_DesignNotes.ipynb` cell 19 is correct: *"Distances are NOT comparable
   across different search spaces! ... Don't do minmax normalization or even scale normalization"* **[V]**.
   The 70/30 stratified quota in `_proportional_topk` sidesteps exactly that problem. Replacing it
   with min-max normalisation would be a **regression**. Keep it.
3. **The fusion you actually need is a quota, not a rank formula.** §2.7 (Netflix 0 blocks) and
   §2.3 (12 of 15 hits from one year) are both *allocation* failures. The fix is per-entity and
   per-year budgets in `_proportional_topk` — one call per company for multi-company queries, and
   a per-year floor for multi-year queries. Same code region, ~1 day, +$0.0005/query for the extra
   QueryVectors calls, and it fixes a 100%-deterministic failure. `S3Vect_QueryCost.md:117` even
   pre-blesses this: *"If you need more candidates for reranking, prefer a second call over bumping
   K beyond 30."* **[V]**

**If** you later add BM25: RRF (rank-based) is the right choice precisely because it never compares
raw scores across spaces — which is the objection the author already raised. Do not min-max.

### 4.3 (c) Cross-encoder reranking — Cohere Rerank 3.5

**Verdict: DO IT. 4th in priority. Use Bedrock, not the Cohere key. Pair it with context trimming.**

| | |
|---|---|
| Expected quality gain | **Highest of the three options.** Directly attacks §2.1 (boilerplate), §2.4 (flat scores), §2.5 (Hit@1 = 0%) |
| Added cost / query | **+$0.002** gross; **$0 to −$0.005 net** if you trim context (see below) |
| Added latency | **~0.5–2s** [I]; +2–7% on P50 27.9s |
| Effort | **~1 dev-day** |
| Variant interaction | **Strongly complementary — and it de-risks the variants** |

**Verified operational facts** (all four sources listed in §0):

| Fact | Value |
|---|---|
| API | boto3 `bedrock-agent-runtime`, `Rerank` operation (`POST /rerank`) |
| Model ID | `cohere.rerank-v3-5:0` |
| Regions | ap-northeast-1, ca-central-1, eu-central-1, **us-east-1**, us-west-2 |
| Price | **$2.00 per 1,000 queries** = $0.002/query |
| Billing unit | 1 query = up to **100 document chunks**; >100 counts as multiple |
| Chunk split | documents >500 tokens are split and each chunk counts separately |
| Max sources | **1,000** per request |
| Request shape | `queries[].textQuery.text`, `sources[].inlineDocumentSource.textDocument.text`, `rerankingConfiguration.bedrockRerankingConfiguration.{modelConfiguration.modelArn, numberOfResults}` |
| Response | `results[].{index, relevanceScore, document}` |
| Cohere-direct alternative | rerank-v3.5 listed at $0.001/search on OpenRouter (<https://openrouter.ai/cohere/rerank-v3.5> — third-party); trial 10 req/min, production 1,000 req/min (<https://docs.cohere.com/docs/rate-limits>) |

Your average sentence is **201 characters ≈ 50 tokens** **[V]** — far under the 500-token split
boundary. So **your entire 30–90 candidate pool is 1 search unit = $0.002.** Note also that
Amazon Rerank 1.0 (`amazon.rerank-v1:0`) is **not available in us-east-1** — Cohere Rerank 3.5 is
the only option in your region. **[V]**

Also newer: `rerank-v4.0-pro` and `rerank-v4.0-fast` exist with **32k** context vs v3.5's 4k
(<https://docs.cohere.com/docs/models>) **[V]**. Bedrock's supported-models table lists **only
Rerank 3.5** **[V]**, so v3.5-via-Bedrock is the right call. 4k context is irrelevant at 50 tokens/sentence.

**Why reranking, specifically, and not the other two:**

- §2.4: a 0.063-wide similarity band means **the ordering you currently pass to `_proportional_topk`
  is close to arbitrary**. A cross-encoder produces a genuinely discriminative score.
- §2.5: Hit@1 = 0.0% is a *ranking* failure, not a recall failure. Filtered Hit@5 is 66.7–80% —
  the right sentence is often **in** the pool and not at the top. That is the textbook reranker case.
- §2.1: a cross-encoder scoring `(query, "FORWARD-LOOKING STATEMENTS...")` will rank generic
  boilerplate below query-specific text. Cosine does not.
- It restores the ranking signal that `ContextAssembler` currently discards (§1.5). Populate
  `final_score`, then trim to the top N.

**The cost argument — this is why it does not violate your cost rule.**

Today: 30 hits → ±3 windows → ~100 sentences → ~21,000 chars ≈ **5,300 input tokens** of RAG block **[V]**.
With reranking: rerank the ~90 pre-cap candidates, keep the top **10–12**, expand those.
Estimated context reduction **~50–60%** [I], so ~2,500–3,000 fewer input tokens.

| Model | Input rate | Token saving | LLM saving | Rerank cost | **Net** |
|---|---|---|---|---|---|
| Haiku 4.5 | $1/1M (`ml_config.yaml` cost block) | ~2,500 | −$0.0025 | +$0.002 | **≈ −$0.0005 (break-even)** |
| Sonnet 4.5 | ~$3/1M | ~2,500 | −$0.0075 | +$0.002 | **≈ −$0.0055 (cheaper)** |

[I] arithmetic on [V] rates and [V] measured token counts. So: **fewer, better sentences.**
This is the one improvement here that plausibly *reduces* both cost and latency while raising quality.
`ml_config.yaml:365` already declares `max_context_blocks: 10` — a knob that is currently unused
(`context_assembler.py:52` "No topK limiting"). Reranking is what would finally make it mean something.

**Interaction with the variant pipeline — keep the variants, and reranking makes them safer.**
The variants' job is *recall* (cast a wider net); the reranker's job is *precision* (sort the net).
They are complementary, not redundant. Right now the variants are a **liability without a reranker**:
they add up to 45 extra candidates into a pool whose ordering is undiscriminative (§2.4), then the
70/30 quota picks 30 of them semi-arbitrarily. With a reranker, extra recall is free upside.

**Do NOT fine-tune your own cross-encoder.** `06_Gold_Test_Framework.md:1098-1109` proposes DeBERTa-Large
on "31 questions × 30 candidates = 930 training pairs" and then admits *"930 pairs is marginal for
fine-tuning. Need to expand P3 suite to 100+ questions"* **[V]**. It is right. Also: `sentence-transformers`,
`scikit-learn`, and torch are **not installed** in `finsight-venv` **[V]** — a local cross-encoder means
a ~200MB+ install, GPU/CPU inference management, and a Lambda deployment problem. The Bedrock managed
API is a boto3 call. Zero new dependencies.

---

## 5. Ranked, sized recommendations

| # | Action | Effort | Cost/query | Fixes | Anchor |
|---|---|---|---|---|---|
| ~~**1**~~ | ~~**Fix `input_type` → `search_query` for the query encoder**~~ **DONE 2026-07-29** | 15 min | $0 | Mis-specified encoder invalidated every measurement | `embedding.spec` in `ml_config.yaml`; `ml_config_loader.py` `query_input_type`; `query_embedder_v2.py from_ml_config`. See `EMBEDDING_INPUT_TYPE_ASYMMETRY.md` |
| **2** | **Global filter respects extracted years** (relax around, don't replace) | **1 h** | **$0** | §2.6, §3.2 — unblocks 39% of gold suite; 23.8% of corpus | `metadata_filters.py:176` |
| **3** | **Text-level dedup + provenance-of-years** | **2 h** | **$0** (saves LLM tokens) | §2.1 — reclaims ~23% of context | `sentence_expander.py:517` |
| **4** | **Retrieval telemetry + `recall@k` harness on `evidence_sentence_ids`** | **1–1.5 d** | **$0** | §2.8, §2.9 — the prerequisite for every claim below | `query_logger.py:88`; `models.py:86` |
| **5** | **Cohere Rerank 3.5 via Bedrock + trim to top 10–12 *before* expansion** (`ContextAssembler` unchanged) | **1 d** | **+$0.002 gross, ~$0 net** | §2.1, §2.4, §2.5 | fill `rag_pipeline/reranker.py`; `models.py:202` |
| **6** | **Per-entity / per-year retrieval quotas** (one call per company on multi-company queries) | **1 d** | **+$0.0005** | §2.7 (NFLX = 0), §2.3 (12/15 hits one year) | `s3_retriever.py:524` |
| **7** | **Comment out `exclude_sections` and annotate why. Do NOT enforce it.** Separately, make `section_name` a soft boost not a hard AND | 10 min / 0.5 d | $0 | §2.2 — enforcing it would delete most of Exxon/Oracle/NVIDIA financials | `ml_config.yaml:222`; `metadata_filters.py:120` |
| **8** | Narrow lexical gate (quoted phrases / ALLCAPS abbreviations / numerics only) | 0.5 d | $0 | EBITDA-class synonym misses | `rank_bm25` already installed |
| **9** | Fix `gold_qs_constant.py:33-35` missing comma (two questions fused, one silently lost) | 5 min | $0 | Test-harness correctness | `constants/gold_qs_constant.py:33` |

**Items 1–4 are one weekend, cost $0, and are the single highest-value block.** Do them together.
Items 5–6 are the following weekend.

### The "don't do this" list

| Skip | Why |
|---|---|
| **BM25 as a co-equal retrieval path** | Amplifies your dominant failure mode (44.9% duplicate text, boilerplate at 0.95+ cosine). Your own regex-based gold curation is the counter-experiment. §4.1 |
| **RRF / any rank-fusion layer** | No second scoring function exists. The existing 70/30 stratified quota is *better* than naive fusion and was built to avoid a real problem the author correctly identified. §4.2 |
| **Min-max or z-score normalisation of distances** | `08_RAGArch_DesignNotes.ipynb` cell 19 already establishes distances aren't comparable across search spaces. Would be a regression. |
| **Fine-tuning DeBERTa-Large on the P3 gold set** | 930 pairs; the doc that proposes it admits it's insufficient. Plus torch/sentence-transformers aren't installed and Lambda deployment gets ugly. |
| **Killing the variant pipeline to save $0.0001** | It's 0.4% of per-query cost. It becomes *valuable* once a reranker can sort the extra recall. Revisit only if recall@k shows variants contribute zero unique gold hits. |
| **Raising topK above 30** | Hard service cap (`S3Vect_QueryCost.md:13,117`). Use a second call. |
| **Any managed vector DB / Pinecone / Weaviate** | Out of scope by design, and nothing in this study argues for it. S3 Vectors' only real limitation here (no native sparse) is addressable locally. |
| **Trusting `06_Gold_Test_Framework.md` numbers** | Diverge from the notebooks by up to 60pp and cite artifacts that don't exist. §2.5 |

---

## 6. Where I disagree with the current design

1. **`ContextAssembler` — LARGELY RETRACTED.** I said the assembler "throws away the relevance
   signal" and framed that as a design flaw. **On the LLM-facing question, that was wrong.**

   The counter-argument is correct: **selection is already the signal.** Picking ~30 sentences out of
   614,787 *is* the assignment of importance. Adding an intra-window "this one was the core hit"
   marker on top would be redundant at best and harmful at worst — window neighbours exist precisely
   to supply the surrounding context, and flagging the centre invites the LLM to over-weight one
   sentence and discount the ±3 that give it meaning. It would also add tokens and a new formatting
   surface for zero demonstrated gain. **Do not add a core-hit marker to the context. I withdraw
   that suggestion.** The assembler's job — sort, group, cite, emit clean prose — is well scoped and
   well executed, and its `:46` "no scores, clean provenance only" is a defensible decision, not an
   oversight.

   **What survives is a different point at a different layer.** I conflated two things:

   | | Question | Verdict |
   |---|---|---|
   | (a) Should the **LLM** see a core-hit / score marker? | annotate *within* assembly | **No. Retracted.** |
   | (b) Should the **pipeline** use `parent_hit_distance` to choose *which* windows to include? | select *before* assembly | **Yes — and this is the real gap.** |

   (b) is not an assembler concern at all. Today the *only* selection is `_proportional_topk`'s
   70/30 quota over a similarity band measured at **0.674–0.737** (§2.4) — i.e. selection on a
   signal with almost no ordering information, after which everything retrieved is expanded and
   assembled. `parent_hit_distance` and `is_core_hit` are computed and populated
   (`models.py:301-302`) but read nowhere outside `sentence_expander.py` **[V]** — and
   `01_pipeline_contract.py:145` anticipated using them (*"Optional: Select top K sentences
   (by parent_hit_distance)"*), while `ml_config.yaml:365`'s `max_context_blocks: 10` is dead
   because nothing ranks.

   So this is not a flaw in `ContextAssembler`. **It is the empty `reranker.py`.** The correct shape
   is: rerank 90 candidates → keep top 10–12 → expand *those* to ±3 windows → hand to
   `ContextAssembler` unchanged, chronological, unmarked. The assembler needs **no modification** for
   recommendation #5; it just receives a better, smaller input. That is also what makes #5
   cost-neutral.

2. **`build_global_filters` hardcoding 2015** (`metadata_filters.py:176`) is defensible on a
   2016–2020 corpus and indefensible on a 2006–2025 one. The revival changed the premise; the code
   didn't follow. §3.2

3. **The variant prompt is self-defeating.** *"Keep the same companies, years, and sections
   mentioned"* (`ml_config.yaml:347`) constrains variants to the base query's neighbourhood, so they
   add little dense diversity — while all three inherit the base filter and die together when it
   returns empty (§2.3). If you keep variants, let at least one *drop* the section constraint.

4. **The "don't re-upload, it costs too much" premise was wrong by ~2 orders of magnitude** — see
   §10. Holding all 614,787 vectors costs **$0.15/month**; the one-time PutVectors bill is **$0.50**.
   The 2015 hardcode in `metadata_filters.py:176` was defending a fifty-cent charge.

5. **`min_similarity: 0.3` is dead code with a comment admitting it** (`ml_config.yaml:384-388`),
   confirmed by the measured 0.674–0.737 band. It creates false confidence in a quality gate that
   rejects nothing. Either remove it or replace it with a rerank-score threshold.

5. **The "~$0.017/query" headline is optimistic.** Measured medians: Haiku **$0.00896**,
   Sonnet **$0.02697**, and `PIPELINE_LATENCY_ANALYSIS.md:39` records a $0.024 average. 14 of 23
   exports ran on Sonnet 4.5, not the Haiku 4.5 that `CLAUDE.md` names as the serving model. Worth
   reconciling — it changes the reranker's cost-neutrality arithmetic in reranking's *favour*.

6. **Two contradictory S3 Vectors cost models coexist in the repo** — per-comparison
   (`S3Vect_QueryCost.md:11,23`) vs per-query (`S3Vect_QueryCost.md:74`, `IMPLEMENTATION_GUIDE.md:74`),
   differing ~40x. Both are <2% of total so it doesn't change any decision here, but pick one.

7. **Minor, pre-existing:** the UI reads `metadata.context.sentence_count`
   (`serving/frontend/metrics.py:103`) which is not a declared field on `ContextMetadata`
   (`serving/backend/models.py:79-86`), so it always renders empty.

---

## 7. Measurement plan

### 7.1 The good news: retrieval ground truth already exists

All six gold files share a 20-field schema, and **`evidence_sentence_ids` is populated in 31/31
questions** of `p3_gold_test_suite_31q.json` **[V]**. The IDs are **exact corpus primary keys** —
`0000104169_10-K_2018_section_7_142` — the same `sentenceID` the S3 Vectors index stores as metadata.

**So recall@k, MRR, and nDCG@k are computable today with zero new labelling.** Nobody has ever
computed them: `grep` finds `evidence_sentence_ids` used only to print `"Evidence: N sentences"`.
`utilities/evaluation_metrics.py` (197 lines) exposes only `rouge_l`, `bertscore_f1`, `cosine_sim`,
`bleurt` — **no retrieval metric function exists**. **[V]**

### 7.2 What to instrument (part of recommendation #4)

Populate `retrieval_stats` (already in the contract, `serving/backend/models.py:86`) and log it:

```
n_filtered_hits, n_global_hits, n_union_hits, n_after_topk, n_sentences_final,
distance_min/median/max, per-source counts, per-(cik,year) counts,
variant_queries[], n_hits_per_variant[], hit_sentence_ids[]
```

`n_hits_per_variant` alone tells you whether the variant pipeline earns its keep.
`per-(cik,year) counts` makes §2.7 and §2.3 visible instead of silent.

### 7.3 Metrics, and which are defensible

| Metric | Computable now? | Use it? |
|---|---|---|
| **recall@k** (k = 15, 30, and post-expansion) | **Yes** | **Primary.** Directly measures "did the gold sentence enter the pool" |
| **Gold-year coverage** — fraction of asked years present in context | **Yes** (I did it in §2.6) | **Primary for #2.** Cheap, unambiguous, no labels needed |
| **Gold-company coverage** — fraction of asked companies with ≥1 block | **Yes** (I did it in §2.7) | **Primary for #6** |
| **Context redundancy rate** — duplicate-text share | **Yes** (I did it in §2.1) | **Primary for #3.** Target: 22.7% → <5% |
| **MRR / nDCG@k** | Yes, but see caveats | **Secondary.** With 24/31 single-evidence questions, nDCG's graded-relevance advantage is wasted; MRR is the more honest ranking metric here |
| **Precision@10 after rerank** | Yes | **Primary for #5** |
| Answer-level BERTScore / BLEURT | Yes | **Tertiary.** Slow (~7.2s/pair, `evaluation_metrics.py:57-68`) and weakly coupled to retrieval |
| Numeric accuracy w/ `tolerance` | **No** | `answer_numeric`/`tolerance` are null in every suite actually used |
| Span-level F1 | **No** | `evidence_spans` empty in 5 of 6 files |

**Suggested protocol:** run all 31 questions before and after each change, report recall@30 and the
four coverage/redundancy metrics as a table, and use **McNemar's test** on the paired binary
recall outcomes rather than eyeballing means.

### 7.4 Honest assessment: the gold sets are weaker than "imperfect"

You called them imperfect. They are worse than that in three specific, measurable ways:

1. **Circularity — the fatal one.** P3.v2 evidence was selected by the *same class of retrieval*
   being evaluated (regex keyword match: `Net Income: (?i)\bnet (income|loss)\b`,
   `06_Gold_Test_Framework.md:488`). The author's own note flags 5 questions as bad
   (*"'total revenue' but answer is a cross-reference statement"*) and 12 more as "too broad" —
   **17 of 31**. **[V]** A *better* retriever will score *worse* against those labels. You cannot
   use the full 31 to measure improvement.

2. **Year-blindness — measured.** 10 of 31 questions (32%) form 5 pairs whose gold answers share
   their first 100 characters: (Q007,Q008) Genworth 2019/2018, (Q010,Q011) MBIA 2013/2016,
   (Q013,Q014) Walmart 2011/2021, (Q015,Q016) Walmart 2021/2022, (Q017,Q018) Meta 2023/2024. **[V]**
   The gold labels cannot distinguish a retriever that gets the year right from one that gets it
   wrong — which is precisely the axis recommendation #2 changes. **These 10 questions cannot
   validate the fix they most concern.**

3. **Statistical power.** 24 of 31 have exactly **1** evidence sentence, so per-question recall is
   binary. With n=31 and typically <8 discordant pairs, only a swing of roughly **≥6–7 questions** is
   distinguishable from noise. A "24/31 → 27/31" improvement is **not** a finding. **[I]** on **[V]** counts.

**What to strengthen, in priority order — this is the real bottleneck:**

| Action | Effort | Why |
|---|---|---|
| **Carve out a trusted subset**: the 10 P3.v3 questions (hand-written, 1–4 evidence, `gpt5_agent`/curated, genuinely analytical answers) + the ~14 P3.v2 questions not on the author's bad/too-broad list | **2 h** | Gives you ~24 usable questions *today*, and stops the circularity from poisoning the headline number |
| **Re-label evidence for the 5 known-bad questions by hand** (Q001, Q002, Q004, Q010, Q011) | **2 h** | Removes the worst circularity |
| **Add 2–3 evidence sentences per question** where only 1 exists | **1 d** | Turns binary recall into graded — makes nDCG meaningful and materially raises power |
| **Grow to ~80–100 questions**, weighted toward pre-2015 years, multi-company, and abbreviation/numeric queries | **2–3 d** | The only real fix for power. Also what `06_Gold_Test_Framework.md:1109` says is needed |
| **Run `p3_gold_qtest_31q_ffhall.json` at least once** | **1 h** | It is referenced by **zero** files and has **no recorded results anywhere** **[V]**. It contains the only high-multiplicity questions in the repo (10 and **46** evidence IDs) — with topK=30, the 46-ID question caps recall@30 at ≤65% even with a perfect retriever, making it a genuinely useful stress probe. But note its V2 half was built by *rewriting the question to fit the lexically-chosen evidence*, which flattened all 21 to `difficulty: easy` — do not use it as your primary suite |

---

## 8. Sequencing — what is blocked on Stage 3

**The S3 Vectors index `finrag-sentence-fact-embed-1024d` exists and is EMPTY. Zero vectors.** **[V]**
(`CLAUDE.md:95-97`; `EMBEDDINGS_VECTORS_REVIVAL_PLAN.md:34,51-79`.)
Embedding regeneration is at 433,799 / 614,647 = 70.58%; Bin 3 (2022–2025, ~180,848 left, ~$0.86) in
progress. Stage 3 = (E) build the join parquet via `platform_core/s3vectors_table_preparation.py`,
then (F) bulk insert via `platform_core/s3vectors_bulk_insertion.py`. Neither has started. **[V]**
Known blocker before F: `s3vectors_bulk_insertion.py` ~L198-199 hardcodes bucket/index names
despite a comment claiming MLConfig (`EMBEDDINGS_VECTORS_REVIVAL_PLAN.md:110-114`). **[V]**

| Blocked on Stage 3 | Doable **now** |
|---|---|
| Every recall@k / MRR / nDCG number | **#1** `input_type` fix (config + 1 line) |
| Gold-year and gold-company coverage measurement | **#2** global-filter fix + unit tests on `build_global_filters` with synthetic entities |
| Redundancy-rate before/after | **#3** text dedup — testable on synthetic `SentenceRecord` lists |
| Any reranker A/B | **#4** harness code + `retrieval_stats` plumbing; validate the ID-join against the Stage 1 parquet offline |
| Any BM25 comparison | **#7** `exclude_sections`, **#9** comma bug |
| Cost-neutrality validation for #5 | Gold-suite triage (§7.4) — pure JSON work |

**So: recommendations #1, #2, #3, #7, #9 can all be written and unit-tested today.** Only their
*measurement* waits on Stage 3. Recommendation #4's harness code can also be written now — build the
`evidence_sentence_ids` → corpus join against `finrag_fact_sentences.parquet` (614,787 rows, 36 MB,
loads fine with `scan_parquet`) so that the moment the index is populated you can run the baseline.

**One sequencing warning:** take the baseline **after** #1 and #2 and **before** #5.
If you measure the baseline on the current mis-specified query encoder and the 2015-floored global
filter, then apply everything at once, you will attribute the whole gain to the reranker and learn
nothing about which change mattered.

---

## 9. What I could not verify

| Item | Status |
|---|---|
| **Actual retrieval quality, at all** | Index is empty. Everything in §2 is from code, from committed notebook outputs, and from 25 context / 23 response exports generated against the **old** 2016–2020 index. |
| **Magnitude of the `input_type` fix** | Cohere documents the correct usage and the live path violates it **[V]**; the docs do not quantify the penalty for using `search_document` on queries, and I ran no embedding calls. Must be A/B'd. |
| **The ~50–60% context reduction from reranking** | [I] estimate from measured token counts. Depends on your chosen top-N. |
| **Reranker latency (~0.5–2s)** | [I]. Not published by AWS for this model; I made no inference calls. |
| **Cohere-direct rerank per-search price** | Conflicting third-party figures ($0.001 vs $0.002/search). The **Bedrock** price is authoritative and verified: **$2.00/1,000 queries**. Cohere's own pricing page shows only Model Vault instance pricing ($5.00/hr), not serverless per-search. |
| **Whether Bin 3 is running now** | `data_cache/embeddings/` is off-limits (live paid job). Progress log says 70.58%; a sibling agent observed shard files newer than the log. Re-verify before touching. |
| **S3 Vectors metadata size limits** | Not documented in any repo file; only the 500-vector / 20 MiB `put_vectors` batch cap. Relevant only if you ever want to store sentence text as metadata (which would let you rerank without a local parquet read). |
| **The "4,674 companies" figure** | Appears in `.claude/CLAUDE.md` and `06_Gold_Test_Framework.md:23`, but the embedded corpus is **25 companies / 614,787 sentences** **[V]**. 4,674 is the upstream ETL universe. Several doc claims about corpus-scale noise are therefore overstated. |

---

## 10. S3 Vectors economics — full upload of the whole corpus

**Question:** if I PutVectors everything — 25 companies, 2006–2025 — what does it cost to hold and to
run, including cold data I never query?

**Answer: $0.50 one-time, $0.15/month to hold, ~$0.00004 per user query.**
The earlier "not worth the PutVectors cost" decision was wrong by roughly two orders of magnitude.

### 10.1 Verified pricing (us-east-1)

Source: <https://aws.amazon.com/s3/pricing/> · limits: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html> **[V]**

| Component | Rate | Metering |
|---|---|---|
| Storage | **$0.06 / GB-month** | logical GB = vector data + metadata + key |
| PutVectors | **$0.20 / GB uploaded** | logical GB; **min 128 KB per PUT request** |
| Query request | **$2.50 / million queries** | per `QueryVectors` call |
| Query data processed | **$0.004/TB** first 100K vectors · **$0.002/TB** 100K–10M · **$0.0004/TB** 10M+ | (vectors in index) × (vector + **filterable** metadata + key). Non-filterable metadata is **not** scanned |
| Query data returned | **$0.01 / GB**, first **512 KB per query free** | key + filterable + non-filterable per result |
| Fixed monthly fee | **none** — no per-bucket or per-index charge | |

Verified against AWS's own worked example (10M vectors → $11.38/mo total), which reconciles to
within rounding of my arithmetic below. **[V]**

### 10.2 Your actual per-vector footprint (measured, not assumed)

Metadata schema from `platform_core/s3vectors_table_preparation.py:280-300` **[V]**:
filterable = `cik_int, report_year, section_name, sic, sentence_pos`;
non-filterable = `embedding_id, section_sentence_count`; plus `sentenceID`, `sentenceID_numsurrogate`.
Measured `sentenceID` length = **34 chars avg** (max 36). **[V]**

| | Bytes |
|---|---|
| Vector data (1024 × 4 B) | 4,096 |
| Metadata JSON (all fields, keys included) | ~270 |
| Key (`sentenceID`) | ~34 |
| **Total per vector** | **~4,399 B = 4.30 KB** |

`614,787 × 4,399 B` = **2.519 GB logical**. Vector data is 93% of it; metadata+key only 7%.

### 10.3 The bill

| Line item | Amount |
|---|---|
| **One-time PutVectors** (2.519 GB × $0.20) | **$0.50** |
| **Storage** (2.519 GB × $0.06) | **$0.15 / month** = **$1.81 / year** |
| **Cold data, never queried, container never spun** | **$0.15 / month. Nothing else.** |
| Per `QueryVectors` call: request fee | $0.0000025 |
| Per call: data processed (100K @ $0.004/TB + 514,787 @ $0.002/TB, 4.12 KB/vector scanned) | ~$0.0000060 |
| Per call: data returned (30 × ~304 B ≈ 9 KB, under the 512 KB free tier) | **$0** |
| **Per call total** | **~$0.0000085** |
| **Per user query (5 calls: filtered + global + 3 variants)** | **~$0.00004** |
| 1,000 user queries/month | ~$0.04 |
| 10,000 user queries/month | ~$0.43 |

So S3 Vectors is **~0.17% of a $0.024 LLM call** — an order of magnitude *below* even the repo's
already-dismissive "<2% of total" (`S3Vect_QueryCost.md:249`). **[I] arithmetic on [V] rates.**

### 10.4 Ingress / egress

| Path | Cost |
|---|---|
| Data **in** to S3 / S3 Vectors from anywhere | **free** |
| S3 → any AWS service in the **same region** | **free** |
| S3 → internet | first **100 GB/month free** (aggregated across all AWS services), then standard regional rates |

Your query responses are ~9 KB per call, ~45 KB per user query. Reaching the 100 GB free-tier
egress ceiling would take roughly **2.2 million user queries per month**. **[I]** Sevalla was
investigated as a serving option but never deployed; production serving ran on ECS Fargate,
inside AWS, so this egress path is same-region and moot.
**There is no egress story here.**

### 10.5 What the upload job looks like operationally

Limits: **500 vectors per PutVectors call**, 20 MiB payload, **2,500 vectors/s** and 1,000 PUT
req/s per index; 2 billion vectors per index; 40 KB metadata cap (you use ~270 B); 2 KB filterable
cap (you use ~88 B); 10 non-filterable keys max (you use 2). **[V]** Everything is far inside limits.

- `614,787 / 500` = **1,230 PutVectors calls**; each ~2.15 MB, comfortably over the 128 KB minimum
  so **no minimum-size penalty applies**.
- Floor from the 2,500 vectors/s quota: **~246 seconds**. Realistically **20–60 min** with Python
  and retry overhead. **[I]**

### 10.6 The conclusion that matters

The expensive thing in this pipeline is **embedding generation** (~$0.12/1M tokens, whole corpus in
the ~$4–5 range) — not storage and not PutVectors. **Cost is therefore not a reason to keep a
truncated year range, a 2015 filter floor, or a partial index.** Upload all 614,787 vectors, delete
the 2015 hardcode (§3.2), and stop optimising a fifty-cent line item. If you later want to store
sentence text as **non-filterable** metadata to skip the local parquet read at rerank time, note
that non-filterable metadata is free to scan at query time and only costs storage — at 201 chars
average that would add ~0.12 GB, i.e. **+$0.007/month**. **[I]**

---

## Appendix: file:line index

| Concern | Location |
|---|---|
| Composition root | `rag_modules_src/synthesis_pipeline/supply_lines.py:64` |
| SL1 (KPI) | `.../supply_lines.py:135` |
| SL2 (RAG) | `.../supply_lines.py:171` |
| SL1+SL2 merge | `.../supply_lines.py:249` |
| Retrieval strategy | `rag_modules_src/rag_pipeline/s3_retriever.py:157` |
| Dedup by identity | `.../s3_retriever.py:458` |
| 70/30 quota | `.../s3_retriever.py:524` |
| Similarity threshold | `.../s3_retriever.py:412` |
| **Global-year bug** | `rag_modules_src/rag_pipeline/metadata_filters.py:176` |
| Filtered filters | `.../metadata_filters.py:69` |
| **Query `input_type` bug** | `rag_modules_src/utilities/query_embedder_v2.py:66,226` + `.aws_config/ml_config.yaml:214` |
| Correct-but-dead config | `.aws_config/ml_config.yaml:266-272` |
| **Text dedup gap** | `rag_modules_src/rag_pipeline/sentence_expander.py:517` |
| Window expansion | `.../sentence_expander.py:211,334-340` |
| Rank discarded | `rag_modules_src/rag_pipeline/context_assembler.py:46,52,242` |
| `final_score` slot | `rag_modules_src/rag_pipeline/models.py:201-202` |
| Empty reranker | `rag_modules_src/rag_pipeline/reranker.py` (0 bytes) |
| Variant orchestration | `rag_modules_src/rag_pipeline/variant_pipeline.py:120` |
| Variant LLM call | `rag_modules_src/rag_pipeline/variant_generator.py:59,94` |
| Section canonicalisation | `rag_modules_src/entity_adapter/section_extractor.py:39,57,92` |
| Year/range extraction | `rag_modules_src/entity_adapter/year_extractor.py:33,151-196` |
| No retrieval telemetry | `rag_modules_src/synthesis_pipeline/query_logger.py:88-176` |
| `retrieval_stats` (declared, unused) | `serving/backend/models.py:86` |
| `exclude_sections` (declared, unenforced) | `loaders/ml_config_loader.py:293` |
| Gold constant comma bug | `rag_modules_src/constants/gold_qs_constant.py:33-35` |
| Retrieval metrics (recorded) | `validation_notebooks/05_GoldP1P2_TestSuite.ipynb` cells 9, 12 |
| Flat score distribution | `validation_notebooks/08_RAGArch_DesignNotes.ipynb` cell 17 |
| Score-comparability argument | `.../08_RAGArch_DesignNotes.ipynb` cell 19 |
| BM25 scoping note | `.../08_RAGArch_DesignNotes.ipynb` cell 3 |
| Zero-hit filtered + variants | `rag_modules_src/02_LLMEval_Notebooks/09_ITest_LLM_Serves_P3.ipynb` cell 5 |
| Bad-question list | `.../09_ITest_LLM_Serves_P3.ipynb` cell 2 |
| n=6 answer scoring | `.../11_ITest_AnsScoring.ipynb` cells 8-9 |
| Boilerplate diagnosis | `validation_notebooks/06_Gold_Test_Framework.md:159-173` |
| Cross-encoder proposal | `.../06_Gold_Test_Framework.md:1098-1109` |
| Gold sets | `data_cache/qa_manual_exports/goldp3_analysis/*.json` |
| Corpus (text, 36 MB) | `data_cache/stage1_facts/finrag_fact_sentences.parquet` |
