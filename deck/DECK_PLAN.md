# DECK PLAN — FinSights Walkthrough Deck (16 slides, Slidev)

Design record, rev 2. Orchestrator (Opus) decides shape; worker (Sonnet E0) implements.
Rev 1 chose Marp and 20 slides. Both reversed by Joel. Reasoning for the reversal is
recorded in section 1 because the *error* is the useful part.

## 1. Tool decision: Slidev — and why rev 1 was wrong

Rev 1 argued Marp, on the grounds that Slidev's differentiator is live Vue
components and "this deck is prose, numbers and static SVG — it does not use them."

That argument contained a hidden premise: **that the content was fixed and the deck
was merely a transport for facts.** Joel falsified it. Presentation quality is
itself a deliverable here — the deck is a product-presentation capability being
built once and reused three times, not a one-off slide dump. Under that goal,
components, motion, incremental reveals and deliberate styling are not unused
overhead; they are the thing being bought.

This is the same failure mode the deck itself is about (see S02i P18, "trust the
artifact over the description"): I optimised against a stated artifact spec
instead of the actual objective. Worth keeping visible.

Decision: **Slidev, fully.** Accept the Node project, accept the build pipeline,
accept the Actions workflow. Verified surface (context7, /websites/sli_dev):

| Need | Mechanism |
| :-- | :-- |
| Incremental reveal | `v-click`, `v-click="[2, 4]"` for enter/exit ranges |
| Motion | `v-motion` with `:initial` / `:enter` / `:leave` |
| Custom components | drop `.vue` into `components/`, auto-registered |
| Per-slide transitions | scoped CSS on `.slidev-page-N` / custom layout classes |
| Build | `slidev build --base /FinSights/ -o dist` |
| Hosting | official Actions workflow, `configure-pages` with `enablement: true` |

Note the official workflow enables Pages itself — no settings click needed. That
makes it *easier*, not more authorised. See OPEN_QUESTIONS.

## 2. Slide count and weighting — 16, reweighted

Joel's direction: compress data engineering, drop open gaps, add the
architecture/design-paradigm material, no forced Mastercard content.

| Act | Rev 1 | Rev 2 |
| :-- | --: | --: |
| Frame | 3 | 2 |
| Data engineering | 4 | **2** |
| Retrieval | 4 | **4** |
| Reversals / epistemics | 4 | **3** |
| Serving + streaming + infra paradigms | 3 | **4** |
| Open gaps | 2 | **0** |
| Close | 1 | 1 |

## 3. Source documents — the material rev 1 was missing

Rev 1 worked only from E0's handoff summary. The repo holds far more, and this is
where the "high-level system / architecture / software design paradigms" live.
Repo root: `MJS_ROOT/MJS_STUDY/NEU Sem5 - MLOPS/MLOps Project/FinSights`

| Document | What it supplies |
| :-- | :-- |
| `study_notes/S02i - Higher-Level Design Principles from a Real Deployment.md` | **19 numbered principles in 5 groups.** The paradigm spine. |
| `study_notes/S02g - Concurrency and Shared State...md` | Threadpool/boto3 thread-safety audit; the shared memo |
| `study_notes/S02h - Measurement as a Design Practice.md` | 6 measurement methods; "three times my own measurement was broken" |
| `investigation_analysis/RETRIEVAL_IMPROVEMENT_STUDY.md` | Boilerplate crowding, flat scores, wrong-year 35%, **three bugs** |
| `investigation_analysis/retrieval_telemetry_and_reranking_design.md` | Telemetry HLD/LLD, gold-set verification, rerank insertion |
| `finrag_docker_loc_tg1_aws/SYSTEMS_WALKTHROUGH.md` | Packaging/placement/wiring/identity/lifecycle; control plane as software |
| `finrag_ml_tg1/IMPLEMENTATION_GUIDE.md` | Corpus + regeneration numbers |
| `finrag_ml_tg1/LLMOPS_TECHNICAL_COMPLIANCE.md` | Standards, test suites |
| Vault `C10` | SSE query-bridge pattern, TTFB numbers |

Selected principles from S02i that carry slides:
P1 prefer unrepresentable to unlikely · P5 the reverse operation is the
completeness test · P10 compare your effect against the system's own noise floor ·
P11 pre-register the decision rule · P13 label provenance on every number ·
P14 negative and null results are results · P15 a tight cost constraint removes
options you did not need · P16 the concurrency model is a consequence of the work ·
P18 trust the artifact over the description

## 4. The slide contract — unchanged, it is the reusable asset

- One claim per slide, phrased as a **sentence**, not a noun phrase.
- Exactly **one measured number** per slide — measured, never modelled.
- Slide face <= 40 words. Depth goes in presenter notes.
- Animation must **carry the argument**, not decorate it: use `v-click` to stage a
  reveal where the sequence *is* the point (claim -> measurement -> reversal).
  A reveal that only delays text is noise.
- **Every slide carries a diagram** unless there is genuinely no fit. See section 7.

## 5. The 16 slides

### Act I — Frame (1-2)
1. **Title.** 25 companies, 2006-2025, 614,647 live vectors, built for $2.21.
2. **The thesis.** A tight cost constraint removed options I did not need (S02i
   P15; `SYSTEMS_WALKTHROUGH.md` Part 0). Frames every later decision.

### Act II — Data and embedding consistency (3-4)
3. **Corpus and checkpointed regeneration.** Sentence-level, 614,647 rows, three
   fail-safe bins at ~1,850 vectors/min for $2.21. A crash costs one bin.
4. **The asymmetry bug — strongest data slide in the deck.** The query was being
   embedded as a *document* against a corpus embedded as documents; input-type
   asymmetry, identified as a bug and free to fix
   (`RETRIEVAL_IMPROVEMENT_STUDY.md` 3.1). This is the embedding-API-consistency
   story, and it is a subtle bug most people never find. `v-click` staging.

### Act III — Retrieval (5-8)
5. **What retrieval actually does.** Five S3 Vectors calls, metadata prefilter,
   variant subsystem. The one system diagram.
6. **Boilerplate crowding is the dominant measured problem** — measured, not
   theorised (`RETRIEVAL_IMPROVEMENT_STUDY.md` 2.1).
7. **The score distribution is flat, and that IS the reranking argument** (2.4).
   Shows the intervention was derived from evidence, not fashion.
8. **Wrong-year context at 35% of exported queries, and deterministic
   multi-company starvation** (2.6, 2.7). "Deterministic" is the sharp word.

### Act IV — Reversals and epistemics (9-11)
9. **Latency reversal.** Documented claim: S3 retrieval ~90% of pipeline. Measured:
   variant generation 1,990ms median > S3 query 1,465ms. `v-click`: claim, then
   measurement, then reversal.
10. **The reranking rejection.** Real 32% cost cut at top-8, rejected because 45.2%
    of surviving context came from the wrong fiscal year vs a 31.3% base rate.
    Pre-registered decision rule (P11); negative results are results (P14).
11. **Measurement as a design practice.** Six methods, and three times my own
    measurement was the broken thing (S02h 8). Noise floor (P10), provenance
    labels (P13).

### Act V — Serving, streaming, infra paradigms (12-15)
12. **The SSE query-bridge.** `queue.Queue` + background thread; TTFB 4.3ms against
    8.96s total processing. Perceived latency fixed without touching real latency.
13. **The concurrency model is a consequence of the work, not a free choice**
    (P16 + S02g). You have concurrency even when you think you don't; boto3
    thread-safety has three answers; the genuinely shared mutable memo is the point.
14. **Fargate bills per task, and that one fact drives the architecture**
    (`SYSTEMS_WALKTHROUGH.md` 3.1). Sizing from measurement: 1.22 GiB peak ->
    1 vCPU / 3 GiB, ARM64, one image not two.
15. **The control plane is software, not a YAML workflow** (Part 7.1), and the
    reverse operation is the completeness test (P5) — teardown proves the build
    was understood. $0.2938/month idle floor; the $32.85 that never got spent.

### Act VI — Close (16)
16. **The principles that generalise.** Four or five lines distilled from S02i,
    staged with `v-click`. No "thank you" slide.

Mastercard content: **excluded.** Not forced in. If the ongoing investigation
yields something genuinely sharp it can replace a weaker slide later, on merit.

Open-gaps slide: **removed** per instruction. Noted once and not relitigated —
a deck without a gaps slide leaves the gaps for a reviewer to find, which was
rev 1's rationale. Joel's call; it stands.

## 6. Repeatability across 3 projects

The reusable assets, in order of value:
1. **The six-act narrative skeleton** — Frame / Data / Retrieval-or-core /
   Reversals / Serving / Principles.
2. **The slide contract** in section 4.
3. The Slidev project itself: theme + `components/` + the Actions workflow, copied.

The hard input is never the tool — it is having real reversals per project. A
project without them gets a shorter deck, not invented ones.

## AUTHORIZATION (resolved 2026-09-11, direct from Joel)

Full authorization granted to both orchestrator and worker, and the orchestrator may
accept authorizations relayed by the peer session: installs, measurement, redo,
clear/delete/rewrite within the Slidev work, git commits, push, deploy tests, npm
builds. The rev-2 OPEN_QUESTIONS 1 and 2 (Pages publishing, commits) are CLOSED.

Retained floor, narrow and by orchestrator judgment only: nothing destructive outside
the FinSights repo and the `deck/` scope.

## REMAINING OPEN ITEM

1. **Theme.** `seriph` vs `default` vs custom — E0 prototypes and reports. Deliberately
   not decided blind.

## DIVISION OF WORK

- **E0 (worker):** Slidev project, install, theme prototype, build, commit, push,
  Pages deploy test, size reporting.
- **Orchestrator:** verification of every factual claim in section 5 against its
  source document, delivered as a table of VERIFIED values with file:line citations.
  Taken off E0's plate to avoid collision and because the spine's numbers are the
  highest-risk surface in the deck.


## 7. Diagram augmentation — every slide, rev 3

Rev 2 capped the deck at 3 diagrams. **That cap is removed.** Joel's direction:
every slide gets its own diagram from the `diagram-design` plugin, chosen
deliberately from the full span available, and a slide goes without one only when
there is genuinely no fit.

The cap was the wrong instinct for the same reason the Marp choice was wrong — I
kept treating presentation as a transport for facts rather than as the deliverable.

**The worker must reason about each choice independently.** The table below is a
proposal, not an assignment. For every slide E0 either justifies the proposed type
against the alternatives or overrides it with a better one and says why. A diagram
that merely decorates the claim is worse than none; the diagram has to carry
something the sentence cannot.

Available span includes: architecture, deployment, sequence, flowchart, state
machine, ER/data model, timeline, swimlane, quadrant, radar/spider, polar, loop/
flywheel, nested, tree, org chart, layer stack, Venn, pyramid/funnel, treemap, bar,
waterfall, line, Gantt, scatter, high-level, process, medallion, data flow, DP
integration, DP security matrix, Sankey, fishbone, Wardley map, kanban, user
journey, dependency graph, UML class, story map, database schema.

| # | Slide | Proposed type | Why this type earns its place |
| --: | :-- | :-- | :-- |
| 1 | Title | **timeline** | The 2006-2025 corpus span is the one fact a title slide can show rather than assert |
| 2 | Cost constraint removes options | **quadrant** | Plots the options the constraint eliminated; shows they were never needed |
| 3 | Corpus + checkpointed regeneration | **Gantt** or **process** | Three sequential bins with checkpoint boundaries is literally a schedule |
| 4 | Query embedded as a document | **sequence** or **data flow** | Two lanes, corpus and query, converging on one mismatched `input_type`. The mismatch is spatial, so show it |
| 5 | What retrieval actually does | **architecture** / **data flow** | The five S3 Vectors calls and the metadata prefilter |
| 6 | Boilerplate crowding | **treemap** | Crowding is an area problem. A treemap makes share-of-context visceral |
| 7 | Flat score distribution | **line** | Flatness only reads as flat when drawn. This is the reranking argument |
| 8 | Wrong-year + multi-company starvation | **Sankey** | 35% of intent flowing into the wrong year is a flow-loss picture |
| 9 | Latency reversal | **waterfall** | Per-stage latency IS a waterfall; variant_gen overtaking s3_query is the whole point |
| 10 | Reranking rejection | **radar/spider** | Won on cost, context and ROUGE-L, lost on answer quality and off-year. Multi-axis win/lose is exactly radar's job |
| 11 | Measurement as a design practice | **fishbone** | Three times the measurement itself was the broken thing — causal, not sequential |
| 12 | SSE query-bridge | **sequence** | Browser, endpoint, `queue.Queue`, background thread, token stream. Ordered interaction |
| 13 | Concurrency as a consequence | **swimlane** | Threads are lanes; the shared memo is the one crossing point |
| 14 | Fargate bills per task | **deployment** | Task, container, ARM64, 3072 MiB. The named type for exactly this |
| 15 | Control plane as software | **state machine** | up / down / destroy / rebuild, and P5 — the reverse edge proves completeness |
| 16 | Principles that generalise | **layer stack** or **pyramid** | Five principle groups from S02i, stacked |

All 16 have a real fit, so no slide should ship bare. If E0 concludes one truly has
none, it says so explicitly with reasoning rather than forcing a shape.

Constraint that still binds: the diagram serves the single claim. Do not let a rich
diagram smuggle a second argument onto the slide — that is how a 16-slide deck
becomes an architecture dump, which is the thing Joel explicitly does not want.

## 8. The voice pass — final stage, after drafts settle

Once first and second drafts are structurally done and the numbers are correct,
the prose goes through the `write-like-joel` skill at
`/Users/joel/.claude/skills/write-like-joel/SKILL.md`, including
`references/voice-profile.md`.

Ordering matters and is not negotiable: **structure, then numbers, then voice.**
Voice last, because the skill's own evidence-aware review checks truth first and
will otherwise be auditing figures we already know are wrong. Running it early
means running it twice.

Mode is **Revise**, not Draft — the content exists and the facts must survive
unchanged. The skill is explicit that factual claims, ownership wording, and
technical terms are preserved. Slide faces are short prose, so its warnings apply
directly: do not add ceremonial conclusions, do not turn each slide into
claim-plus-three-examples-plus-recap, do not reach for elevated synonyms, and do
not strip legitimate constructions because they look like AI tells. Presenter notes
are the longer prose and benefit most.

## 9. Iteration protocol

This refines by rounds, not in one pass.

1. E0 drafts or revises, then reports what changed and what it is unsure about.
2. Orchestrator reviews against: numbers verified at source, one claim per slide,
   diagram earning its place, animation carrying the argument.
3. Corrections go back with reasoning, not just verdicts.
4. Repeat until structure and numbers are settled.
5. Voice pass (section 8).
6. Build, commit, push, Pages deploy test.

E0 reports upward rather than waiting to be asked. Anything it cannot verify at
source gets flagged, never smoothed over.
