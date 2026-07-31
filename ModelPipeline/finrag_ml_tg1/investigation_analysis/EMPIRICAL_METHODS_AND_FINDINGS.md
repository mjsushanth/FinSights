# Empirical Methods and Findings — a catalogue of what this project actually measured

> **Purpose.** FinSights has run a lot of real experiments. Their results are scattered
> across notebooks, markdown reports and log tables, and the *methods* — which are the more
> reusable part — are mostly implicit. This document collects both in one place: what was
> asked, how it was measured, exactly what came back, and what the measurement could not see.
>
> **Provenance labels are used throughout and they matter:**
>
> | Label | Means |
> | :-- | :-- |
> | **(a) MEASURED** | the output of an actual run |
> | **(b) ILLUSTRATIVE** | an example, docstring, or projection — arithmetic, not observation |
> | **(c) CONFIGURED** | a parameter or threshold, i.e. an input, not a result |
> | **NOT FOUND** | searched for and absent. Distinct from "false". |
>
> Numbers are quoted at the precision the source reports them. `path:line` citations are
> relative to `ModelPipeline/` unless stated.
>
> Companion notes: `study_notes/S02h - Measurement as a Design Practice` (the method layer),
> `study_notes/S02g - Concurrency and Shared State` (the audit), and
> `../../finrag_docker_loc_tg1_aws/SYSTEMS_WALKTHROUGH.md` (the deployment).

---

# PART 1 — Deployment-era measurements (2026-07-31)

All of Part 1 was run in this session against the live account `908877262866` and the local
ARM container. Scripts are preserved in this directory.

## 1.1 Container memory under real load

**Question.** How much memory does the backend actually need, so the Fargate task can be sized?
The documentation said 0.25 vCPU / 512 MiB.

**Why it needed a method.** Peak memory cannot be read cheaply from inside the process, and it
cannot be observed at all without real work driving it. So: an external sampler, real queries,
and a marker file to coordinate start/stop.

**Script.** `measure_container_memory.sh`

```bash
sample() {                                   # $1 = phase label
    while [ -f "$OUT/sampling" ]; do
        docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' \
            | sed "s/^/$1 /" >> "$OUT/stats_raw.log"
    done
}
run_query() {
    touch "$OUT/sampling"; sample "$1" &
    curl -s -X POST localhost:8000/query -d "$(jq -n --arg q "$2" '{question:$q}')" ...
    rm -f "$OUT/sampling"; wait
}
```

Reduced with awk, normalising MiB/GiB and keeping the max per phase.

**Result — (a) MEASURED.**

| | Idle | Simple query | 10-company query |
| :-- | --: | --: | --: |
| Backend | 213 MiB | 1,139 MiB | **1,220 MiB** |
| Frontend | 146 MiB | 146 MiB | 146 MiB |

Queries used: `"What was Apple's total revenue in 2021?"` and a 10-company / 4-KPI /
risk+liquidity+outlook question. Both returned HTTP 200 with 32,259 and 58,720 characters of
assembled context respectively — i.e. they did real retrieval, not a guardrail short-circuit.

**Decided.** Task shape **1 vCPU / 3072 MiB**, split 2560 / 384 as soft reservations. The
documented 512 MiB shape would have been OOM-killed on the first query.

**Three things it revealed that were not the question:**
1. The frontend is *flat* — evidence it is a pure HTTP client, which justifies both its 384 MiB
   reservation and the "co-locating is nearly free" argument.
2. The backend loads **lazily** (213 → 1,220 MiB), so ML components are built on demand, not at
   import.
3. Simple and heavy peaks are close (1,139 vs 1,220), so most of the footprint is fixed cost
   paid by any query, not proportional to result size.

**Blind spot.** `docker stats --no-stream` takes 1–2 s per iteration, giving ~8 samples on a
14 s query. A spike between samples is invisible; the reported peak is a **lower bound**.

## 1.2 Constructor cost, measured in two passes

**Question.** How expensive is the per-request component rebuild in `answer_query`?

**Method.** Run the same construction **twice in one process** and print both passes, so
one-time import cost separates from recurring cost. `tracemalloc` alongside each timing.
Script: `measure_constructor_cost.py`, executed inside the running container via
`docker exec -e PYTHONPATH=/app:/app/serving`.

**Result — (a) MEASURED.**

| Constructor | Pass 1 | Pass 2 (steady state) | tracemalloc peak |
| :-- | --: | --: | --: |
| `MLConfig()` | 66.8 ms | 65.2 ms | 0.3 MiB |
| `init_rag_components()` | 1076.7 ms | **592.2 ms** | 0.7 MiB |
| `PromptLoader()` | 91.5 ms | 92.4 ms | 0.3 MiB |
| `create_bedrock_client_from_config()` | 4.0 ms | 3.8 ms | 0.1 MiB |
| `QueryLogger()` | 72.5 ms | 71.4 ms | 0.3 MiB |
| **Total** | ~1,312 ms | **~825 ms** | <1 MiB |

Pass 1 overstates the recurring cost by ~60%; ~485 ms of `init_rag_components()` is one-time
module import. **The steady-state figure is pass 2.**

**The two-tool insight.** `tracemalloc` reports under 1 MiB, while §1.1 saw ~900 MiB. Both are
right: `tracemalloc` cannot see native allocations, and the ~900 MiB is Arrow/Polars buffers.
Together they establish something neither shows alone — **construction is cheap, the memory is
in the query work, therefore caching constructors will not reduce the task's memory at all.**

This corrected an earlier claim of mine that a large table was being loaded as *construction*
cost. It is not.

## 1.3 Discarded table loads — the measurement that reversed a recommendation

**Question.** The audit (§1.4) found `S3StreamingLoader` memoises tables into instance
attributes. Since `init_rag_components()` builds a fresh loader per request, how much work does
that throw away?

**Method.** Construct a **new** loader instance for the cold reading; reuse **the same** instance
for the warm one. Script: `measure_table_load_cost.py`.

```python
loader = create_data_loader(config)      # fresh instance = cold memo
t0 = time.perf_counter(); df = fn();  cold = ...
t0 = time.perf_counter();      fn();  warm = ...   # same instance = memo hit
```

**Result — (a) MEASURED.** Loader mode: `S3StreamingLoader`.

| Table | Cold (per request today) | Warm (memo hit) | Rows |
| :-- | --: | --: | --: |
| Stage 2 meta | 189.1 ms | 0.00 ms | 614,787 |
| KPI fact | 4.4 ms | 0.00 ms | 9,260 |
| **dim: companies** | **477.5 ms** | 0.00 ms | **25** |
| dim: sections | 201.7 ms | 0.00 ms | 21 |
| **Total** | **872.7 ms** | **0.01 ms** | |

**Two findings.**

**(a) It reversed a recommendation.** Total avoidable per-request work is
`825 ms + 873 ms ≈ 1,698 ms` — about **17.7%** of a 9.6 s query, not the 8.6% that constructor
timing alone implied. I had judged caching "not necessary" from one of the two costs.

**(b) A 25-row table is 2.5× slower than a 614,787-row table.** 477.5 ms vs 189.1 ms. Cost here
is per-call overhead — round trip, file open, parquet footer parse — not data volume.
**Latency tracks round trips, not bytes.**

**Blind spot.** Measured in a container running for hours with a warm `/tmp/finrag_cache`. A
genuinely cold container additionally pays S3 download time. 873 ms is the **warm-disk** figure;
the true first-request cost is higher and **NOT MEASURED**.

## 1.4 AST statelessness audit

**Question.** Is it safe to share the RAG components across requests? Some properties are about
*all* executions, so running the program cannot establish them.

**Method.** Parse each file, walk every `ClassDef`, and bucket `self.x = ...` assignments by
whether the enclosing function is `__init__`/`__post_init__`/`__new__` or something else.
**Report, do not judge.** Script: `audit_state.py` (~90 lines).

**Result — (a) MEASURED.**

```
entity_adapter.py     SAFE  EntityAdapter          (7 attrs, all in __init__)
pipeline.py           SAFE  MetricPipeline         (2 attrs)
query_embedder_v2.py  SAFE  QueryEmbedderV2        (2 attrs)
metadata_filters.py   SAFE  MetadataFilterBuilder  (1 attr)
variant_pipeline.py   SAFE  VariantPipeline        (5 attrs)
s3_retriever.py       SAFE  S3VectorsRetriever     (15 attrs)
sentence_expander.py  SAFE  SentenceExpander       (4 attrs)
bedrock_client.py     SAFE  BedrockClient          (7 attrs)
query_logger.py       SAFE  QueryLogger            (9 attrs)
prompt_loader.py      SAFE  PromptLoader           (5 attrs)
ml_config_loader.py   SUSPECT  MLConfig  (self._aws_creds_source <- _load_aws_credentials():60,72,83)

TOTAL: 17 safe, 1 suspect
```

**The SUSPECT was a false positive.** `ml_config_loader.py:36` calls `_load_aws_credentials()`
**from `__init__`**, so the mutation happens during construction. The tool answered "assigned
outside `__init__`" when the question was "assigned after construction completes." Those differ
whenever a constructor delegates to helpers.

**Blind spots, each checked separately and separately clean:**

```bash
# (a) in-place mutation of a contained object - invisible to the audit
grep -nE "self\.[a-zA-Z_]+\[[^]]+\] *=|self\.[a-zA-Z_]+\.(append|extend|update|add|pop|clear)\(" ...
# (b) module-level mutable globals - outside class scope entirely
grep -nE "^_?[a-z][a-zA-Z_]* *[:=] *(\{\}|\[\])|^global |    global " ...
```

**The one real finding.** `LocalCacheLoader` and `S3StreamingLoader` each mutate 4 attributes
outside `__init__` — lazy memoisation of immutable Polars frames. Benign race (both threads
load equal data, one assignment wins), but worth double-checked locking to avoid two concurrent
62 MB loads. This is what §1.3 then quantified.

**Also found, incidentally:** `supply_lines.py` contains a *second* `init_rag_components`
definition at line 373 — inside a triple-quoted string (lines 369–437), a preserved pre-Lambda
reference copy. Legal, not a bug, and invisible to linters and to graphify.

## 1.5 Cloud introspection as measurement

A class of question answerable by API call, where guessing is inexcusable because the call takes
seconds.

**Cross-region inference routing — (a) MEASURED.** A least-privilege policy for a `us.*` Bedrock
model needs the foundation-model ARN in every region the profile can route to:

```bash
aws bedrock get-inference-profile \
  --inference-profile-identifier "us.anthropic.claude-haiku-4-5-20251001-v1:0"
# "Routes requests to ... in us-east-1, us-east-2 and us-west-2."
```

**Three** regions. A policy naming two would have worked most of the time and thrown
`AccessDeniedException` whenever Bedrock routed elsewhere — the most expensive failure shape.

**Model access — (a) MEASURED.** `list-foundation-models` says a model exists; it does not say
this account may invoke it. Preflight therefore *invokes* both models with a 2-token request.
Both succeeded. `list-foundation-models --by-inference-type ON_DEMAND` returned only
`anthropic.claude-3-haiku-20240307-v1:0` for Claude — i.e. listing would have been actively
misleading about Haiku 4.5, which is reachable only via the inference profile.

**Route tables, not subnet flags — (a) MEASURED.** `MapPublicIpOnLaunch` was `True` on all six
default subnets, but reachability is a property of the route table. Verified a real
`igw-0859a4b15b8c85d71` route on the main table, and **zero NAT gateways** — avoiding
~$32.85/mo per AZ.

**Fargate pricing — (a) MEASURED.** Usage types carry a region prefix, which is why an
unprefixed query returns nothing:

| Rate | x86_64 | ARM64 | ARM saving |
| :-- | --: | --: | --: |
| `USE1-Fargate-*-vCPU-Hours:perCPU` | $0.040480 | **$0.032380** | 20.01% |
| `USE1-Fargate-*-GB-Hours` | $0.0044450 | **$0.0035600** | 19.91% |

**Artifact sizes — (a) MEASURED.** `aws ecr describe-images --query 'sum(imageDetails[].imageSizeInBytes)'`
→ backend 396,603,334 B + frontend 293,581,708 B = **690,185,042 B (0.643 GB) → $0.0643/month**,
against a documented "~$1/month".

**Deployed query — (a) MEASURED.** From the container's own log:
`cost=$0.0140, tokens=12670, time=9631ms`, and
`INFO: 127.0.0.1:34932 - "POST /query HTTP/1.1" 200 OK` — the source address being the proof
that both containers share one network namespace.

## 1.6 Three times my own instrument was the broken thing

Recorded because these are the failures that manufacture false confidence.

**A grep that could never match.** A monitor loop waited on
`grep -qiE "credential|IAM_ROLE|S3_STREAMING|..."`. The log says `using IAM role` — space,
lowercase. Five minutes spent on a condition that could not become true, while the query had
already succeeded. It produced "no evidence of success," one step from being read as failure.
**Test that your check can go green.**

**An exit code from the wrong command.** A deployment was reported "exit code 0"; the 0 came
from the `tail` at the end of the pipeline. The deploy had actually failed on the ECS
service-linked role. Fix: `echo "REAL_EXIT_CODE=$?" >> up.log` immediately after the command.

**A pricing query that returned nothing, read as data that did not exist.** Labelled the ARM
rates UNVERIFIED; the query was simply missing the `USE1-` prefix. **"My tool returned nothing"
and "the data does not exist" are different conclusions.**

Also: `set -- $spec` inside a `for` loop silently did nothing because **zsh does not word-split
unquoted variables**. Symptom was files named `D1-control-plane 1480 1230.png`. Shell dialect is
part of the apparatus.

---

# PART 2 — Embedding vector-space studies

Source: `platform_core/05_CohereDirect_VectorSpaceValidation.ipynb`, executed
**2026-07-29T09:08:27+00:00** (cohere SDK 7.0.8, polars 1.43.0, numpy 1.26.4, Python 3.11.15,
macOS arm64). Total API calls: **2**.

> **An important correction to how this is often remembered.** This is a **transport**
> comparison, not a cross-provider-model comparison. Both sides are *Cohere Embed v4 at 1024-d*
> — one via Bedrock `cohere.embed-v4:0`, one via the native Cohere API `embed-v4.0`. And the
> decision threshold was **0.9999**, not 0.999; the observed mean landed just *below* 0.9999.

## 2.1 Method — the part worth copying

- **Zero Bedrock calls.** Bin 1 (report years 2006–2016) sentences whose Bedrock vectors were
  already on disk were re-embedded through the direct Cohere API, and compared row-wise
  (`05_...ipynb:26-33`).
- **Deterministic sampling, no RNG.** Sort Bin 1 `sentenceID` lexicographically, take evenly
  spaced indices: `Sorted Bin 1 ids : 206,959`, `Stride : 6,467 -> 32 picks (32 unique)`.
  Because the ID is `{cik}_{form}_{year}_section_{n}_{i}`, striding auto-spreads coverage —
  yielding **20 companies, 10 report years** (`:1663-1665`). Rationale given in the notebook:
  byte-for-byte reproducible on any machine, whereas a seeded shuffle depends on the RNG
  implementation.
- **Parameter parity table** mapping the Bedrock `invoke_model` body to the native API, checked
  against `platform_core/embedding_generation.py::_call_bedrock_api`. One genuine vocabulary
  difference: `truncate: "RIGHT"` (Bedrock) vs `truncate="END"` (native), inert because the
  corpus is filtered to ≤500 tokens.
- **(c) CONFIGURED, pre-registered before any numbers were seen** (`:928`, code at `:967`):

  | mean cosine | verdict |
  | :-- | :-- |
  | ≥ 0.9999 | SAME vector space |
  | 0.99 – 0.9999 | drifting, needs decision |
  | < 0.99 | different space |

- Other (c) constants: `SAMPLE_SIZE = 32`, `OUTPUT_DIMENSION = 1024`
  (`# CRITICAL: SDK defaults to 1536 if omitted`), `MAX_API_CALLS = 30`,
  `INPUT_TYPE = "search_document"`.

## 2.2 Result — (a) MEASURED

Matched pairs, same sentence, Bedrock-stored vs Cohere-direct (`:739`, restated `:1681`):

```
min=0.999726  mean=0.999848  median=0.999849  max=0.999900  std=3.27e-05
full precision: min 0.99972571 | mean 0.99984832 | median 0.99984937 | max 0.99990012
1 - mean                                  = 1.517e-04
worst-case deviation (1 - min)            = 2.743e-04
implied mean Euclidean gap on unit sphere  = 0.017417
```

Rubric verdict (`:953-957`): **`SAME MODEL FAMILY, DRIFTING - NEEDS DECISION`**.

L2 norms confirm both sides return unit vectors: stored Bedrock
`0.999999903 / 1.000000108` (`:394`); Cohere-direct `0.999999938 / 1.000000053`.

## 2.3 The determinism surprise — (a) MEASURED

Two calls to the **identical endpoint, identical model id, identical text**, differing only in
API key (trial vs production) (`:1038`, `:1669`):

```
min=0.999723  mean=0.999991  median=1.000000  max=1.000000  std=4.82e-05
Sentences where trial and production vectors are bit-identical : 31/32
Max absolute per-component difference                          : 2.891e-03
```

The single non-identical row (`:1056`): `i=0, 1-cos=2.772e-04, tok=5,
'Item 11 Executive Compensation.'`

Notebook label: `[VERIFIED] SURPRISE - the endpoint is not bit-deterministic` (`:1673`),
attributed to run-to-run nondeterminism in Cohere's serving stack — batch composition, kernel
selection, accumulation order (`:1046-1051`).

So: **same provider, same region, same endpoint → 31/32 identical, 1/32 not.**
**Cross-region determinism: NOT FOUND** — no cross-region vector comparison exists. Cross-region
appears only as a *billing* fact: it debits the daily token cap at **2×**
(`EMBEDDING_PROGRESS_LOG.md:215`).

## 2.4 The reconciliation — is the drift an effect or the noise floor?

This is the best piece of experimental design in the project. Section 9 asks a falsifiable
question: **is the Bedrock-vs-direct difference larger than the difference between two calls to
the same endpoint?** (`:1334-1341`):

```
A) different transport (Bedrock stored vs Cohere direct), n=32
     mean 1.517e-04   median 1.506e-04   max 2.743e-04
B) SAME transport, same model, repeat call, n=1
     mean 2.772e-04   median 2.772e-04   max 2.772e-04

worst cross-transport / worst same-endpoint = 0.99x
-> The cross-transport difference is NO LARGER than the model's own run-to-run variation.
```

The "drift" was noise. **Any measurement without a noise floor is uninterpretable.**

The notebook states its own limitation: the noise-floor estimate rests on **one** non-identical
row, so it is "suggestive, not conclusive — the load-bearing evidence for the GO decision
remains the self-retrieval result."

## 2.5 The discriminating control — does the difference matter for retrieval?

Method: compare Cohere vector *i* against stored Bedrock vector *j*, `i != j`, in three views —
a deterministic derangement (shift-by-1, no RNG), all off-diagonal pairs, and self-retrieval
rank (`:1160-1175`).

```
derangement (32 pairs)        min=0.128905  mean=0.265165  median=0.264675  max=0.465970
all off-diagonal (992 pairs)  min=0.053597  mean=0.253779  median=0.242911  max=0.618884
Separation: matched mean 0.999848  vs  off-diagonal max 0.618884   -> gap 0.380842

Cohere-direct vectors whose nearest stored Bedrock vector is their own : 32/32 (100.0%)
Margin (own - best wrong): min=0.380989  mean=0.565296  max=0.765940
Transport noise    (1 - matched mean)          : 1.517e-04
Semantic signal    (matched mean - off-diag)   : 0.746070
Signal-to-noise ratio                          : 4,919x
```

Context (`:1345-1349`): distance to an unrelated 10-K sentence is **4,920×** the cross-transport
deviation; the worst wrong-pair distance is **1,389×** the worst drift. And **float32 storage
quantum is ~1e-7 per component, so storage precision cannot explain a 1.5e-04 effect.**

**Decision — `:1428`: `DECISION: GO - treat Bedrock and Cohere-direct as ONE vector space.`**
Six checks PASS. Consequences: Bin 3 may be embedded via the direct API into the *same* S3
Vectors index with no re-embedding of Bins 1–2; query-time embedding may use either transport;
the Bedrock daily token cap is sidestepped. Conditions: n=32 all-Bin-1 caveat, `input_type` must
stay `search_document`, `output_dimension` must be passed explicitly.

## 2.6 Full-table provider parity after Bin 3 ran — (a) MEASURED

`platform_core/06_Bin3_CohereDirect_Embeddings.ipynb:2126-2128`, over the whole merged table:

| bin | years | rows | l2_mean | l2_std | min | max |
| :-- | :-- | --: | --: | --: | --: | --: |
| bin1 | 2006–2016 | 206,959 | 1.0 | 2.5365e-7 | 0.999997 | 1.000001 |
| bin2 | 2017–2021 | 224,196 | 1.0 | 2.5410e-7 | 0.999997 | 1.000001 |
| bin3 | 2022–2025 | 183,492 | 1.0 | 2.5297e-7 | 0.999997 | 1.000002 |

`max spread in mean norm across bins: 0.00e+00` — Bins 1–2 are Bedrock-generated, Bin 3
Cohere-direct. Provider provenance is stamped per row via `embedding_id`
(`bedrock_cohere_v4_1024d_...` vs `cohere_direct_v4_1024d_...`). Merge continuity: 3,000 sampled
pre-merge rows → `bit-identical vectors : 3,000/3,000`, `collided : 0`.

## 2.7 The `input_type` asymmetry study — (a) MEASURED

`validation_notebooks/10_InputType_Margin_And_Recall_Check.ipynb`. Method: for each of 10
`P3.v3` gold questions, embed the question twice via direct Bedrock `invoke_model` (bypassing
`QueryEmbedderV2` so the role can be forced) — once `search_query`, once the old buggy
`search_document` — then compare correct-vs-distractor cosine **margin** under each role.
Prediction written down before running. Cost ~$0.0001.

```
questions where search_query margin > search_document margin : 5/10
mean margin (search_query)    : 0.2169
mean margin (search_document) : 0.2157
mean cos(query-role, evidence)    : 0.4071
mean cos(document-role, evidence) : 0.4273
```

A **null result**: 5/10 and a margin difference of 0.0012 do not establish the expected
asymmetry on this sample. Design note worth keeping
(`EMBEDDING_INPUT_TYPE_ASYMMETRY.md:361`): *"The margin matters more than the raw cosine. Raw
cosines are not comparable across roles."*

Part B, live against the real index (614,647 vectors, open regime, topK=30):
`Mean recall@30: 0.133`, `MRR@30: 0.200`, `>=1 evidence hit: 2/10`. Explicitly framed as **a
fresh floor, not an improvement delta** — no prior baseline exists on this account.

## 2.8 What was NOT tested

Worth knowing, because these are commonly assumed to have been checked:

- **Cohere v3 vs v4: NOT FOUND.** `cohere_embed_v3` exists only as an unused config entry
  (`ml_config.yaml:262`).
- **Amazon Titan comparison: NOT FOUND.** Titan appears only as (c) never-populated schema slots
  (`ml_config.yaml:59-62`, `:95-99`, `:264`). The policy in
  `EMBEDDING_TRANSPORT_DESIGN.md:232` — *"THE MODEL IS COHERE EMBED V4, AND NOTHING ELSE... they
  produce DIFFERENT VECTOR SPACES"* — is **asserted, not measured**.
- **768d vs 1024d: NOT FOUND.** `cohere_768d` exists as a config slot and as a **P0 bug**
  (`EMBEDDING_PROVIDER_ABSTRACTION_DESIGN.md:165-173`: `embeddings_path()` sent non-Bedrock
  providers to the 768-d path). No 768-d vectors were ever produced.
- **Matryoshka / dimension truncation quality: NOT FOUND.** The only dimension finding is that
  *both* APIs silently default to 1536-d if `output_dimension` is omitted — a configured pin,
  not a truncation experiment.

---

# PART 3 — Token accounting and cost

## 3.1 There is no tokenizer — and that is the interesting part

**NOT FOUND: any tokenizer library used for cost accounting.** Repo-wide search for `tiktoken`,
`get_encoding`, `cl100k`, `o200k`, Anthropic `count_tokens`: **zero hits.** (The only
`AutoTokenizer` usage is unrelated QA experimentation in a dormant ETL notebook.)

Token counts come from three sources instead, in descending authority:

| Source | Where | Authority |
| :-- | :-- | :-- |
| Provider-reported LLM usage | `bedrock_client.py:171-172` → `models.py:255-259` | authoritative |
| Provider-reported embedding billing | `resp.meta.billed_units.input_tokens` | authoritative |
| **In-house heuristic** | `platform_core/data_preparation.py:271` | estimate |

```python
((pl.col('sentence').str.count_matches(' ') + 1) * 1.33).cast(pl.Int16).alias('sentence_token_count')
```

Word count × 1.33. Used for the ≤1000-token outlier filter (`embedding_generation.py:325-329`).

**And it was validated against the provider's own count — (a) MEASURED** (`05_...ipynb:1566-1568`):

```
meta-table token estimate for the same 32 sentences : 1,342
Cohere-billed input tokens per call                 : 1,360
Estimate vs billed discrepancy                      : +18 tokens (+1.3%)
```

Measured density: ~39 tokens/sentence corpus-wide; **mean 42.5 billed tokens/sentence** on this
sample. A 1.3% error on a heuristic used only for outlier filtering is entirely adequate —
**this is a good example of validating a cheap proxy rather than reaching for a dependency.**

## 3.2 The strongest cost-method artefact: an exact three-way reconciliation

`EMBEDDING_PROGRESS_LOG.md:195-197`, detail at
`EMBEDDING_PROVIDER_ABSTRACTION_DESIGN.md:80-92` — (a) MEASURED:

```
CloudWatch on-demand  (UTC 2026-07-28)   9,277,163
CloudWatch cross-region                    229,032
                                       -----------
total                                    9,506,195
Cost Explorer UsageQuantity x 1M         9,506,195   <- EXACT MATCH
```

The pipeline's own tracked figure was `8,254,022`, differing by `1,023,141` — aborted starts,
ad-hoc embeds, and billed-but-discarded retries.

**Method lesson stated in the source:** a Cost Explorer daily row aggregates every run in that
UTC day, so *"estimate per-bin cost from token counts, not by scaling a CE row"* (`:201`). EDT/UTC
skew is explained at `:199-200`.

This is a genuinely rigorous piece of work: two independent billing telemetry sources agreeing
to the token, plus a named explanation for why the *internal* counter differs.

## 3.3 Configured model rates — (c) CONFIGURED

`.aws_config/ml_config.yaml`, `serving_models`:

| key | model | $/1k in | $/1k out |
| :-- | :-- | --: | --: |
| `development_CH45` **(default)** | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | 0.001 | 0.005 |
| `development` | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | 0.001 | 0.005 |
| `development_CL_SONN_4_5` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | 0.003 | 0.015 |
| `production_balanced` | `us.anthropic.claude-3-5-sonnet-20241022-v2:0` | 0.003 | 0.015 |
| `production_budget` | `amazon.nova-micro-v1:0` | 0.000035 | 0.00014 |
| `openai_compatible` | `meta.llama3-1-70b-instruct-v1:0` | 0.00099 | 0.00099 |

Embedding: `cohere_1024d: 0.00012  # $0.12/1M, confirmed 2026-07-27`. Budget guard
`embedding_budget_usd: 5.00`, alert at 80%. Rerank `rerank_cost_per_1k_queries: 2.00`.

Cost formula (`bedrock_client.py:224-228`) is the obvious one; its docstring value `0.0435` is
**(b) ILLUSTRATIVE**, as are the demo values in `mlflow_tracker.py:707-732`.

## 3.4 Per-query cost analytics from the real query log — (a) MEASURED

Instrumentation: `QueryLogger` writes one row per query to `query_logs.parquet` (S3-synced),
with `input_tokens, output_tokens, total_tokens, cost, context_length, processing_time_ms, ...`.
**Note `context_length` is characters, not tokens** (`models.py:71`, set at `:269`).

`rag_modules_src/02_LLMEval_Notebooks/10_ITest_LLM_Log_Analytics.ipynb:583-586`, n=59 queries,
2025-11-19 → 2025-12-07, 21 unique questions:

```
Total Cost            $0.9317
Total Tokens          493,386  (448,150 in + 45,236 out)
Avg Cost per Query    $0.0158
Avg Tokens per Query  8,362
Avg Processing Time   18,047.8 ms
Failed Queries        0
```

Model-wise (`:782-783`) — **caveat: this cell ran at an earlier point with 45 rows in the log,
so it does not sum to the 59-row totals above.** Treat as a separate snapshot:

| model | queries | total tokens | total cost | avg cost | avg ms |
| :-- | --: | --: | --: | --: | --: |
| claude-haiku-4-5 | 31 | 252,006 | $0.334718 | $0.010797 | 16,592.7 |
| claude-sonnet-4-5 | 14 | 93,274 | $0.386082 | $0.027577 | 17,905.2 |

Query-wise, most expensive first (`:670`, `:688`) — abridged:

| question (truncated) | runs | avg in | avg out | avg cost | avg ms |
| :-- | --: | --: | --: | --: | --: |
| Walmart fiscal 2018-2020 … | 16 | 5,474 | 808 | $0.014227 | 18,472.0 |
| Microsoft Intelligent Cloud revenue … | 7 | 6,989 | 384 | $0.016526 | 14,094.3 |
| Meta regulatory over time … | 2 | 10,469 | 1,476 | $0.036118 | 29,148.2 |
| NVIDIA + Microsoft revenue/op income … | 4 | 10,698 | 1,145 | $0.016423 | 23,367.1 |
| Apple revenue FY2017 | 5 | 8,049 | 354 | $0.0098168 | 11,214.5 |
| 6-company multi-year comparison | 1 | 12,096 | 2,863 | $0.026411 | 50,156.8 |

That last row is the empirical basis for the "complex queries reach $0.04–$0.06 and 50 s+"
claim, and for the observation that **cost scales with entity fan-out, not with question
length**.

## 3.5 Latency + token + cost by complexity class — (a) MEASURED

`finrag_ml_tg1/PIPELINE_LATENCY_ANALYSIS.md:35-44`:

| Metric | Q1 Multi-KPI | Q2 Simple factoid | Q3 Narrative | Average |
| :-- | --: | --: | --: | --: |
| Total latency | 36.8 s | 15.8 s | 31.0 s | 27.9 s |
| **Pipeline** | **7.3 s** | **6.2 s** | **8.0 s** | **7.2 s** |
| **LLM synthesis** | **29.5 s** | **9.6 s** | **23.1 s** | **20.7 s** |
| LLM % of total | 80.1% | 60.5% | 74.3% | 71.6% |
| Input tokens | 16,469 | 12,107 | 12,950 | 13,842 |
| Output tokens | 3,465 | 603 | 1,811 | 1,960 |
| Cost | $0.034 | $0.015 | $0.022 | $0.024 |

Edge case Q4 (`:48-54`): **total 319.9 s, pipeline 7.8 s, LLM 312.1 s**, 5,658 output tokens,
$0.043.

Stage breakdown (`:79-88`): initialization 0.4–0.6 s, KPI pipeline 0.1–0.9 s, **RAG pipeline
5.8–7.0 s**, context assembly <0.1 s, prompt formatting <0.1 s.

**This is the decisive evidence for the central latency claim: the pipeline is essentially
constant at ~6–8 s regardless of complexity, and everything above it is the LLM generating
tokens.** Q4 makes it unmissable — pipeline 7.8 s against LLM 312.1 s (97.6% of total).

It also independently explains why Lambda was never viable: API Gateway caps an integration at
~29 s, and Q1, Q3 and Q4 all exceed that.

**Method: `time.perf_counter()` around six blocks, n=1 per query, 4 queries, on a Windows
machine in `LOCAL_CACHE` mode** (`02_LLMEval_Notebooks/13_LatencyTracking_Serve.ipynb` cell 2).
Q2's own verdict printed `→ Primary bottleneck: Pipeline` (39.5%) — the one query where the
"LLM dominates" story does not hold.

**A method flaw worth naming.** `PIPELINE_LATENCY_ANALYSIS.md:15-17` reports
`P50 27.9s / P95 32.1s / P99 36.3s`. The code producing those is literally
`total_sec * 1.15` and `total_sec * 1.30` **from a single observation**. These are **not
percentiles** — label them (b) ILLUSTRATIVE. Worse, "P50 (Median): 27.9s" is the arithmetic
**mean** of Q1–Q3; the actual median of the three is **31.0 s**. The same document labels 27.9
"Average" in one table and "P50 (Median)" in another.

The 120k-token extrapolation at `:96` ("$0.9–$2.8, 650–800 s") is also **(b) ILLUSTRATIVE**.

## 3.5b The sub-stage breakdown — the best latency artifact in the repo, cited by no document

`run_supply_line_2_rag()` instruments six sub-stages with `perf_counter` into a `timings_ms`
dict (`synthesis_pipeline/supply_lines.py:25`, `:224-269`), which
`build_retrieval_telemetry()` persists under `retrieval_stats.timings_ms`
(`utilities/retrieval_telemetry.py:36`, `:62`). **30 real end-to-end runs carry it**, in
`validation_notebooks/15_reranking_answer_quality_scored_30q.json` (10 questions × 3 configs,
real Bedrock, 2026-07-30, on the Mac).

Aggregated — **(a) MEASURED**:

| Sub-stage | A: no rerank (n=10) mean / median | B: top-16 | C: top-8 |
| :-- | --: | --: | --: |
| `entities` (EntityAdapter) | 44.6 / 45.7 ms | 44.7 | 44.7 |
| `embed` (query embedding) | 398.9 / 283.3 ms | 361.2 | 349.4 |
| **`retrieve` (S3 Vectors)** | **4667.1 / 4726.3 ms** (3017.7–5776.2) | 3733.4 | 3837.6 |
| `expand` (SentenceExpander ±3) | 50.7 / 52.2 ms | 53.0 | 50.4 |
| `rerank` (Cohere Rerank 3.5) | — | 463.1 | 479.1 |
| `assemble` (ContextAssembler) | 3.7 / 3.9 ms | 4.2 | 3.0 |
| **sub-stage sum** | **~5,165 ms** | ~4,660 | ~4,764 |

**`retrieve` is ~90% of the RAG pipeline.** Query embedding is ~8%. Entity extraction, sentence
expansion and context assembly **together are under 100 ms — about 2%.** Reranking adds only
~460–480 ms.

**This flatly contradicts a headline claim in `Performance_Cost_Analysis.md:10`**, which asserts
the pipeline "includes S3 streaming overhead (~5-8s), lazy metadata joins (~3-5s), window
expansion over 469K sentences (~8-12s)":

| Claim | Measured | Error |
| :-- | :-- | :-- |
| window expansion "~8-12 s" | **50.7 ms** | **~200×** |
| "3-5 second metadata join" | not a stage in any instrumentation | unbacked |
| components summing to 16–25 s | measured pipeline is 5.2–8.0 s | cannot coexist |

**Every number in `Performance_Cost_Analysis.md:10` and `:30` should be treated as (b)
illustrative prose, unbacked.** This matters because those figures have been quoted as the
optimisation targets — someone optimising "window expansion" would have been tuning a 50 ms
stage while a 4,667 ms stage sat next to it.

> **The lesson: an unmeasured bottleneck claim will send you to the wrong stage.** The telemetry
> that settles it was built in 2026-07; before that, `retrieval_stats` was declared in
> `serving/backend/models.py:86` and was **`null` in every response export**, which is why
> `10_ITest_LLM_Log_Analytics.ipynb` could report `Failed Queries: 0` across 59 queries while
> being blind to retrieval failures entirely.

Also (a): retrieval-only eval at scale runs **30.44 s/query**
(`11_..._Harness.ipynb`: `31/31 questions scored in 943.7s`) — ~6× the per-pass figure, because
the harness does gold-ID joins per question. And the reranker's measured latency
(**463–479 ms mean**) came in at the low end of a prior `[I]` estimate of "~0.5–2 s" — the
estimate was right in order of magnitude.

## 3.6 Embedding ingestion cost ledger — (a) MEASURED

`EMBEDDING_PROGRESS_LOG.md`:

- Bin 3 (`:70-71`): `180,848 sentences, 1,884 calls, 104.3 min, zero retries, 7,555,061 billed
  tokens = $0.9066`, 76 shard checkpoints.
- Total (`:83-84`): **`~$2.21`** (~$1.30 Bedrock for Bins 1–2 + $0.9066 Cohere for Bin 3),
  against ~$5 estimated.
- Quota (`:102`): `8,100,000 tokens/day, rolling 24h`. Full 3-bin redo: `19,111,042 tokens =
  $2.29`.
- Pre-run estimate vs actual for Bin 3 — a clean calibration record: predicted
  `7,162,360 tokens / ~$0.86 / ~100 min`; actual `7,555,061 / $0.9066 / 104.3 min`. **Within
  5.5% on tokens and 4% on wall time.**

## 3.7 S3 Vectors cost model — (b)/(c), NOT a measurement

`finrag_ml_tg1/S3Vect_QueryCost.md` is a **model**, and should be cited as one:
`cost_per_call(K) ≈ (15 × K / 1,000,000) × P`; storage `~$0.30 per million vectors per month`,
so 203k vectors `≈ $0.06/month`. Summary metrics: `avg cost per query $0.0170`, `monthly
recurring $25.50`, `annual $306.00`.

Its own conclusion is the useful part: *"The real cost centers are typically embeddings and LLM
tokens, not vector comparisons."*

**Provenance gap flagged:** the `6,153 in / 777 out` and `$0.02782 / $0.01044` figures at
`:175-176` appear nowhere else in the repo and no run producing them could be located. **Do not
cite as measured.**

## 3.8 Cost-specific contradictions

The full cross-document contradiction table is **Part 6**. Two are cost-specific and belong here:

1. **`Performance_Cost_Analysis.md:8`** claims *"$7-10/month for 1M queries!!"*, inconsistent with
   `S3Vect_QueryCost.md`'s own table showing **$85/month at 5,000 queries/month**. The former
   appears to cover infrastructure only, excluding Bedrock tokens. **Neither states its scope**,
   which is the actual defect — a cost figure without a scope is not a number.
2. **Cost saving vs a managed vector DB** is given as both **"99%"** (`Performance_Cost_Analysis.md:7`)
   and **"60-73%"** (`S3Vect_QueryCost.md:267`), in the same document family, with no comparison
   source for either. Unresolved.

One apparent contradiction that is **not** one: `614,787` meta rows vs `614,647` live vectors. The
difference is exactly **140** — the token-outlier sentences (`sentence_token_count > 1000`)
excluded by design, 53 / 43 / 44 across the three bins. Documented at
`EMBEDDING_PROGRESS_LOG.md:67-68`. **Worth stating, because a 140-row gap looks like drift until
you find the intent.**

---

# PART 4 — Ablation and evaluation studies

The reranking investigation is the most complete piece of empirical work in the project — five
linked studies, several published errors corrected in place, and a ship decision that went
against the headline numbers. It is worth reading as a single arc.

## 4.1 Step 1 — the A0/A1/A2 ablation, and an architectural fact that reframes it

`validation_notebooks/12_Reranker_Ablation_A0_A1_A2.ipynb`; `RERANKING_IMPACT_ANALYSIS.md`.

**Method.** Three arms on the same 31 gold questions: **A0** no reranker (shipped), **A1**
`top_n=None, min_score=0.0` (scoring only — membership *unchanged*), **A2** `top_n=8` (real prune
config). Cross-encoder `cohere.rerank-v3-5:0` via `bedrock-agent-runtime`, one call per question.
A0/A1 membership confirmed identical by inspection (166 sentences, same set).

**The reframing.** `ContextAssembler._sort_sentences()` always re-sorts survivors into document
order before the LLM (`RERANKING_IMPACT_ANALYSIS.md:24-30`). So **a reranker that only reorders
changes nothing about the final context string — the only lever with any effect is pruning.**
This is a *pruning* test, not a ranking test. Recognising that before interpreting the numbers is
what makes the rest of the arc coherent.

**Result — (a) MEASURED:**

| Metric | A0 | A1 | A2 |
| :-- | --: | --: | --: |
| `recall@5` | 0.0430 | 0.1371 | 0.1371 |
| `recall@30` | 0.0591 | 0.4704 | 0.4704 |
| `MRR` | 0.0288 | 0.0758 | 0.0735 |

A1 vs A2 is flat (MRR −0.002). The A0→A1 jump is a reordering artifact, and the notebook's own
sanity check said so: `Sanity check -- A0 vs A1 recall@30 should match (A1 doesn't prune):
0.0591 vs 0.4704 MISMATCH -- investigate`. **A self-check that fired and was left visible.**

**Gate 0** (gold-containing block near top of A1's ranking): **15/31 (48%)** against a
pre-registered bar of ≥24/31.

## 4.2 Step 2 — top-N sweep, and the ceiling

`notebook 13`, scoring cached to `data_cache/rerank_scored_blocks_31q.json` so the whole sweep
cost **zero additional Bedrock calls**. Good method hygiene worth copying.

| top_n | avg sentences kept | gold survival | recall@30 | MRR |
| --: | --: | --: | --: | --: |
| 4 | 27.9 | 38.7% | 0.4059 | 0.0680 |
| **8 (shipped config)** | 50.9 | **54.8%** | 0.4704 | 0.0735 |
| 16 | 93.0 | 58.1% | 0.4704 | 0.0742 |
| 30 | 125.8 | 64.5% | 0.4704 | 0.0755 |
| all (~29 blocks) | 132.1 | **64.5%** | 0.4704 | 0.0758 |

**Negative result #1 — the ceiling is upstream.** Even **zero pruning** reaches only 64.5%
survival. The remaining ~35% is evidence the *retriever* never surfaced, "which no amount of
generosity at the reranker stage can recover" (`:170-177`). And top-16 buys **+3.3 points over
top-8 for roughly double the tokens.**

**Negative result #2 — two of the three metrics are structurally incapable of moving.**
`RERANKING_FINAL_SYNTHESIS.md:425-433`: `recall@5` is flat at 0.1371 for every `top_n` because
`kept_ids` is assembled from blocks already sorted by score, so *the first five sentence IDs are
identical for every `top_n` ≥ 1*. `recall@30` only moves between N=4 and N≥8. **"Neither column
carries information about the pruning choice, and neither should be cited as evidence about it."**

That is a rare and valuable kind of finding: **discovering that your metric cannot answer your
question.**

**A metric-definition correction.** The notebook's `gold_survived = (n_hits == len(gold_ids))` is
a *strict conjunction* — every gold ID must survive. Recomputed both ways at top-8: **54.8%
strict, 64.5% loose**. Cause of the strict floor: for 6 of 7 multi-evidence questions the
retriever surfaces only 1–2 of the 3–4 required gold sentences, so they fail at *any* `top_n`.
Isolating pruning from the ceiling: **of the 25 questions where gold is reachable, top-8 loses 5.**

## 4.3 Step 3 — score calibration, and a falsified prediction

Notebook 14, over **910 scored blocks (27 gold-containing, 883 non-gold)** — (a) MEASURED:

```
gold-containing: n=27   mean=0.5175  median=0.5181
non-gold:        n=883  mean=0.2363  median=0.1579
Fraction of NON-gold blocks scoring >= the median GOLD score: 0.120
```

**A hypothesis tested and abandoned, recorded rather than dropped.** The author expected the
gold/non-gold gap to be mostly a *length* artifact (gold blocks are 9.11 vs 4.36 sentences).
Controlling for length, it survives (`RERANKING_FINAL_SYNTHESIS.md:303-315`):

| block length | gold mean | non-gold mean | gap |
| :-- | --: | --: | --: |
| 1 sentence | 0.193 (n=3) | 0.160 (n=318) | +0.033 |
| 2–3 | 0.359 (n=5) | 0.242 (n=135) | +0.117 |
| 4–7 | 0.611 (n=8) | 0.285 (n=364) | **+0.326** |
| 8+ | 0.610 (n=11) | 0.323 (n=66) | **+0.288** |

*"my hypothesis was wrong and I am recording that rather than quietly dropping it."*

**Length bias quantified:** Pearson **r = +0.285** between block sentence-count and relevance
score; mean score rises 0.161 → 0.247 → 0.292 → 0.364 with length. The 3 single-sentence gold
blocks average 0.193 — **they would be pruned at essentially any `top_n`.**

**A prediction falsified.** A prior design note predicted `min_score` would "sit at 0.0
permanently." The sweep says a **0.05–0.1 floor is worth piloting** (0.05 cuts ~18% of blocks for
a 7.4-point gold-recall cost).

## 4.4 Step 4 — the answer-quality A/B/C with 30 real LLM calls

`validation_notebooks/15_Reranking_AnswerQuality_E2E.ipynb`. 10 `P3.v3` questions × 3 configs,
real Bedrock Haiku 4.5, **30/30 succeeded**, all `stop_reason == "end_turn"`, actual spend
**$0.492**.

**A method detail worth stealing.** `answer_query()` has no config-swap parameter, and editing
`ml_config.yaml` on disk was unsafe because another process was reading it. So the author **first
verified empirically that `MLConfig()` is not a singleton**, then hand-mirrored the init path with
an in-memory-only override — leaving everything downstream of config construction as unmodified
production code. That is how you run a config ablation without either mutating shared state or
forking the code under test.

**Result — (a) MEASURED:**

| config | avg ROUGE-L | avg cosine | avg ctx chars | avg in tok | total cost |
| :-- | --: | --: | --: | --: | --: |
| A no rerank | 0.1012 | 0.7618 | 35,905 | 13,108 | $0.1970 |
| B top-16 | 0.1052 | 0.7324 | 25,015 | 10,689 | $0.1631 |
| **C top-8** | **0.1120** | **0.7705** | **14,314** | **8,140** | **$0.1319** |

Per-question reductions vs A: context median **33.0%** (B) / **61.0%** (C); cost median **16.9%**
(B) / **31.6%** (C). Retrieval counts were **identical across arms** (`filtered_hits` 19.8,
`global_hits` 12.6, `union_hits` 28.5, `expanded_sents` ~145) — only `reranked_sents` differs.
Clean arm hygiene.

**Aggregate verdict: null.** Cosine goes 0.762 → 0.732 → 0.771, "a dip-then-recover pattern with
no monotonic story." *"No meaningful uniform quality change detected. That is a legitimate,
useful finding, not a failure to find something."*

## 4.5 Step 5 — reading the actual answers, which is what changed the decision

> **Correction to an earlier draft of this document.** I wrote that reranking was declined
> because a ROUGE-L delta of 0.011 sits inside the noise of a 10-question sample. That is
> *true* but it is **not the recorded reason.** The real reason came from reading the answers,
> and it is more interesting.

**LLM/human-as-judge tally** (one judge, ten questions, no blinding — **self-flagged as a bias
risk**), `RERANKING_FINAL_SYNTHESIS.md:353`:

> **B vs A: 1 better, 6 same, 3 worse. C vs A: 3 better, 2 same, 5 worse.**

**The pattern:** *"Aggressive pruning helps when the answer is a single fact, and hurts when the
answer must span multiple entities, years, or sub-topics."* C's three wins are all single-fact
questions; its five losses are all breadth questions.

**Entity starvation, mechanistically traced.** For P3V3-Q005 (4 companies), 112 expanded sentences
were available; survivors were 29 at top-16 and **10 at top-8**, and at top-8 only 2 of 4
companies had surviving evidence. Config C then answered: *"the provided dataset contains Item 1A
Risk Factors sections only for Apple Inc. and Icahn Enterprises L.P."* — a **confident false
absence.**

**The binding defect, found only by reading the text** (`:27-33`): **45.2% of the blocks surviving
at top-8 come from a fiscal year the question did not ask about**, versus a 31.5% off-year rate in
the unpruned pool. Reranking does not merely fail to fix off-year contamination — **it
concentrates it**, because off-year blocks are systematically longer (5.49 vs 4.04 sentences) and
score higher (0.300 vs 0.219), and *the cross-encoder never sees year metadata at all.*

**Verdict:** `rerank_top_n_blocks = 8` **not fit to ship; neither is a flat 16.**
`enable_reranking: false` stays (confirmed at `ml_config.yaml:511`).

**And the automated metrics were anti-correlated with quality.** On Q004, ROUGE-L ranks C
*highest* (0.118 vs 0.079) while C answers 1 of 3 companies. On Q005, cosine ranks C *highest*
while C declines 2 of 4. Conclusion recorded: *"the automated metrics are close to uninformative
about answer quality, and occasionally anti-correlated with it. They are fine as cost/context
instrumentation and should not be used as a quality gate."*

**Two prior conclusions overturned in the same pass**, including an entity-cardinality fix that
*"converts an honest refusal into a confident false negative."*

> **The lesson of the whole arc: the aggregate metrics said ship it; reading ten answers said do
> not. Reading the outputs is a measurement method, and on small samples it is often the
> highest-resolution one available.**

## 4.6 The reproducibility failure — the most consequential methodological finding

`RERANKING_FINAL_SYNTHESIS.md:117-125`:

> *"retrieval is not reproducible run to run, even with `enable_variants = False`."*

Pool membership for the same ten questions across two draws: Q002 overlaps 192/206, Q005 98/111,
Q003 170/187. Worse, **gold coverage differs between draws** — Q004 2/3 vs 1/3, Q005 2/4 vs 1/4,
Q002 1/4 vs 0/4.

Consequences stated: block-level and answer-level analyses are **not strictly coupled**, and the
"64.5% ceiling" is a single-draw estimate that is *probably an underestimate*. Cause **not
diagnosed** — possibly S3 Vectors ANN approximation, possibly `_proportional_topk()` sampling.

**This undermines the precision of every retrieval number above, and it was found and written
down rather than buried.** It is the single most important open item in the evaluation stack.

## 4.7 A published error kept visible

`RERANKING_IMPACT_ANALYSIS.md:7-13`: the original claim *"gold-evidence survival under A2
pruning: 31/31 (100%)"* was **wrong** — it compared `recall@30`, which truncates at 30 sentences,
against a pruned set actually holding ~51. True full-membership survival at top-8 is **54.8%**.

The wrong text was **struck through rather than deleted**: *"Left the original wrong text below
struck through rather than deleted, so the mistake and its correction are both part of the
record."* That is the right instinct, and it is why this arc is trustworthy.

## 4.8 The retrieval floor — the uncomfortable number

Two independent measurements against the live index:

| Source | Regime | Result |
| :-- | :-- | :-- |
| `10_InputType_Margin_And_Recall_Check.ipynb` Part B | open, no filter, topK=30, 10 P3.v3 q | `recall@30 0.133`, `MRR@30 0.200`, **≥1 hit: 2/10** |
| `11_RetrievalTelemetry_RecallMRR_Harness.ipynb` | filtered+global union, variants off, 31 q | `core_recall@30 0.5376`, `core_mrr 0.1179` |

By scope (harness): local (n=24) 0.583; cross_year (n=4) 0.396; cross_company (n=3) 0.361.

**A surprising result:** `expanded_recall@k` is **worse than `core_recall@k` at every k**
(expanded_recall@30 0.0591 vs core 0.5376). Window expansion *dilutes* rank-based metrics by
inflating the list with non-core neighbours — so expansion helps the LLM's context and hurts the
retrieval metric. **A case where a metric penalises a change that is actually beneficial.**

This also contextualises the deployment verification query, which returned the "KPI snapshot not
in retrieved context" guardrail rather than the revenue figure: **that was retrieval coverage
behaving exactly as measured, not a deployment fault.**

## 4.9 The gold suites are the weakest link — three measured defects

`RETRIEVAL_IMPROVEMENT_STUDY.md:833-865`. This is essential context for every quality number
above.

1. **Circularity (fatal).** P3.v2 evidence was selected by the same *class* of retrieval being
   evaluated — regex keyword match, e.g. `Net Income: (?i)\bnet (income|loss)\b`. **17 of 31**
   questions are flagged bad or too broad. *"A better retriever will score worse against those
   labels."*
2. **Year-blindness.** **10 of 31 (32%)** form 5 pairs whose gold answers share their first 100
   characters (Walmart 2011/2021, Meta 2023/2024, …). *"These 10 questions cannot validate the
   fix they most concern."*
3. **Statistical power.** 24 of 31 questions have exactly 1 evidence sentence → binary recall.
   With n=31, **only a swing of ≥6–7 questions is distinguishable from noise**; minimum
   detectable MRR effect is **+0.07 to +0.13**, against an observed A1-vs-A2 change of −0.002.
   *"A '24/31 → 27/31' improvement is **not** a finding."*

**And a bad-question detector was built and it worked** (`06_Gold_Test_Framework.md:849-880`):
signal = `ROUGE-L < 0.05` **and** `BERTScore > 0.75` **and** both texts match meta-commentary
regexes. It flagged **3 of 31** as bad — a *"10% false-positive rate in automated question
generation."* Catching P3V2-Q001, which scored BERTScore 0.802 while *both* gold and answer were
non-answers.

**Metric availability, checked empirically** (`RERANKING_ANSWER_QUALITY_TEST.md:42-68`):
`bert_score`, `rouge_score` and `bleurt` are installed in **none** of the four conda
environments on the machine, and **no BLEURT-20 checkpoint exists on disk**. So BERTScore and
BLEURT were **not computed in any 2026-07 run**, and ROUGE-L was reimplemented *without Porter
stemming*, so scores read slightly low. **The headline 0.826/0.446 figures cannot be reproduced
today.**

---

# PART 4b — Memory, I/O, and measurements that deleted code

## 4b.1 The memory-explosion investigation — a crash that redesigned a module

`TechNotes_MemoryExp_Handling.md`. The observed failure was a **Windows
`STATUS_ACCESS_VIOLATION`, error code 3221225477** — "a native fault or OOM in a C/Rust library
(here: Polars' join or allocation)" (`:17`). A Python-level OOM would have raised
`MemoryError`; a native fault means the allocation died inside Rust, below Python's visibility.
**The error code itself was the diagnostic.**

The key insight recorded (`:21`):

> *"Lazy `scan_parquet` alone doesn't help if, at the end, we still call `.collect()` on a query
> that conceptually is 'meta + full vector list joined and held in RAM'."*

That is the subtle part of lazy evaluation, and it is worth memorising: **laziness defers work,
it does not shrink the result.** A lazy plan whose final `collect()` materialises a 1.67 GB list
column is exactly as fatal as an eager read.

**The artifact proving the redesign happened.** `platform_core/s3_vectors_table_prep_eagerload_v1.py`
is *entirely commented out*, with the header:

```python
# # THIS IS AN EAGER LOADING SCRIPT WHICH NOW DOESNT WORK:
# # Reason, study memory explosion technical research notes in the same project.
```

Its replacement `s3vectors_table_preparation.py` documents the new contract: `scan_parquet` not
eager load, `sink_parquet` **streaming write** (`:313`, zstd), dimensions validated separately,
hashes computed chunk-wise (`:259` — *"map_elements runs per-chunk in streaming mode (not giant
Python list)"*), and `:53-58` — *"Never loads full embeddings table (1.7GB) into memory / Never
materializes joined table / Only tracks scalars, not large DataFrames."*

The two file headers even disagree about the same job — the eager version called Stage 3 *"a JOIN
operation (cheap, ~1-2 min)"*; the lazy version calls it *"memory-intensive with 1.7GB embedding
column."* **The estimate that preceded the crash is preserved next to the one that followed it.**

A diagnostic habit was adopted (`:24-33`): run `print(plan.explain())` /
`describe_optimized_plan()` **before** executing a big join.

**Caveat on this document — (b).** `:3` claims *"we calculated the exact memory spikes for 300MB,
750MB and 1.7GB dataset versions… and tracked them across operations"*, but **no such table
exists in the repo** — the numbers are asserted, not shown. And `:10`'s "407,048 rows × 1024
floats × 4 bytes ≈ 1.67 GB" is arithmetic, with a row count that **matches no other figure
anywhere** (see §4b.3).

## 4b.2 Two measurements that killed features rather than building them

**The checkpoint-salvage feature that was never built.** Checkpointing writes every 50 batches.
Worst-case loss on a crash was *quantified* rather than assumed
(`EMBEDDING_TRANSPORT_DESIGN.md:161-163`):

> `50 batches × 96 texts = 4,800 sentences ≈ 192k tokens = **$0.023**. Two cents. Not worth any
> salvage machinery — so we will **not** build an abort-flush.`

**A cost measurement used to decline engineering work.** This is the inverse of the usual
direction and worth imitating.

**The resume-authority fix that removed a dependency.** The resume logic had been reading an
*ephemeral 483 MB scratch checkpoint* while the durable 2.29 GB vectors table was never consulted
(`:136-138`). Fix: resume from the vectors table — *"removes a dependency rather than adding
machinery."*

**Throughput facts behind the ingestion run — (a):** batches always exactly 96 texts, because
*"the token cap of 128k is never the binding constraint at ~39 tokens/sentence"* — **RPM was the
real ceiling, not TPM.** Identifying which of two limits actually binds is the whole of rate-limit
engineering.

**Byte-level integrity method — (a).** Local and S3 copies of the 2,293,538,065-byte vectors table
verified byte-identical by size *and* a locally recomputed multipart composite ETag
`b47a120c6558e28f55f3770d18f1e9fa-35` (64 MB parts), with the explicit warning
(`EMBEDDING_PROGRESS_LOG.md:191`): *"compare byte sizes (do not trust the multipart ETag as an
MD5)."* Knowing that a multipart ETag is **not** an MD5 is exactly the kind of detail that turns a
verification into theatre if you get it wrong.

## 4b.3 The corpus-size contradiction set — five numbers for one corpus

This one is worth its own section because it silently corrupts every per-row claim:

| Figure | Where | Status |
| --: | :-- | :-- |
| **203,076** | `.claude/CLAUDE.md`, `S3Vect_QueryCost.md:9`, `07_S3_CostProjections.ipynb` | the **old, deleted** account's index |
| **469,252** | `06_ITest_RetrievalSpine_Steps8to10.ipynb`, `Performance_Cost_Analysis.md:28` | explicitly labelled **stale** at `EMBEDDING_PROGRESS_LOG.md:132` |
| **614,647** | current vectors / Stage 3 rows | **current, verified** |
| **614,787** | current Stage 1 / meta rows | **current, verified** (differs by the 140 token-outliers excluded by design) |
| **407,048** | `TechNotes_MemoryExp_Handling.md:10` | matches nothing else |
| "200K rows, 500MB+" | `CLAUDE.md:86-87` | stale against measured 37.5 MB / 64.8 MB |

Related: **"4,674 companies"** appears in several docs; the embedded corpus is **25 companies**.
`RETRIEVAL_IMPROVEMENT_STUDY.md:910` adjudicates: *"4,674 is the upstream ETL universe. Several
doc claims about corpus-scale noise are therefore overstated."* And
`06_Gold_Test_Framework.md:75` describes an *"open regime (no filters, global **71.8M-sentence**
search)"* — off by roughly **100×** against any corpus figure in the repo.

The vectors parquet also has **three** committed sizes: 2.29 GB (measured bytes), 1.56 GB, and
~2.2 GB — in three different documents, for one file.

> **When a project has five numbers for its own corpus size, no per-row or per-vector claim in it
> can be trusted without re-derivation.** This is the cheapest possible audit and the one most
> often skipped.

## 4b.4 Lazy-vs-eager: a rule the serving path violates

`CLAUDE.md:94` states: *"Use `pl.scan_parquet()` on Stage2/3 files — NEVER `pl.read_parquet()`.
They are 500MB-3GB. Eager loading crashes kernels."*

But `loaders/data_loader_strategy.py` uses **`pl.read_parquet` (eager) at every site** — `:94`,
`:104`, `:113`, `:130`, `:176`, `:184`, `:203`, `:215`, `:241`, `:250`. There is no
`scan_parquet` in the serving data path at all.

This is **survivable rather than wrong**: the serving path reads the 62–65 MB Stage 2 *meta*
table, not the 2.29 GB vectors table, and 62 MB eager is fine. But the rule as written does not
distinguish them, so the code appears to violate its own documented standard. **A rule that is
routinely and correctly violated should be rewritten to say what it actually means** — here,
"never eager-load the vectors or Stage 3 tables."

## 4b.5 Redundancy and context-quality measurements — the dominant documented failure mode

`RETRIEVAL_IMPROVEMENT_STUDY.md:152-172`, computed over **25 real exported contexts** — (a)
MEASURED:

| Metric | Value |
| :-- | --: |
| Median sentences per context | **100** (74–199) |
| Median context size | **21,119 chars** (15,210–52,082) |
| Mean exact-duplicate sentences per context | **22.0** |
| Mean near-duplicate (60-char prefix) | **28.6** |
| **Mean near-duplicate rate** | **22.7% of the context** |

Corpus-wide over 614,787 rows: unique sentence *texts* **338,869**, i.e. an **exact-duplicate text
rate of 44.9%**. Of the 98,825 texts appearing more than once, only **827 (2.1% of occurrences)**
are cross-company. Top offender: *"Because of its inherent limitations, internal control over
financial reporting may not prevent…"* — **424 occurrences across all 25 companies.**

Root cause located in code: the dedup key is `(sentence_id, cik_int, report_year, section_name)`
at `sentence_expander.py:517` — *"Nothing in the pipeline ever compares sentence text."*
Projected value of fixing it: **~23% of the context window reclaimed (measured, not estimated).**

**The flat-score-distribution finding — the strongest single argument for a reranker in the repo**
(`08_RAGArch_DesignNotes.ipynb` cell 17, verbatim):

```
All thresholds (0.0 -> 0.5): 45 hits, NO rejections
Similarity range: [0.674, 0.737]   Mean: 0.693, Median: 0.687
Zero hits below 0.6 similarity, Zero hits above 0.8 similarity
no "long tail" of weak matches to filter out AT ALL.
```

> *"Your top-45 candidates occupy a 0.063-wide band. Cosine similarity carries essentially zero
> ordering information at this granularity."*

That is a beautiful negative result about a *metric*: the similarity score cannot rank within the
candidate set, which is precisely why a cross-encoder was worth testing — and why `min_similarity:
0.3` (`ml_config.yaml:487`) can never reject anything.

**The wrong-year audit — (a), all 23 response exports.** Comparing asked years against the
`| FY nnnn |` headers actually present in the delivered context: **8 of 23 (35%)** exports where
the asked year is **entirely absent**. Year range present in *every* context: 2016–2020 only.
Grounding held — the LLM refused or flagged the gap in every case. Root cause: **23.8% of the
corpus (146,203 sentences) is pre-2015**, unreachable under a then-hardcoded 2015 floor
(`metadata_filters.py:176`), while **12 of 31 gold questions (39%) target pre-2015 years.**
`recent_year_threshold` is now 2006, but `metadata_filters.py:176` still ignores
`entities.years` entirely.

**Multi-company starvation — deterministic, (a).** In one export `MSFT 3 / NVDA 10`; across three
separate runs `MA 4, RDN 2, NFLX 0` — **Netflix received zero context in all three.** Cause:
`cik_int {"$in": [...]}` with a single global topK and *"no per-entity budget anywhere in
`s3_retriever.py`."* A single-query-multi-entity fan-out with one shared budget starves the tail
entity **by construction**, not by chance.

**Live evidence of total multi-path collapse — (a)** (`09_ITest_LLM_Serves_P3.ipynb` cell 5):

```
  ✓ Base query: 15 raw hits
→ Retrieving 3 variant queries (filtered only)...
  ✓ Variant 1: 0 hits    ✓ Variant 2: 0 hits    ✓ Variant 3: 0 hits
  • Filtered: 0 hits     • Global:   15 hits
```

The filtered call **and all three *paid* Haiku variant calls** returned `{"vectors":[]}`. Money
spent, zero retrieved. Core recall 2/4 on that question.

**A finding published wrong, then corrected — ITEM_15.** Initially called "boilerplate leakage";
on inspection ITEM_15 has the **highest `likely_kpi` rate of any section (24.9%)**, above ITEM_7
(24.2%) and ITEM_8 (19.7%), and only **13.4%** of its sentences match auditor/exhibit boilerplate
patterns. Conclusion reversed: `exclude_sections` *"must never be switched on… Its being dead code
was a lucky accident."* A prior recommendation for a soft section boost was **retracted** on
learning S3 Vectors offers ANN + metadata filtering only — *no scoring hook, no boost primitive.*

# PART 5 — The method catalogue

Every measurement in this document, as a reusable table.

| Method | Question it answers | Tool | Structural blind spot |
| :-- | :-- | :-- | :-- |
| External sampler + real work | peak resource use | `docker stats` loop | spikes between samples; no attribution to code |
| Two-pass timing | one-time vs recurring cost | `perf_counter` ×2 | doesn't separate CPU from IO |
| Cold instance vs warm instance | what a per-request rebuild discards | new vs reused object | warm disk cache hides cold-start cost |
| Python-heap profiling | Python allocation | `tracemalloc` | **native/Arrow memory invisible** |
| AST class audit | mutation outside construction | `ast` module | helpers called from `__init__`; in-place container mutation; module globals |
| Capability invocation | can this account actually do X | real API call | only proves *now*, in *this* region |
| API introspection | declared truth (regions, routes, prices) | `describe-*` / `get-*` | says nothing about whether it works |
| Artifact measurement | real size/shape | `describe-images`, `wc`, `ls` | none — this is ground truth |
| **Noise-floor control** | **is my effect bigger than self-variation** | repeat the identical call | needs enough repeats; here n=1 |
| **Discriminating control** | is the effect semantically meaningful | mismatched pairs / derangement | must be deterministic to be reproducible |
| Deterministic striding | reproducible sampling | sort + stride | correlated IDs could bias; here IDs help |
| Pre-registered rubric | stops post-hoc rationalisation | write thresholds first | must be honoured when inconvenient |
| Proxy validation | is my cheap estimate good enough | compare to authoritative count | validated on one sample |
| Cross-source reconciliation | do two telemetry sources agree | CloudWatch vs Cost Explorer | timezone/aggregation skew |
| Full ablation grid | does a component help | N questions × M configs, real calls | small N → noise dominates small deltas |
| **Sub-stage instrumentation** | **which stage actually dominates** | `perf_counter` per stage, persisted into telemetry | needs to be *persisted*, or it is unavailable after the fact |
| **Cached-score sweep** | parameter sweep without re-paying | score once → JSON → sweep offline | freezes one retrieval draw (see §4.6) |
| **Membership-identical arms** | isolating one variable | A0/A1 verified same member set | requires explicit proof, not assumption |
| **Reading the outputs** | is the answer actually better | human/LLM judge on N triplets | unblinded, single judge, n=10 |
| **Error-code forensics** | Python OOM vs native fault | `3221225477` = `STATUS_ACCESS_VIOLATION` | tells you the layer, not the line |
| **Anti-join coverage check** | nothing missing AND nothing orphaned | two-way join both directions | one direction alone proves half |
| **Byte + ETag integrity** | is the S3 copy the local copy | size compare + recomputed multipart ETag | a multipart ETag is **not** an MD5 |
| **Duplicate-rate analysis** | how much context is wasted | exact + 60-char-prefix dedup over real exports | prefix matching is a proxy for semantic dup |
| **Score-distribution check** | can this score rank anything at all | min/max/spread over candidate set | a 0.063-wide band ranks nothing |
| **Metric-sensitivity check** | *can* my metric move under this change | reason about the definition first | the most-skipped check of all |

---

# PART 6 — Consolidated contradictions

Every place two documents disagree about the same quantity. A contradiction is a finding: it
tells you at least one document is wrong, and usually that nobody has re-derived the number
since it was first written.

**Ordered by how much damage the wrong value would do.**

| Quantity | Value A | Value B | Adjudication |
| :-- | :-- | :-- | :-- |
| **Window expansion latency** | **50.7 ms** measured (30q telemetry) | "~8-12 s" (`Performance_Cost_Analysis.md:10`) | **A. Off by ~200×.** B would send you to optimise a 2% stage. |
| **Metadata join latency** | not a stage in any instrumentation | "3-5 second metadata join" (`:30`) | **A.** B is unbacked prose. |
| **P1/P2 Hit@k, Self@1, MRR** | `05_GoldP1P2_TestSuite.ipynb` outputs | `06_Gold_Test_Framework.md` | **A.** Divergence up to **60 percentage points**; the repo itself says trust the notebook. |
| **P3 answer-metric sample size** | n=31 claimed | **n=6 actual** (`11_ITest_AnsScoring.ipynb` cells 8-9) | **B.** The derived difficulty/scope tier tables *cannot have been computed*. |
| **Gold survival at top-8** | "31/31 (100%)" | **54.8% strict / 64.5% loose** | **B.** A compared `recall@30` against a ~51-sentence set. Struck through in place. |
| **Corpus size** | 203,076 / 469,252 / 407,048 / "200K" | **614,647** vectors, **614,787** meta rows | **B.** See §4b.3 — five figures for one corpus. |
| **Companies** | 4,674 | **25** embedded | 4,674 is the upstream ETL universe; corpus-scale noise claims are overstated. |
| **Open-regime search size** | "71.8M sentences" (`06_Gold_Test_Framework.md:75`) | ≤ 614,787 | **B.** A is off by ~100×. |
| **Vectors parquet size** | **2,293,538,065 B (2.29 GB)** measured | 1.56 GB / ~2.2 GB | **A.** Three sizes, one file. |
| **Stage 2 parquet size** | "500 MB – 2.3 GB" / "500MB+" | **64,781,290 B (~62 MiB)** | **B.** Measured. |
| **Per-vector footprint** | 4,210 B → 0.7962 GB (203k vectors) | 4,399 B → 2.519 GB (614,787) | Different corpora *and* different metadata assumptions. A third value (0.82 GB) at `S3Vect_QueryCost.md:167`. |
| **Total latency** | 15.8–36.8 s + one 319.9 s outlier | 9.6–14.1 s | **Both.** Different query classes; resolved in `ECS_FARGATE_RUNBOOK.md` §3.1. |
| **RAG pipeline constant** | 6.2–7.0 s (Windows, LOCAL_CACHE) | 5.17 s (Mac, 30q telemetry) | Both; different machine and corpus. |
| **"P50 / P95 / P99"** | 27.9 / 32.1 / 36.3 s | code is `observed × 1.0 / 1.15 / 1.30`, **n=1** | **Neither is a percentile.** And 27.9 is the *mean*; the median is 31.0 s. |
| **Reranker latency** | "~0.5–2 s" `[I]` | **463–479 ms** measured | **B**, and A was right in order of magnitude. |
| **Avg cost/query** | $0.017 | $0.024 | Both are real; different query mixes. Deployed single query: **$0.0140**. |
| **Cost saving vs managed vector DB** | "99%" | "60-73%" | Neither states scope. Unresolved. |
| **Q006 at top-8** | "pattern not triggering" | damaged too | **B.** All 3 `cross_company` questions degrade, not 2 of 3. |
| **ECR storage** | "~$1/month" | **$0.0643/month** measured | **B.** |
| **Index population state** | "exists and is EMPTY. Zero vectors" | 614,647 live, query-verified | **B.** A is a stale snapshot. |

> **A caution about this repository's own navigation files.** Several stale figures above are
> still live in `.claude/CLAUDE.md` and `finrag_ml_tg1/CLAUDE.md` — 203,076 vectors, "200K rows,
> 73MB", "500MB+", 4,674 companies, "30-50 seconds". Those files are read *first* by anyone (or
> any agent) starting work here, so they propagate hardest. **Flagged, deliberately not edited**
> — correcting them is its own scoped task, not a side-effect of writing this document.

---

# PART 7 — What has never been measured

Stated plainly, so nobody assumes otherwise. **NOT FOUND means searched for and absent.**

**Tooling never used**
- `psutil`, `memory_profiler`, `resource.getrusage`: **NOT FOUND** anywhere in the repo.
- Any recorded output from the `estimated_size('mb')` probes: the calls exist in tests, **no
  measured Polars MB value is committed**.
- The per-operation memory-spike table for the 300 MB / 750 MB / 1.7 GB dataset versions claimed
  at `TechNotes_MemoryExp_Handling.md:3`: **no artifact exists.**
- No tokenizer library for cost accounting (§3.1) — by design, and validated (§3.1).

**Evaluation never run**
- **BM25 / sparse / hybrid fusion: zero runs.** Considered, ranked, and deliberately
  deprioritised — correctly labelled as such rather than as "proven useless".
- **`n_hits_per_variant`** — i.e. *any* measurement of what query variants contribute. Variants
  are `enable_variants: true` in production and have run for months **with no evidence they
  help**. The 30q JSON records `variant_queries`, so this is reachable, not blocked.
- **McNemar's test** — recommended as the correct paired significance test, **never run**.
- **BERTScore and BLEURT in any 2026-07 run** — the packages are installed in none of the four
  conda environments and no BLEURT-20 checkpoint is on disk. The headline 0.826 / 0.446 figures
  **cannot be reproduced today**.
- **nDCG@k, span-level F1, numeric-answer accuracy** — never computed, and the latter two are not
  *computable* with the current label files (`answer_numeric`/`tolerance` null; `evidence_spans`
  empty in 5 of 6 files).
- **`top_n=16 + min_score=0.05`** — the one recommended combination, never run as a config.
- **Reranker p50/p95 latency** as a reported figure — self-flagged gap, though the per-call ms are
  in the 30q JSON, so it is closable from existing data.
- **MLflow-recorded latency or memory** — `LatencyMetrics` plumbing exists; no run in `mlruns/`.

**Cost and infrastructure never measured**
- **Per-stage token attribution.** Latency is broken down by stage; tokens are not.
- **Variant-generation cost** as a separate line item.
- **Query-time embedding cost** — all embedding cost figures are corpus-ingestion side.
- **An actual AWS invoice for serving.** Only Cost Explorer *token quantity* was reconciled
  (§3.2), never a dollar invoice.
- **Cold-container first-request cost** (§1.3 blind spot).
- **Cache-hit vs cold-start latency for `S3StreamingLoader`** — probe exists in tests, no output.
- **ARM vs x86 runtime performance** for this workload — only price was compared (§1.5).
- **Cross-region embedding determinism** (§2.3).
- **Cohere v3 vs v4, Titan, 768d, Matryoshka truncation** (§2.8).

**The structural limit on everything above**
- **No study here has n large enough to resolve a small quality delta.** The gold suites are 10
  and 31 questions; the minimum detectable MRR effect at n=31 is **+0.07 to +0.13**; only a swing
  of **≥6–7 questions** is distinguishable from noise. And per §4.6, **retrieval is not
  reproducible run to run**, so even the point estimates are single-draw.
- Consequence: *"a '24/31 → 27/31' improvement is not a finding."* §4.5 is what taking that
  seriously looks like in practice — and §4.1's Gate 0 bar of ≥24/31 was itself mis-specified,
  because gold is only reachable for 25/31.

---

## Scripts preserved alongside this document

| Script | Produces |
| :-- | :-- |
| `measure_container_memory.sh` | §1.1 — idle/simple/heavy peak per container |
| `measure_constructor_cost.py` | §1.2 — two-pass constructor timing + tracemalloc |
| `measure_table_load_cost.py` | §1.3 — cold vs warm table load |
| `audit_state.py` | §1.4 — AST statelessness audit, any file list |

*Compiled 2026-07-31. Part 1 measured in this session; Parts 2–4 are exact citations from the
project's own notebooks and reports, re-verified against source with `path:line` references.*
