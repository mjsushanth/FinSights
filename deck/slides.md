---
theme: seriph
# Placeholder pending prototyping (design record OPEN_QUESTIONS #3) --
# seriph vs default vs a custom build needs an actual rendered preview,
# which needs the npm install Joel has not yet confirmed in this session.
background: null
class: text-left
highlighter: shiki
lineNumbers: false
drawings:
  persist: false
transition: fade
title: FinSights -- A Financial RAG System Under a Hobbyist Budget
---

<!--
DECK STATUS: content draft only. Not yet run through `slidev build` or even
`slidev` dev mode -- this repo has no node_modules yet, pending Joel's
explicit go-ahead on the install (asked separately, not assumed from the
orchestrator's dispatch). Every number below is cited to a source file in
its own slide's presenter notes. Two numbers ($32.85/mo NAT, $0.017-0.06
Bedrock cost band) are the only ones NOT independently re-measured this
session -- both are reported from S02i / SYSTEMS_WALKTHROUGH.md, both
already carry [V] or an explicit AWS Pricing API citation in their own
source doc, and both are flagged as such in their slide's notes rather
than presented as fresh measurement.
-->

# FinSights
## A financial RAG system, priced like a hobby project

<div class="eyebrow">Sep 2025 -- Dec 2025</div>

25 companies &middot; 2006-2025 &middot; **614,647** live vectors &middot; built for **$2.21**

<!--
Title slide, exempt from the one-number rule by convention (frame, not
argument). Verified against IMPLEMENTATION_GUIDE.md:43 (1,850 vectors/min,
$2.21 total across three
bins) and the live S3 Vectors index count. Corpus is 25 companies, not the
upstream 4,674-company ETL universe -- that distinction matters and gets
its own correction elsewhere in the repo; not relitigated here.
-->

---

# The thesis

<span class="stat">$17<span class="stat-label">/month, the line that was never crossed</span></span>

One constraint -- never adopt anything costing more than this -- decided seven
architecture decisions before a single line of infra code was written.

<!--
Source: S02i P15 "A tight cost constraint removes options you did not
need," and SYSTEMS_WALKTHROUGH.md Part 0 (the thesis-in-one-sentence
framing). VERIFIED against both docs directly this session. The seven
decisions and which ones actually cost quality (2 of 7 -- scale-to-zero
cold starts, no load balancer's shifting public IP) are the material for
slide 15's close on the same theme; don't spend that here.
-->

---

# Corpus and checkpointed regeneration

<span class="stat">1,850<span class="stat-label">vectors/minute, sustained</span></span>

614,647 sentence-level vectors, three checkpointed fail-safe bins, $2.21 total.
A crash costs one bin, not the corpus.

<!--
Source: IMPLEMENTATION_GUIDE.md:43, "Sustained throughput reached ~1850
vectors per minute." VERIFIED this session. Three bins: two via Bedrock,
one via the Cohere direct API after hitting an 8.1M-token/day account
quota (documented elsewhere, not needed on this slide). Corpus is
sentence-level, not chunk-level -- 614,647 rows, not a chunked
approximation. Cost broke down as ~$1.30 Bedrock + ~$0.91 Cohere direct.
-->

---
layout: default
---

# The asymmetry bug
### The single sharpest finding in the whole project

<v-click>

The corpus is embedded with `input_type="search_document"`.

</v-click>
<v-click>

So is every user query.

</v-click>
<v-click>

<span class="stat">$0<span class="stat-label">to fix -- zero re-embedding, zero re-upload</span></span>

Cohere's dual-encoder needs the *query* tagged `search_query` -- a different,
asymmetric objective from document-to-document similarity. One config line
carried the wrong value since a refactor.

</v-click>
<v-click>

The correct value was already sitting in a deprecated config block. The
live path just wasn't reading it.

</v-click>

<!--
Source: RETRIEVAL_IMPROVEMENT_STUDY.md section 3.1, tagged [V] against
ml_config.yaml:214, query_embedder_v2.py:66, and Cohere's own API docs
(docs.cohere.com/docs/embeddings, docs.cohere.com/reference/embed).
VERIFIED this session by reading the cited lines directly. IMPORTANT
HONESTY NOTE: the source document explicitly does NOT claim a measured
retrieval-quality improvement from this fix -- "I am not claiming a
magnitude... it must be A/B'd." A follow-up doc (EMBEDDING_INPUT_TYPE_
ASYMMETRY.md) shows the fix was implemented (48/48 config resolutions
unchanged in an A/B against pre-edit YAML) but the retrieval-quality A/B
had not landed as of that doc's writing. Do NOT let a magnitude claim
creep onto this slide face -- the honest story is "found a real bug via
code trace + external docs, fixed at zero cost," not "improved X%."
The fourth click's reveal: ml_config.yaml:214 sets the live corpus block
to search_document, query_embedder_v2.py:66 reads that same value for the
query (the bug). But ml_config.yaml:272, inside the deprecated
rag_orchestrator block that the live path never reads, already has the
correct search_query. V1 (query_embedder.py:44) also defaulted correctly
-- V2 regressed it in a config refactor. The right answer was in the
repo the whole time, just in a block nothing was reading.
-->

---

# What retrieval actually does

![FinSights retrieval architecture](./img/architecture.svg)

Five S3 Vectors calls per question. One filtered path, one global fallback,
three semantic variants. Metadata prefilters do the heavy lifting.

<!--
The one system diagram in the deck (design record: max 3 total, only this
slide gets one). Diagram built via the diagram-design skill, profile
"finsights" (blended palette, see ~/.diagram-design/profiles/finsights.md
for the derivation). Five calls verified: RETRIEVAL_IMPROVEMENT_STUDY.md
1.2 -- base filtered (topK=30), base global (topK=15), then 3 variant-
filtered calls (topK=15 each), all serial. The diagram compresses this to
5 conceptual stages (Query Understanding / Retrieval Control / Context
Assembly / LLM Synthesis / Serving) -- cross-checked against Joel's own
full architecture reference diagram mid-session and confirmed as a
faithful compression of that diagram's "LLM Serving" row specifically,
not an invented abstraction.
-->

---

# Boilerplate crowding is the dominant measured problem

<span class="stat">44.9%<span class="stat-label">exact-duplicate text rate across the corpus</span></span>

The same sentence, repeated verbatim across filing years by the same company --
not cross-company leakage. One sentence alone recurred 424 times.

<!--
Source: RETRIEVAL_IMPROVEMENT_STUDY.md 2.1, tagged [V], measured directly
against finrag_fact_sentences.parquet (614,787 rows): 338,869 unique
texts, only 827 distinct texts appearing cross-company (2.1% of
duplicates). Root cause traced to code: sentence_expander.py:517's dedup
key is (sentence_id, cik_int, report_year, section_name) -- purely
identity-based, never compares sentence text, so the same verbatim
sentence in FY2016 and FY2017 survives twice and consumes two of 30
retrieval slots. Companion stat in the 25 real exported contexts: mean
near-duplicate rate 22.7% of context, median 100 sentences per context.
-->

---

# The score distribution is flat -- this is the reranking argument

<span class="stat">0.063<span class="stat-label">-wide similarity band across the top 45 candidates</span></span>

[0.674, 0.737]. Zero rejections at any threshold from 0.0 to 0.5. No
long tail to filter -- cosine carries almost no ordering information here.

<!--
Source: RETRIEVAL_IMPROVEMENT_STUDY.md 2.4, quoting 08_RAGArch_
DesignNotes.ipynb cell 17 verbatim, tagged [V]. "All thresholds (0.0 to
0.5): 45 hits, NO rejections... no long tail of weak matches to filter
out AT ALL." This is presented in the source as the single strongest
piece of evidence for trying a cross-encoder -- only a model that reads
query and candidate jointly can extract signal a flat band this narrow
does not carry. Sets up slide 10's reranking story directly.
-->

---

# Wrong-year context, and it is deterministic

<span class="stat">35%<span class="stat-label">of exported queries entirely missing the asked year</span></span>

8 of 23 real exports never contained the fiscal year the question asked
about. One 3-company export gave Netflix zero context, three times running.

<!--
Source: RETRIEVAL_IMPROVEMENT_STUDY.md 2.6 and 2.7, both [V]. 2.6: checked
all 23 response exports against "| FY nnnn |" headers actually present;
8/23 (35%) missing the asked year entirely, years present in every context
only 2016-2020 (partly old-corpus coverage at the time, but the code-level
cause -- the global filter's year handling, bug 3.2 -- survives the
revival). 2.7: cik_int $in filter + single global topK means ANN returns
the 30 globally-best hits regardless of company -- a company whose
sentences sit slightly further from the query gets nothing. Netflix: 0
context in 3/3 runs. Only 3 of 31 gold questions are cross_company, so
this affects 100% of the multi-company gold set that exists. "Deterministic"
is the word worth keeping -- this is a structural gap, not noisy variance.
-->

---
layout: default
---

# The latency reversal

<v-click>

**Documented claim:** S3 Vectors retrieval is ~90% of pipeline time.

</v-click>
<v-click>

**Measured:** variant generation, <span class="stat" style="display:inline">1,990ms</span> median --
larger than the S3 query itself, <span class="stat" style="display:inline">1,465ms</span>.

</v-click>
<v-click>

The 90% figure was real. The attribution was wrong.

</v-click>

<!--
Source: TIER1_PROGRESS_LOG.md, Step 0 (2026-08-01), directly verified this
session in an earlier deck iteration. The retrieve timer wraps BOTH
variant generation (1 Haiku call + 3 embedding calls) AND the actual S3
Vectors queries as one block -- the 90% figure for the whole block was
correct, but attributing all of it to "S3 Vectors" specifically was not.
This is the finding that motivated splitting the timer into variant_gen_ms
and s3_query_ms as two separate fields, additive, not replacing the
original `retrieve` key.
-->

---
layout: default
---

# The reranking rejection

<v-click>

**Won on three metrics:** cross-encoder reranking at top-8 cut cost
<span class="stat" style="display:inline">32%</span>, cut context 61%, and
had the best ROUGE-L of any configuration tested.

</v-click>
<v-click>

**Rejected anyway:** answers got worse on 5 of 10 held-out questions.

</v-click>
<v-click>

Mechanism: the cross-encoder is blind to fiscal year. Off-year context rose
from <span class="stat" style="display:inline">31.3%</span> of the pool to
<span class="stat" style="display:inline">47.4%</span> of what survived pruning.

</v-click>

<!--
CORRECTED 2026-09-11 after a peer session's independent verification pass
caught a real error in an earlier draft: this slide previously paired
"45.2% vs 31.3%" as one comparison. Those numbers come from DIFFERENT
populations and must not be paired -- RERANKING_FINAL_SYNTHESIS.md
distinguishes 45.2% (top-8, ALL 31 questions) vs 31.5% (overall pool base)
from 47.4% (top-8, the 24 single-company/single-year "local" questions
only) vs 31.3% (local-only pool base). This slide now uses the internally
consistent local pair (47.4% vs 31.3%), independently re-verified by me
directly against RERANKING_FINAL_SYNTHESIS.md before applying the fix,
not taken on the peer's word alone.
Also corrected: the rejection was NOT primarily about wrong-year context.
Source, verbatim: "That 'top-8 is not fit to ship' follows from
5-worse-of-10." The off-year concentration is the MECHANISM/supporting
evidence for why reranking makes answers worse, not the primary reason
itself. Benefit side, also corrected upward: 61% median context reduction
and best ROUGE-L, not just the 32% cost cut this slide previously led with
alone. Mechanism detail: off-target-year blocks score higher (mean 0.300
vs 0.219) and are longer (5.49 vs 4.04 sentences) than on-year blocks --
the cross-encoder scores text quality, and report_year is never in its
input, so it structurally cannot tell a well-written wrong-year passage
from a well-written right-year one.
All figures: RERANKING_FINAL_SYNTHESIS.md, cross-referenced against
IMPLEMENTATION_GUIDE.md:420 (local-pair figures) and :425
(enable_reranking: false, confirming the rejection shipped as a real
config state, not just a recommendation).
-->

---

# Measurement as a design practice

<span class="stat">3<span class="stat-label">times my own measurement tooling was the broken thing</span></span>

A grep pattern that could never match. An exit code read from the wrong
command. A Pricing API query with the wrong usage-type prefix.

<!--
Source: S02h - Measurement as a Design Practice.md, section 8, all three
VERIFIED directly this session. (1) `grep -qiE "...IAM_ROLE..."` against a
log that actually printed "IAM role" (space, lowercase) -- waited 5
minutes on a condition that could never become true, after the query had
already succeeded. (2) Reported "exit code 0" that was actually the exit
code of a `tail` at the end of a pipe, not the real command. (3) A Fargate
Pricing API query returned nothing because usage types carry a region
prefix (USE1-Fargate-ARM-vCPU-Hours:perCPU) -- once fixed, real rates came
back exactly ($0.032380/vCPU-hr ARM64, matching this deck's own slide 14).
The lesson stated directly in the source: "my tool returned nothing" and
"the data does not exist" are different conclusions, and conflating them
produces a confident gap.
-->

---

# Perceived latency, fixed without touching real latency

<span class="stat">4.3ms<span class="stat-label">time to first byte, against 8.96s total processing</span></span>

A `queue.Queue` plus a background thread streams pipeline-stage events and
token output to the browser. Total time is unchanged. What changed is the wait.

<!--
Source: TIER1_PROGRESS_LOG.md Change 4b (2026-08-01), VERIFIED via a real
Docker rebuild + browser test this session (see vault C10 for the full
mechanism writeup: answer_query_stream(), a worker thread pushing events
into a queue, drained by a generator, re-emitted as SSE). Honest limit
carried in slide 15's notes, not repeated here per the no-open-gaps-slide
instruction: this was verified locally and in Docker, not against the
live deployed Fargate service specifically.
-->

---

# The concurrency model is a consequence, not a choice

<span class="stat">1<span class="stat-label">genuinely shared mutable thing, found by audit</span></span>

`answer_query` is blocking and I/O-heavy -- that alone decided threadpool over
event loop. boto3 clients are safe to share; Sessions are not. One
lazy-table memo was the real hazard.

<!--
Source: S02g - Concurrency and Shared State.md, VERIFIED this session.
"Is boto3 thread-safe" has three answers in the source's own words:
Client generally yes (safe to share, not across processes), Resource no
(one per thread), Session no (one per thread/process) -- straight from
boto3's own docs, not recalled from memory. The one genuinely shared
mutable object found by AST audit: the DataLoader's lazy table memo.
Also: AwsSession's own client-cache factory has a latent (harmless today,
single-threaded by construction) race on first use of a new service --
documented rather than silently living with it. P16: "the shape of the
work chooses [the concurrency model], and then you accept the
consequences" -- not a taste decision.
-->

---

# Fargate bills per task, and that fact drives everything

<span class="stat">1,220 MiB<span class="stat-label">measured peak -> sized at 1 vCPU / 3072 MiB</span></span>

Fargate charges per task, on the reserved shape, not per container and not on
actual usage. One image, two containers, ARM64 -- 20% cheaper than x86_64.

<!--
Source: SYSTEMS_WALKTHROUGH.md 3.1 and 3.2, VERIFIED against the AWS
Pricing API this session (region prefix fixed, per S02h 8.3 above):
$0.032380/vCPU-hr and $0.003560/GB-hr on ARM64, both ~20% below x86_64.
Units corrected 2026-09-11 per peer verification: source states 1,220 MiB
(10-company query) and 1,139 MiB (simple query) as the two measured
peaks, ECS_FARGATE_RUNBOOK.md:169-170; task shape is 1 vCPU / 3072 MiB,
split 2560/384 as soft reservations, :180. MiB and 3072 read as measured;
"1.22 GiB / 3 GiB" was a rounding that undersold the point of the slide.
Sizing rationale unchanged: 1,220 MiB was the worst measured peak; 2048
MiB would leave under 900 MiB headroom, so 3072 MiB (the next valid
Fargate memory tier at 1 vCPU) was chosen for ~2.5x headroom without
paying for a second vCPU. "One image, not two" (Part 2.2): a second CONTAINER
inside the same task is nearly free; a second TASK doubles the bill --
the entire reason the backend and frontend share one task rather than
being split into two services.
-->

---

# The control plane is software, and the reverse operation proves it

<span class="stat">$0.2938<span class="stat-label">/month, everything scaled to zero</span></span>

`destroy` then `up` reached the same steady state from the repository alone.
That is the completeness test -- not a disaster-recovery drill.

<!--
Source: SYSTEMS_WALKTHROUGH.md Part 7.1 (control plane as a Python
package CI calls, not reimplements) and S02i P5 (the reverse-operation
completeness test), both read directly this session. $0.2938/month idle
floor VERIFIED this session directly against Cost Explorer, swept against
every classic silent-billing resource (NAT gateway, ALB, Elastic IP, EBS,
Route 53, Secrets Manager, KMS, Glue) -- none exist. Companion figure, NOT
independently re-measured by me this session (reported from SYSTEMS_
WALKTHROUGH.md 3.4 / S02i P15, both citing the same source): the ~$32.85
/month a NAT gateway would have cost, deliberately never adopted, in favor
of public subnets since the workload needs egress, not inbound privacy.
December's prior deployment looked healthy right up until the account
closed -- the destroy/rebuild test is what would have caught that
class of failure, not a stronger monitoring dashboard.
-->

---
layout: default
class: text-left
---

# What generalises

<v-click>Prefer unrepresentable to unlikely.</v-click>
<v-click>Trust the artifact over the description.</v-click>
<v-click>Label provenance on every number -- an unlabelled one is a liability.</v-click>
<v-click>A tight cost constraint removes options you did not need.</v-click>
<v-click>Negative results, reached honestly, are still results.</v-click>

<!--
Distilled from S02i - Higher-Level Design Principles from a Real
Deployment.md (19 numbered principles in 5 groups), specifically P1, P18,
P13, P15, P14 -- each already carries its own verified anchor earlier in
this deck (slide 4 for P18-adjacent artifact-trust reasoning, slide 2/15
for P15, slide 10 for P14, this deck's whole citation discipline for
P13). No "thank you" slide, per the design record. This is the close.
-->
