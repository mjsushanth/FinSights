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
- Slide face word budget: **<= 40 words for a single-claim slide, <= 120 for a
  two-column slide** with bullets left and a figure right. The 40-word rule was written
  for the single-claim layout and is obsolete for the two-column pattern Joel asked for
  ("2-3 bullets", "the LEFT SPACE 70% of it should have some good talk"). Measured
  against live slides: ~110 words fits comfortably, 138 fits but with no slack at the
  bottom edge. Treat >130 as at risk of overflow.
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

## 8b. Precedence — THIS DOC IS CANONICAL

**`deck/DECK_PLAN.md` is the single source of truth. Cross-session messages are
notifications, not the record.** When a message and this document disagree, **the
document wins.** No timestamp forensics required.

The orchestrator writes this doc *last*, after any message on the same decision, so
its state is by definition the latest ruling. An instruction sent by message but not
yet reflected here is **provisional** and must be flagged as such rather than built on.

Why this exists: the six-bone / five-bone fishbone conflict (see section 13). The
orchestrator issued an instruction, refined it after seeing the build, and wrote the
doc in parallel with messaging. Two channels carrying the same decision at different
times is how a worker builds the wrong thing with full confidence. The worker caught
it by comparing file mtimes and held off committing, which was correct — but it should
never have needed to.

## 8c. File ownership handoff — one direction only

**Whoever hands off a file does not touch it again without announcing a re-lock.**

The orchestrator unlocked `slides.md` ("rebuild, verify, commit"), the worker began its
diff-and-verify pass, and the orchestrator then applied an eighth edit and called the
file "final and yours." The worker committed having diffed only the first seven. The
content happened to be correct and independently re-verified afterwards, but it was
committed unreviewed.

Root cause is the **handoff, not the commit discipline.** The worker's proposed fix —
diff immediately before commit — is sound defense and worth keeping, but it treats the
symptom. The orchestrator mutated a file after transferring ownership of it.

This is the second instance of one pattern, the first being the doc-versus-message
precedence conflict in section 8b: shared state modified while the other party was
acting on its earlier view of it. Both were the orchestrator's doing, and both were
caught by the worker rather than by the party that caused them.

Rules, and they bind the orchestrator hardest because it has been the one breaking them:

1. Unlocking a file is final. To edit again, announce a re-lock and wait for
   acknowledgement before touching it.
2. A late correction after unlock goes to the owner **as a request**, not as an edit.
3. Diff immediately before `git add`, with nothing in between.

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

## 10. Diagram ruling, rev 4 — final assignment

Worker challenged the section 7 proposal type by type rather than accepting it.
Outcome: 3 orchestrator picks overturned, 2 slides argued bare and accepted,
4 resolved to a third shape neither side first proposed. **14 of 16 carry a diagram.**

| # | Final type | Resolution |
| --: | :-- | :-- |
| 1 | *(none)* | Bare, accepted. A timeline needs positioned events; one unbroken span is text |
| 2 | **matrix** (7 x 2) | Refined. Quadrant invents an axis; a binary bar chart is a list. The punchline is a column of uniform "No" |
| 3 | **process** | Worker override accepted. Gantt bars cannot be sized without per-bin durations — inventing proportions is fabrication |
| 4 | **data flow** | Worker override accepted. Two static paths, no time-ordered messages |
| 5 | architecture | Confirmed |
| 6 | treemap | Confirmed — 338,869 unique texts vs duplicate remainder |
| 7 | **box/range on full 0-1 axis** | Refined twice. Bars bury the clustering claim; a dot plot/beeswarm would imply 45 observations from 4 summary stats. Box is the honest encoding for min/median/mean/max |
| 8 | Sankey, year-coverage only | Confirmed with scoping. Multi-company starvation stays in notes — second claim |
| 9 | **waterfall if the full stage split exists, else bar** | Conditional. A whole-pipeline budget has a real cumulative total; two durations do not |
| 10 | radar | Confirmed. Every axis carries a real number |
| 11 | **fishbone, head = "a number you can trust", 6 bones = the S02h methods** | Refined. 3 incidents would leave it sparse; they become callouts on the bones |
| 12 | sequence | Confirmed — cleanest fit in the deck |
| 13 | **layer stack** | Worker override accepted. Swimlane implies handoff; nothing is handed off |
| 14 | deployment | Confirmed |
| 15 | state machine | Confirmed. P5's reverse-operation test is literally "does a transition back exist" |
| 16 | *(none)* | Bare, accepted. Layer stack would impose hierarchy on five peer groups — dishonest, not just suboptimal |

Spread: seven chart-like, seven structural, minimal repetition. Answers the
monotony risk raised in section 9.

Standing rule reaffirmed both times it came up: a figure needing a number that
cannot be sourced does not get estimated. Same discipline as the prose.

## 11. Blocked

**GitHub Pages is not enabled.** Build succeeds end to end; `configure-pages`
fails because creating a Pages *site* needs repo-admin privilege the default
`GITHUB_TOKEN` never receives at any permission level. Repo
`default_workflow_permissions` is already `write`, so that is not the cause and no
workflow-file edit fixes it. Orchestrator attempt via `gh api` was blocked by the
session permission classifier; not routed around, and not delegated to the worker.

Needs one of: Joel flips Settings -> Pages -> Source: GitHub Actions, or Joel
approves `gh api -X POST repos/mjsushanth/FinSights/pages -f build_type=workflow`.
One-time either way; the existing workflow then deploys on every push.


## 12. Staging — animation that carries the argument

Three diagrams render in two states via `v-click`, one figure each rather than two images:

- **Slide 4** — both paths converging on `search_document` as wired, then where the
  query path should diverge to `search_query`.
- **Slide 9** — the documented ~90% assumption, then the measured split beside it.
  The assumption bar must be **ghosted and labelled as a claim**: nobody measured it,
  and a slide about an unchecked assumption must not itself assert an unobserved number.
- **Slide 10** — the three won axes light first (cost, context, ROUGE-L), then the two
  lost ones (answer quality, off-year). The tension arrives in the argument's own order.

Slides 12 and 15 stay static. Sequence and state-machine diagrams already carry their
ordering inherently; inventing a reveal there would be decoration.

Rejected: dot plot / beeswarm for slide 7 — see the row in section 10. Same failure
class as the refused Gantt: an encoding implying data that cannot be sourced.

Bar-family count across the final set: **one** (slide 9, and only if the full stage
split is unavailable). The monotony risk is closed.

## 13. Deviation ruling, rev 6 — and a propagated error caught

Worker built all 14 diagrams and disclosed four deviations from spec in the relevant
presenter notes. Ruling:

| Deviation | Ruling |
| :-- | :-- |
| Slide 2 matrix: 1 column, not 2 | **Accepted.** An "eliminated by cost" column is constant-true by construction; a constant column carries no information. The uniform "No" column was always the argument |
| Slide 8 Sankey: 2 stages, not 3 | **Accepted.** 23 -> 15/8 has no natural middle stage; inventing one is the Gantt error again |
| Slide 11 fishbone: 4 bones, not 6 | **Refined to 5.** Cold-vs-warm folding into one-time-vs-per-call is a real same-concern merge. But "measure the artifact, not the description" is restored — it is the most distinctive idea in S02h and it is also P18 |
| Slide 10 radar: 5 metrics normalized to 0-10 | **Rejected as built.** See below |

### The radar error — orchestrator's, not the worker's

The built radar lights ROUGE-L as one of three "won" axes. But the source disclaims it:

- `EMPIRICAL_METHODS_AND_FINDINGS.md:860` — "a ROUGE-L delta of 0.011 sits inside the
  noise of a 10-question sample"
- `S02i:276` — same finding, stated again

Normalizing 0.101 vs 0.112 to a 0-10 axis renders a within-noise delta as a visible
advantage. **S02i P10 is "compare your effect against the system's own noise floor,"**
and P10 is material in this deck — so the figure contradicted the deck's most
distinctive idea using the deck's own numbers.

Root cause: the orchestrator's slide-10 reframe instructed "won on three metrics
(32% cost, 61% context, best ROUGE-L)." The docs do contain the phrase "the best
ROUGE-L" in a summary line, but qualify it as noise two paragraphs later. Summary read,
caveat missed, error propagated into the build.

Fix: keep the axis, draw a **noise band** showing both polygons inside it, light two
axes rather than three on the first reveal, and restate the claim as —

> Won on cost and context. Tied on ROUGE-L, inside the noise floor of a 10-question
> sample. Rejected because 5 of 10 answers got worse.

That demonstrates P10 on the project's own numbers instead of asserting it elsewhere.
Refusing to count a favourable result because it sits inside the noise is a stronger
signal than the win would have been.

### Standing lesson

Three times this round an encoding was refused for implying data that could not be
sourced — the Gantt, the dot plot, the fabricated waterfall total. The radar is the
fourth case and the only one that got through, because the unsourceable part was not a
missing number but a **missing significance test** on a number that did exist.

## 14. FINAL STATE — deck complete at 0934b8e

Independently verified by the orchestrator, not taken on report:

| Check | Result |
| :-- | :-- |
| HEAD | `0934b8e`, in sync with `origin/main` |
| Slides | 16 |
| Diagrammed slides | 14 (slides 1 and 16 argued bare) |
| SVG files | 17 — three slides render two `v-click` states (4, 9, 10) |
| Referenced SVGs present | all |
| Strict XML validity | all 17 parse as well-formed XML |
| `slidev build` | clean, 810 ms |
| `dist/` staged | never |

Commit arc: `168d588` diagrams + cap dropped -> `c7d5477` rev-6 fixes (claim bar,
radar noise band, 5-bone fishbone) -> `1ef4f29` export gotchas -> `0934b8e` voice pass.

### What the process caught that a single pass would not

Both directions, which is the argument for the orchestrator/worker split:

- Worker caught the orchestrator's `{{TOKENS}}` instruction as a bad trade (regressing
  twelve sourced citations to guard against one error).
- Orchestrator caught the 45.2% / 31.3% mispairing — two figures from different
  populations presented as one comparison.
- Worker caught a doc-vs-message precedence conflict by comparing mtimes, and held off
  committing rather than guessing. Produced the section 8b rule.
- Orchestrator caught the radar asserting a ROUGE-L win the source disclaims as noise —
  a figure contradicting the deck's own P10 using the deck's own numbers.
- Worker caught three XML-export failure classes and a silent label-clipping bug, after
  its own `self_check.py` had already passed.
- Voice pass caught two stale internal claims: a `DECK STATUS` header still saying the
  deck had never been built, and slide 5 citing the removed 3-diagram cap.

Four encodings were refused for implying unsourceable data: the Gantt (no per-bin
durations), the dot plot (4 summary stats drawn as 45 observations), a waterfall total
(two different-scope measurements stitched), and the radar's ROUGE-L win (a number that
existed but had no significance test). The last is the instructive one — the missing
thing was not a number but a noise floor.

### Open

1. **GitHub Pages not enabled.** See section 11. Needs Joel.
2. **Projects 2 and 3.** The recipe is section 6; the reusable assets are the six-act
   skeleton and the slide contract, not the tooling. Awaiting Joel naming the projects.
3. **Upstream note, optional.** The three XML-export gotchas in `img/EXPORT_NOTES.md` are
   generic to the diagram-design plugin, not to this repo. Worth raising upstream; the
   plugin's `self_check.py` catches neither the `--`-in-comment case nor label clipping.

## 15. Post-deploy polish — orchestrator re-lock

Deck verified live at https://mjsushanth.github.io/FinSights/ after Joel enabled Pages.
Two defects found by looking at the rendered page rather than the build log:

1. **Literal `--` on 11 slide faces.** Written as an em dash substitute, but markdown-it
   has `typographer` off by default, so it rendered as two hyphens on nearly every slide —
   including the title slide's eyebrow, the first thing anyone sees. Converted to real
   em dashes (en dash for the date range). Presenter notes deliberately untouched: `--`
   inside an HTML comment never renders, and rewriting 67 instances would risk the
   XML-comment problem recorded in `img/EXPORT_NOTES.md`.

2. **Dark mode crushed contrast.** `style.css` is light-only — hardcoded `#f8f8f6`
   background and `#5a6571` subtitle. With seriph's dark mode active the subtitle sat
   grey-on-near-black. Since a viewer's OS preference decides this, the deck could have
   looked broken for a recruiter with dark mode on. Fixed with `colorSchema: light`
   in the headmatter (verified key, Slidev headmatter reference), locking the deck to
   the scheme its stylesheet was actually designed for.

Both were invisible to every check run so far: `slidev build` passed, all 17 SVGs
validated, the dev server served clean, and the workflow went green. The defects only
appear when a human looks at the page. That is the same lesson as
`img/EXPORT_NOTES.md` entry 3 — some classes of defect have no validator.

**Ownership note, per section 8c.** The worker had been handed `slides.md` and stood
down, and session-to-session messaging hit its rate limit, so a re-lock could not be
announced by message. Recorded here instead, the canonical channel per section 8b:
the orchestrator re-took `slides.md`, made these two changes, rebuilt (724 ms, clean),
verified no slide figure changed, and committed. Worker should re-read before any
further edit.

## 16. Autonomous run — finish through slide 15 and deploy

Joel away, explicit authorisation to finish and publish without review. **Deck ends at
slide 15; there is no slide 16.** The parked asymmetry slide comes out of the live
sequence entirely — content retained, but the deployed deck must be exactly 15 slides.

Worker owns `slides.md`, diagrams, build, commit, push. Orchestrator owns independent
verification of the deployed page and this record. Orchestrator does not edit
`slides.md` during this run (section 8c).

### Final structure — 15 slides, resolving an ambiguity I introduced

My disposition table ended at 16 with a Close slide. Joel then said *"finish all until
slide 15 and forget slide 16."* At that moment slide 16 **was** the Close, so the
instruction drops the Close — it does not ask for two other slides to be merged to make
room for it. The deck ends on Deployment and operations, carrying slight closing weight.

| # | Slide |
| --: | :-- |
| 1 | FinSights — proposition |
| 2 | Two supply lines |
| 3 | Corpus construction |
| 4 | Embedding pipeline |
| 5 | Retrieval architecture |
| 6 | Question to cited answer |
| 7 | Structured KPI extraction |
| 8 | Boilerplate duplication |
| 9 | Cross-company queries |
| 10 | Streaming response delivery |
| 11 | Evaluation infrastructure (fold of score distribution, wrong-year, latency, reranking) |
| 12 | Operating cost analysis — worked use case |
| 13 | Live incremental ingestion |
| 14 | Engineering choices and cost trade-offs |
| 15 | Deployment and operations — final slide |

No Close slide. No slide 16. Parked asymmetry content leaves `slides.md` entirely.

### Corrections to orchestrator specs, found by worker verification

Numbers I passed second-hand that did not survive checking. Recorded because the pattern
matters more than the individual errors:

- KPI table: **25 companies is right.** "18 years" is unsupported anywhere. "98 distinct
  GAAP metrics" is wrong — it is **97 standardized metric labels mixing GAAP and derived**.
  There is also no `company` column; rows key on `cik`, with names in a separate
  dimension table.
- Answer types: four are defined in the schema but **only three are exercised** across the
  curated questions; the numeric type appears in none of them. Say "four defined, three
  exercised."
- **A near-duplicate curated-question file exists** with conflicting difficulty and
  confidence values for the same questions. Cite the canonical file only.

All three came from the orchestrator relaying figures from memory of an earlier
inspection instead of re-reading source. Same failure class as the ROUGE-L noise-floor
error in section 13.

### Acceptance criteria — self-review replaces Joel's review

1. Exactly 15 slides live.
2. Every slide fits its canvas **at every click state**, confirmed by looking at it.
3. Click counts equal real steps; no phantom trailing clicks.
4. Zero internal codenames on any slide face.
5. No slogan titles; plain tech/business phrasing.
6. Every figure on a face traced to a source, or the claim rewritten to not need it.
7. Live page renders, confirmed by loading it — not by a green workflow.

Criterion 2 exists because the previous "complete" call passed build, XML validation and
CI while three slides were unusable. Automated signals do not cover slide overflow.

Ranked for a short run: **numbers real, slides legible.** Tone, staging and diagram
choice are recoverable in a later pass; those two are not, because Joel reads the live
page cold.

### Progress ledger

| When | Commit | State |
| :-- | :-- | :-- |
| run start | `6ab7797` | Slides 1-2 in new frame and approved. 3-15 outstanding. Specs for all sent. |
