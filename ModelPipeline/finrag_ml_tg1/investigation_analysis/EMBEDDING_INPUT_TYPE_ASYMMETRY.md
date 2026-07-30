# Asymmetric Dual Encoders and the `input_type` Parameter

**Written:** 2026-07-29 · **Status: IMPLEMENTED 2026-07-29** (Option B, additive variant — see §2.4).
Part 1 is the theory; Part 2 records the fix as shipped.

> **SHIPPED.** `embedding.spec.input_type_document` / `input_type_query` added to
> `ml_config.yaml`; `MLConfig.document_input_type` / `query_input_type` /
> `assert_input_types_differ()` added; `EmbeddingRuntimeConfig.from_ml_config` now reads the query
> value. Verified: the live Bedrock request body for a user query carries
> `input_type: search_query`, and the corpus path still resolves `search_document`.
> A/B against the pre-edit YAML: **48 path/property resolutions, zero differences.**
**Why it exists:** the live query path embeds user questions with `input_type="search_document"`.
That is the corpus setting. Queries must use `search_query`. This doc explains the theory well
enough to judge the claim, then specifies exactly where and how to fix it.

**Companion docs:** `RETRIEVAL_IMPROVEMENT_STUDY.md` §3.1 (evidence), `EMBEDDING_TRANSPORT_DESIGN.md`
§5 (the config restructure this fix should ride along with).

---

## Part 1 — The theory

### 1.1 The retrieval problem is not a similarity problem

The instinct "use the same model on both sides, so use the same settings on both sides" is right
about the model and wrong about the settings. To see why, look at what you are actually asking for.

```
query:    "What was Exxon's total revenue in 2008?"
answer:   "Total revenues and other income were $477,359 million."
```

These two strings are **not similar**. Almost no shared vocabulary. Opposite grammatical mood —
one interrogative, one declarative. Different length, different register. A naive text-similarity
model would rank this pair *low*.

Meanwhile, here are two strings that **are** highly similar:

```
query:    "What was Exxon's total revenue in 2008?"
distractor: "What does the Corporation report as revenue in its Financial Section?"
```

So "similarity" is the wrong objective. What you want is **relevance**: *does passage P answer
question Q?* Relevance is **asymmetric** — P answers Q, but Q does not answer P. Similarity is
**symmetric** by construction: `sim(a,b) == sim(b,a)`.

That asymmetry is the entire subject of this document.

### 1.2 Symmetric vs asymmetric tasks

| | Symmetric | Asymmetric |
|---|---|---|
| Question asked | "are these two things the same kind of thing?" | "does this thing satisfy that need?" |
| Inputs | same type both sides (passage↔passage) | different types (query→passage) |
| Example tasks | dedup, clustering, near-duplicate detection, STS | search, QA retrieval, RAG |
| Length profile | comparable | short query, long passage |
| `sim(a,b)=sim(b,a)`? | yes, and that's correct | no, and forcing it is a modelling error |

Your task is **asymmetric**. Sentence-level SEC retrieval from natural-language finance questions
is about as asymmetric as retrieval gets: ~10-word interrogatives against 201-character declarative
financial statements.

### 1.3 Bi-encoders, and where the asymmetry lives

A **bi-encoder** (a.k.a. dual encoder) embeds query and document *independently*, then compares
with a cheap operation (cosine / dot product):

```
q ──► E_q ──► u ∈ R^1024  ┐
                          ├── score = cos(u, v)
d ──► E_d ──► v ∈ R^1024  ┘
```

This independence is what makes ANN search possible at all: you precompute every `v` once, build an
index, and at query time you only encode `u`. That is exactly your S3 Vectors architecture.

There are two ways to build the two encoders:

**(a) Two separate towers** — `E_q` and `E_d` are different networks with different weights.
Classic DPR (Karpukhin et al., 2020) does this. Maximum flexibility, 2x the parameters, and the two
towers can drift apart.

**(b) One shared tower, task-tagged input** — `E_q` and `E_d` are *the same weights*, and you tell
the model which role the current input is playing. Cohere v3/v4, E5, BGE, and Instructor all do
variants of this. The role is conveyed by prepending a task instruction or a learned prefix token to
the input text before encoding.

**Cohere's `input_type` is the mechanism for (b).** It is not a model selector. It is the role tag
that the shared encoder conditions on.

Conceptually:

```
input_type="search_query"     ->  E("[QUERY] What was Exxon's total revenue in 2008?")
input_type="search_document"  ->  E("[DOCUMENT] Total revenues and other income were $477,359 million.")
```

Same weights `E`. Different conditioning. Different output subspace.

> The exact tagging implementation is proprietary and undocumented; whether it is a literal text
> prefix, a special token, or a learned task embedding is not published. The *behavioural* contract
> is documented and is what matters here.

This resolves your question directly:

| Requirement | Rule | Reason |
|---|---|---|
| Same **model** | **Mandatory** — both sides `cohere.embed-v4:0` | Different models produce incomparable vector spaces. Cosine across them is noise. |
| Same **dimensions** | **Mandatory** — both sides 1024 | Dimensionality mismatch is a hard error; and v4 silently defaults to 1536. |
| Same **`input_type`** | **Must differ** — `search_query` vs `search_document` | It selects the *role*, not the space. Using one value for both collapses an asymmetric task into a symmetric one. |

The first two are about *which vector space*. The third is about *where in that space* the input
lands. You have the first two right.

### 1.4 The training objective

This is the part that makes the behaviour predictable rather than mysterious.

**The data.** Training uses pairs `(q_i, d_i⁺)` — a query and a passage known to satisfy it.
Sources: search-click logs, QA datasets, title↔body pairs, synthetic LLM-generated queries.

**The loss: InfoNCE / in-batch-negatives contrastive learning.** For a batch of `N` pairs, encode
all queries with the query role and all passages with the document role. For query `i`, the correct
passage is `d_i⁺`; every *other* passage in the batch, `d_j` for `j ≠ i`, is a negative. Then:

```
                    exp( cos(u_i, v_i⁺) / τ )
L_i  =  − log  ───────────────────────────────────────
                 Σ_j∈batch  exp( cos(u_i, v_j) / τ )
```

with `τ` a temperature (typically 0.01–0.05). Summed over the batch, often symmetrised
(query→doc and doc→query) and augmented with **hard negatives**: passages that a cheap retriever
scored highly but that are actually wrong. Hard negatives are where most of the quality comes from.

**What gradient descent is therefore optimising.** Read the loss carefully — the numerator pulls
`u_i` toward `v_i⁺`; the denominator pushes `u_i` away from every other `v_j`. So the objective is:

> maximise `cos(query-role vector, correct-passage-role vector)`
> minimise `cos(query-role vector, incorrect-passage-role vector)`

There is **no term anywhere in this loss that shapes query-role↔query-role geometry**, and none that
shapes document-role↔document-role geometry either, beyond what falls out incidentally. The model is
never rewarded for making a *question* close to a *question*. It is only ever rewarded for making a
question close to its *answer*.

Consequence — and this is the crux:

**The `search_query`→`search_document` direction is the only direction the model was trained on.
Every other combination is off-distribution.**

### 1.5 So what actually happens when you use `search_document` for a query?

You are computing `cos(document-role(question), document-role(passage))`. Both inputs are in the
document manifold, so you have accidentally built a **symmetric passage-similarity** system. It
still returns results — cosine of two 1024-d vectors is always defined — and the results are not
random, because the encoder still understands finance. They are systematically *wrong in a
particular way*:

> It retrieves passages that **resemble the question as a piece of text**, rather than passages that
> **answer** it.

Predicted failure signature:

| The model will favour | Over |
|---|---|
| Text that *mentions* the metric | Text that *states* the value |
| Definitions, glossaries ("ROCE is a performance measure ratio") | Actual figures |
| Table headers, index lines, cross-references | Table contents |
| Questions, prompts, forward-looking hedges | Declarative facts |
| Interrogative or meta-discursive prose | Assertive prose |

Because a question *about* revenue is textually more similar to a *definition* of revenue than to a
number.

There is a second, subtler effect. Off-distribution inputs land in a region of the space the model
was not trained to spread out, so embeddings tend to occupy a **narrower cone** — pairwise cosines
compress toward each other. This is the well-documented anisotropy/hubness problem in dense
retrieval. Symptom: *all* your top-k scores look similar and the ranking loses discriminative power.

Your measured similarity band across 45 candidates is **[0.674, 0.737]** — 0.063 wide, with zero
hits below 0.6 and zero above 0.8, and no threshold from 0.0 to 0.5 rejecting anything
(`validation_notebooks/08_RAGArch_DesignNotes.ipynb` cell 17). That is what score compression looks
like. **[V] measurement, [I] attribution** — I cannot prove the input_type is the cause without the
A/B, but it is the mechanism that predicts precisely this shape.

### 1.6 Why this is a plausible cause of your observed failures

Every one of these is "topically adjacent prose beat the actual answer" — the exact predicted
signature from §1.5. All **[V]**:

| Query | What retrieval returned | Anchor |
|---|---|---|
| Exxon total revenue 2008 | *"Reference is made to the following in the Financial Section of this report"* — a **cross-reference** | `09_ITest_LLM_Serves_P3.ipynb` cell 2 |
| J&J cash flow from operations 2016 | the **auditor's opinion boilerplate** | ibid. |
| Eli Lilly net income 2006 | *"A 5 percent change in the valuation allowance would result in a change in net income of ~$25 million"* — a **sensitivity note** | ibid. |
| Apple EPS 2006 | *"The following table sets forth the computation of basic and diluted earnings per share"* — the **header** | `p3_gold_test_suite_31q.json` P3V2-Q005 |
| (many) | contexts dominated by *"FREQUENTLY USED TERMS"*, ROCE **definitions**, *"FORWARD-LOOKING STATEMENTS"* | 25 files in `rag_modules_src/exports/contexts/` |

Also: open-regime `Self@1` is only **58.3%** (`05_GoldP1P2_TestSuite.ipynb` cell 12) — 40% of the
time an unfiltered search fails to return *the query sentence itself* at rank 1. In a properly
symmetric passage-similarity setup a sentence should be its own nearest neighbour essentially always.
Something is off in the geometry.

These were previously written off as gold-curation faults. Some genuinely are. But **the retriever
surfaced those sentences in the first place**, and a document-role query encoder explains why.

### 1.7 Honest limits of this claim

- Cohere documents the correct usage but **publishes no penalty magnitude** for getting it wrong.
  Any number I gave you would be invented.
- Published ablations for E5/BGE-style prefix conditioning report meaningful but not catastrophic
  degradation when prefixes are wrong. I have **not** verified a v4-specific figure and will not
  quote one.
- v4 may be more robust than v3 here; it is a newer, more instruction-tuned model. Unknown.
- **This is a hypothesis with a strong mechanism and a matching evidence pattern — not a proven
  cause.** It is cheap, safe, and decisive to test, which is the whole argument for doing it first.
- What is **not** in doubt: the current setting contradicts the vendor's documented contract.
  Sources: <https://docs.cohere.com/docs/embeddings> · <https://docs.cohere.com/reference/embed>

---

## Part 2 — The fix

### 2.1 Where the wrong value comes from

```
.aws_config/ml_config.yaml:214
  cohere_embed_v4: { model_id: cohere.embed-v4:0, dimensions: 1024,
                     batch_size: 96, input_type: search_document }
                                     └──────────────┬──────────────┘
                                       correct for the CORPUS
                                                    │
        ┌───────────────────────────────────────────┘
        ▼
utilities/query_embedder_v2.py:66      EmbeddingRuntimeConfig.from_ml_config()
  input_type=model_cfg["input_type"]   <- borrows the DOCUMENT value
        │
        ▼
utilities/query_embedder_v2.py:226     _invoke_bedrock_raw()
  "input_type": self.cfg.input_type    <- sends search_document for a QUERY
```

**One root cause:** a single config field is serving two different roles. `EmbeddingRuntimeConfig`
(`query_embedder_v2.py:36-67`) is a *query-side* object that reads its `input_type` from the
*document-side* model block.

**Corroborating evidence that this was an accident, not a decision:**

| Anchor | Content |
|---|---|
| `ml_config.yaml:266` | `## query_embedding - user submission query uses exactly this config` |
| `ml_config.yaml:272` | `input_type: search_query` — **correct, and read by nothing** (the `rag_orchestrator` block is legacy per `CLAUDE.md`) |
| `utilities/query_embedder.py:44` | V1 signature: `def embed_query(self, query, input_type="search_query")` — **V1 had it right; V2 regressed it** |
| `query_embedder_v2.py:226` | inline comment `# e.g. "search_document" or "search_query"` — the author knew both existed |
| `EMBEDDING_TRANSPORT_DESIGN.md:250` | `input_type: search_document   # corpus ingest; queries use search_query` — **you documented the split yesterday but the field is still singular** |

### 2.2 What does NOT change — read this before touching anything

- **Do not re-embed the corpus.** `search_document` is correct for all 614,787 sentences. That is
  what `platform_core/embedding_generation.py:315` sends via `MLConfig.bedrock_input_type`
  (`ml_config_loader.py:225-228`). Leave it alone.
- **Do not touch the in-flight Bin 3 job.** Unaffected.
- **Do not rebuild or re-upload the S3 Vectors index.** Unaffected.
- **Do not change `ml_config.yaml:214`.** It correctly describes the corpus.
- **Cost of this fix: $0.** No re-embedding, no migration, no backfill. It changes one string on one
  API call per query.

Only the **query-side** call changes.

### 2.3 Blast radius — every call site

`graphify explain QueryEmbedderV2` gives 15 edges; the ones that matter:

| Consumer | Path | Effect |
|---|---|---|
| `run_supply_line_2_rag` | `synthesis_pipeline/supply_lines.py:210` | base query embedding — **primary fix target** |
| `VariantPipeline.generate` | `rag_pipeline/variant_pipeline.py:208` | all 3 variant embeddings — **also needs it** (variants are queries too) |
| `init_rag_components` | `synthesis_pipeline/supply_lines.py:94-96` | builds `EmbeddingRuntimeConfig` — **the single construction point** |
| `create_variant_pipeline` | `rag_pipeline/variant_pipeline.py:325-327` | second construction point (notebooks/tests) |
| `platform_core/embedding_generation.py:315` | corpus ingest | **must keep `search_document` — do not touch** |
| `utilities/query_embedder.py` | legacy V1, unused by live path | already defaults correctly; leave |

Good news: because both live query paths (base + variants) funnel through the same
`QueryEmbedderV2` instance constructed once at `supply_lines.py:96`, **fixing the construction fixes
both.** No orchestrator change, no retriever change, no serving-contract change,
no `ContextAssembler` change.

### 2.4 The fix, sized

Two options. I recommend B.

#### Option A — minimal, 15 minutes

Add a query-side field to the dataclass and default it correctly.

- `EmbeddingRuntimeConfig` (`query_embedder_v2.py:36-43`): add
  `query_input_type: str = "search_query"`.
- `from_ml_config` (`:46-67`): read `embedding.query_input_type` if present, else default to
  `"search_query"`. **Do not fall back to `model_cfg["input_type"]`** — that reintroduces the bug.
- `_invoke_bedrock_raw` (`:226`): send `self.cfg.query_input_type`.
- Optionally rename the existing field to `document_input_type` to kill the ambiguity at the source.

Backward compatible, no YAML change strictly required.

#### Option B — fold it into the config restructure you already designed (recommended)

`EMBEDDING_TRANSPORT_DESIGN.md` §5 is already rewriting exactly this block, and its Step 1 is
"Config restructure only — no code, no run". That is the natural home: you get one config change
instead of two, and the singular-field ambiguity dies permanently.

Change the `spec` block from a single `input_type` to an explicit pair:

```yaml
embedding:
  spec:
    dimensions: 1024
    model_family: cohere_embed_v4

    # ASYMMETRIC ENCODER -- THESE MUST DIFFER. NOT A STYLE CHOICE.
    # Cohere v3/v4 are asymmetric dual encoders: one shared tower, the input
    # tagged by role. Training only ever optimised
    #   cos(search_query(question), search_document(answer)).
    # Using search_document on BOTH sides silently converts retrieval into
    # passage-similarity: it then favours definitions, table headers and
    # cross-references over the actual figures.
    # Corpus was embedded with search_document -- that is CORRECT. Never change it.
    # See EMBEDDING_INPUT_TYPE_ASYMMETRY.md
    input_type_document: search_document   # corpus ingest  (614,787 sentences)
    input_type_query:    search_query      # user queries AND variant queries

    max_texts_per_call: 96
    max_tokens_per_call: 128000
```

Then:
- `MLConfig.bedrock_input_type` (`ml_config_loader.py:225-228`) → resolve to `input_type_document`.
  Keep the old property name so `embedding_generation.py:315` is untouched, or add
  `document_input_type` / `query_input_type` properties and migrate both call sites.
- `EmbeddingRuntimeConfig.from_ml_config` → read `input_type_query`.
- Add a startup assertion: `input_type_document != input_type_query`. Cheap, and it makes the
  regression impossible to reintroduce silently.

**Effort:** ~30–45 min inside the Step 1 restructure you were doing anyway.
Both transports need it — Cohere's native `/v2/embed` takes the same `input_type` values, so this is
transport-independent and belongs in `spec`, not under `bedrock:`.

### 2.5 How to verify — do this before and after

**Offline sanity check (no index needed, ~$0.0001 of embed calls).** The single most convincing test:

1. Take 5–10 gold questions with hand-verified evidence (prefer the P3.v3 subset — hand-written,
   multi-evidence).
2. Embed each question **twice**: once `search_query`, once `search_document`.
3. Embed the known-correct evidence sentence with `search_document`.
4. Compare `cos(query_role(q), doc_role(evidence))` vs `cos(doc_role(q), doc_role(evidence))`.
5. Also embed 3–5 *distractors* per question — a definition, a table header, a forward-looking
   hedge — and check whether the correct/distractor **margin** widens under `search_query`.

The margin matters more than the raw cosine. Raw cosines are not comparable across roles; the
*ordering* is the thing.

**Full check after Stage 3:** run the harness in `RETRIEVAL_IMPROVEMENT_STUDY.md` §7 and report
recall@30 and MRR both ways. Take this baseline **before** adding the reranker, or you will
attribute the reranker's gain to the wrong change.

**Expected direction** (falsifiable — write it down before running): correct-evidence rank improves,
definition/header/cross-reference distractors fall, and the top-k similarity band **widens** from
its current 0.063. If the band does not widen and ranks do not move, the hypothesis is wrong,
you have lost ~30 minutes and $0.0001, and you have eliminated a confound before benchmarking
anything else. That is a good trade at any odds.

### 2.6 One-paragraph summary

Cohere Embed v3/v4 are asymmetric dual encoders — one shared tower, the input tagged by role via
`input_type`. The contrastive objective only ever optimises
`cos(search_query(question), search_document(answer))`; no other role combination is trained.
The live path embeds queries with `search_document` because `EmbeddingRuntimeConfig`
(`query_embedder_v2.py:66`) borrows the corpus value from `ml_config.yaml:214`, which turns
retrieval into passage-similarity and structurally favours definitions, headers and
cross-references over facts — matching the failure pattern across the exports and gold sets. The
corpus embeddings are correct and must not be re-run; only the query-side call changes. Fix it in
the `spec` block as `input_type_document` / `input_type_query` with a startup assertion that they
differ, and A/B it on the gold suite before anything else lands.
