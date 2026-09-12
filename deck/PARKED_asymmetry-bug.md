<!--
PARKED 2026-09-11, moved out of slides.md entirely (not just to the end of
the sequence) per the orchestrator's final ruling: "remove the parked
asymmetry slide from the live sequence entirely. It should not appear as
a trailing 16th... Joel will rework it with me when he's back."

Original context: parked 2026-09-11 per Joel's direct review of the live
deck: "its broken for me... the diagram also seems broken and I DONT KNOW
exactly what youre trying to show here. ignore this. discard this or push
it to last page to fix for later." This was originally slide 4, "The
asymmetry bug," picked as the orchestrator's "sharpest finding" -- itself
an instance of the same framing error the whole deck revision corrected:
a config bug found during development is a process/tooling story, not a
project achievement, and doesn't belong in a deck about what the system
does and delivers.

Kept below verbatim (content, diagrams, and citations unchanged) so
nothing sourced is lost, in case a future revision finds a real use for
it. The two referenced diagrams (asymmetry-flow-current.svg,
asymmetry-flow-fix.svg) remain on disk in deck/img/, unreferenced by
slides.md as of this move.
-->

# Embedding input-type asymmetry — found and fixed at zero cost
### Found by reading the live config against Cohere's own docs

<v-click>

The corpus is embedded with `input_type="search_document"`.

So is every user query.


</v-click>
<v-click>

<span class="stat">$0<span class="stat-label">to fix — zero re-embedding, zero re-upload</span></span>

Cohere's dual-encoder needs the query tagged `search_query`, not `search_document`.

</v-click>
<v-click>

The correct value was already sitting in a deprecated config block. The
live path just wasn't reading it.


</v-click>

<div class="fig-swap" v-click="[1,3]">

![Two paths converging on the same wrong value](./img/asymmetry-flow-current.svg)

</div>
<div class="fig-swap" v-click="3">

![The correct value already existed in a deprecated block](./img/asymmetry-flow-fix.svg)

</div>

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
