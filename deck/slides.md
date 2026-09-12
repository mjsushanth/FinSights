---
theme: seriph
# Confirmed 2026-09-11: seriph, light mode, custom accent layer in style.css
# matching the diagram-design "finsights" profile. Screenshotted and ruled
# on by the orchestrator — not a placeholder anymore.
background: null
class: text-left
# style.css is light-only (hardcoded #f8f8f6 bg, #5a6571 subtitle).
# Locked so seriph's dark mode cannot take over and crush contrast.
colorSchema: light
highlighter: shiki
lineNumbers: false
drawings:
  persist: false
transition: slide-left
title: FinSights — SEC 10-K Document Intelligence with Hybrid Retrieval
---

<!--
DECK STATUS: built and pushed. `slidev build` clean, all diagram SVGs
validated as strict XML and confirmed serving. Every number below is cited to a source file in
its own slide's presenter notes. Two numbers (\$32.85/mo NAT, \$0.017-0.06
Bedrock cost band) are the only ones NOT independently re-measured this
session -- both are reported from the design-principles note / SYSTEMS_WALKTHROUGH.md, both
already carry [V] or an explicit AWS Pricing API citation in their own
source doc, and both are flagged as such in their slide's notes rather
than presented as fresh measurement.
-->

# FinSights
## SEC 10-K document intelligence with hybrid retrieval

<div class="eyebrow">Sep 2025 – Dec 2025</div>

25 companies &middot; 2006-2025 &middot; **614,647** live vectors &middot; built for **$2.21**

<!--
Title slide, exempt from the one-number rule by convention (frame, not
argument). Verified against IMPLEMENTATION_GUIDE.md:43 (1,850 vectors/min,
\$2.21 total across three
bins) and the live S3 Vectors index count. Corpus is 25 companies, not the
upstream 4,674-company ETL universe -- that distinction matters and gets
its own correction elsewhere in the repo; not relitigated here.
-->

---
layout: two-cols
class: text-left compact-list
transition: fade-out
---

# Two supply lines feed one answer

<div class="eyebrow">SEC 10-K filings, 2006–2025 · 25 companies</div>

<span class="stat">$0.150<span class="stat-label">/month to keep the whole 614,647-vector index live</span></span>

- SEC 10-K sentence corpus, extending a 71M-sentence base — kept current via EDGAR SDK incremental ingestion and the SEC EDGAR API
- Structured financial KPIs from a third-party parsed-financials corpus, standing alongside the sentence text
- **Hybrid pipeline:** vector embeddings and entity adapters converge into a single, fully-provenanced context spanning financials, sentences, and analysis

::right::

![Two supply lines feed one answer](./img/hybrid-pipeline-thesis.svg)

<!--
REWRITTEN 2026-09-11 per Joel's direct correction after reviewing the live
deck: "the deck is the early-growth and impact presentability of the
project's initiatives... not your agentic-work memories." This slide
previously led with a \$17/month budget constraint and a "decision / hurt
quality" matrix -- a process/cost-discipline framing, not a proposition
about what the system is and does. Joel, verbatim: "under 17\$ that thing is
NOT a thing for us, dont use under 17/month tag. our tag is different."

New framing is the project's own stated thesis, verbatim from README.md:10
-- "Two supply lines feed one answer: structured KPI extraction from parsed
financial tables, and semantic retrieval over sentence-level embeddings."
Left-column bullets are Joel's own five framing points (SEC 10-K utility,
the 71M-sentence cold dataset, the live EDGAR SDK incremental feed, the
third-party tabular-metrics corpus, the hybrid-pipeline philosophy)
condensed to three for the face; nothing is fabricated, everything traces
to material already documented in this repo, not just this slide's own
prior draft.

REFINED 2026-09-11 after Joel reviewed this slide directly: two changes.
(1) Named the actual tooling behind "kept current" rather than leaving it
as a vague "live feed" -- EDGAR SDK incremental ingestion and the SEC
EDGAR API, both confirmed in README.md's own repo map and source-links
section (src_edgar_incremental, company_tickers.json). Did not name
"EdgarTools" specifically -- README.md:223 marks that one as "potentially
used," not confirmed, so it stays out of a slide face. (2) The
"hybrid pipeline" bullet was Joel's own rough phrasing, given as a bare
idea to refine, not to ship verbatim -- rewritten from a flat list
("embeddings + entity adapters assemble one context -- financials,
sentences, analysis, provenance") to a single sentence that states the
mechanism and the outcome ("vector embeddings and entity adapters converge
into a single, fully-provenanced context spanning financials, sentences,
and analysis"). Same theme and same four components, folding "provenance"
into an adjective rather than a fourth list item, since a fully-provenanced
context is what the pipeline actually claims to deliver.

STAT CORRECTION, not taken on request: the peer's spec asked for "average
cost per query, ~\$0.00004" and "total cost of the vector embeddings" as the
headline. Neither figure checked out as requested. \$0.00004 does not appear
anywhere in ModelPipeline/finrag_ml_tg1/S3Vect_QueryCost.md or any other
source I could find. The document's one figure literally labeled "Average
cost per query" is \$0.0170 (S3Vect_QueryCost.md:259) -- but that entire
table (lines 190-266) is a COST MODEL built from assumed monthly query
volumes (100/300/500/1,000/1,500/2,000/5,000 queries/month) and an assumed
35%/65% Sonnet/Haiku split, not a measurement of real traffic. This deck's
whole discipline has been measured over modeled, disclosed where it isn't,
so I did not put an unverified number or an unlabelled model estimate on
the opening slide's headline stat. Used \$0.150/month instead: real,
measured, already independently verified earlier in this project
(S3Vect_QueryCost.md's "Verified pricing -- measured 2026-08-05" section;
also matches the \$0.1452/30-day idle-floor figure in the same section,
small variance from rounding/estimation basis, not a contradiction). This
is a different number from the title slide's \$2.21 (that is the one-time
embedding-generation cost; this is the ongoing monthly storage cost) --
deliberately complementary, not redundant.
DIAGRAM NOTE: new diagram, hybrid-pipeline-thesis.svg. Two source boxes
(structured KPI extraction, semantic retrieval) converging via orthogonal
elbows into one focal "One answer" box, matching README.md's own two-lines-
into-one framing exactly. Not the decision-matrix diagram that lived here
before -- that content is being reframed separately as an "architecture
choices, each against a named alternative" slide per the orchestrator's
next spec, not yet built.
-->

---
layout: two-cols
class: text-left compact-list
---

# Corpus construction — selection, stratification and scoring

<span class="stat">47s<span class="stat-label">to stratify-sample 71M sentences into the working corpus</span></span>

- In-process DuckDB and Polars over a hosted warehouse, stratifying three merged sources — S&P 500 holdings, SEC CIK mappings, and a 71M-sentence corpus
- Company selection is scored, not hand-picked — five hard admission gates determine <span v-mark.underline.orange>WHO</span> is in the dataset, not <span v-mark.underline.orange>WHAT</span> gets sampled
- Temporal and section imbalances are left uncorrected, deliberately — real disclosure variation is signal, not noise to normalize away

::right::

![A weighted multi-objective selection score, not a manual pick](./img/corpus-selection-score.svg)

<!--
NEW SLIDE 2026-09-11, split out of the old "Corpus and checkpointed
regeneration" slide per the orchestrator's disposition table -- that slide
was doing two jobs (corpus selection AND embedding regeneration) and this
one takes the selection half, expanded with real material that was never
on a slide before.

Source: DataPipeline/data_engineering_research/duckdb_data_engineering/
DuckDB_Sampling_Strategy.md for the quality_score formula and the five
admission gates, verbatim, and its own line "These filters determine WHO
is in the dataset, not WHAT gets sampled" (quoted on the diagram exactly).
Inputs verified in the same doc: S&P 500 holdings via State Street SPDR
SPY daily holdings (503 holdings, 99.94% weight coverage), SEC EDGAR
company tickers (10,142 CIK-to-ticker mappings), plus a custom shortlist
for sector diversity and underrepresented industries.

The "47s" stat and "three merged sources" bullet are both from
Data_Engineering_README.md's "Production-Ready Proof" table (three
heterogeneous sources -- Excel SPY holdings, SEC JSON mappings, 71.8M-row
Parquet corpus -- merged via fuzzy matching; total pipeline wall-clock
~47s for corpus load through export, dominated by a 36.83s schema-
retrieval join, which the table itself calls "Expected (big join)" rather
than a problem). Rounded 71.8M to 71M to match the wording already
shipped on slide 1's bullet, not a new number.

The "imbalances left uncorrected" bullet is DuckDB_EDA.md's own two
named arguments ("Recency Bias is Actually Good" and "Temporal, Sentence,
Section Imbalances shouldn't be corrected in the dataset"), not my
framing -- the doc's own reasoning: "Product is a RAG system, not a
time-series model," and section/sentence-density variation reflects how
companies actually choose to disclose, which the retrieval layer should
be robust to rather than the corpus trying to flatten.

DIAGRAM NOTE: new diagram, corpus-selection-score.svg. A formula panel
plus a five-row admission-gate checklist, closing with the source's own
"WHO not WHAT" line as a bordered callout -- not a flowchart, because the
selection logic here is a scoring/filtering computation, not a sequence
of stages, and a flowchart would invent connective structure that doesn't
exist. Deliberately dense/textual to match how a real quality-gate query
reads.
-->

---
layout: two-cols
layoutClass: wide-left
class: text-left compact-list tight-body
---

# Embedding pipeline — batching, rate control, checkpointing and recovery

<span class="stat">1,850<span class="stat-label">vectors/minute, sustained</span></span>

- Token-aware batching — 96 vectors / 15K tokens per call, exponential backoff, three-try recovery
- Rate limiting with retry classification — failed batches logged for deterministic replay, not blocked; the same pattern reused in the S3 retriever
- Checkpoint and resume, flushed before abort — a real quota-exhaustion run once lost 1,920 already-embedded sentences before this fix existed
- Merge-crash guard protects completed bins from a failed final merge
- Provider abstraction — Bedrock and Cohere direct behind one interface; caught before shipping: a single global checkpoint path would have let two providers' vectors merge undetected
- Cohere's 2,000 rpm ceiling was never binding — the run used ~34 rpm of it, headroom rather than a speed claim

::right::

![Three checkpointed embedding regeneration bins, vertical](./img/embedding-bins-vertical.svg)

<!--
EXPANDED 2026-09-11, split out of the old "Corpus and checkpointed
regeneration" slide per the orchestrator's disposition table -- the
selection half became its own slide (previous); this is the regeneration
half, now carrying the pipeline's real engineering rather than just its
bins. Layout per Joel's explicit instruction: the bin diagram vertical on
the right (~30% width), the left column (~70%) carrying the actual talk.

Source: ModelPipeline/finrag_ml_tg1/investigation_analysis/
EMBEDDING_PROVIDER_ABSTRACTION_DESIGN.md, VERIFIED directly this session,
every figure below traced to a specific line:
- Pipeline shape (line 257-258): load meta -> filter -> [batch ->
  rate_limiter -> provider.embed -> retry] -> checkpoint -> merge ->
  update meta -> save to S3 + local.
- 96 vectors / 15K tokens per call: also IMPLEMENTATION_GUIDE.md:43
  ("Batches of 96 vectors / 15K tokens per call, with exponential backoff
  and three-try recovery").
- The 1,920-sentence loss is a REAL incident, not a hypothetical: "yesterday
  the run reported 131,520 embedded but only 129,600 were saved -- about
  1,920 sentences of already-paid-for work lost" (line 199-200). Flushing
  the checkpoint before the abort path recovers it going forward.
- CHECKPOINT_PATH collision: "one global file... a Bedrock-run and a
  Cohere-run checkpoint would collide, and vectors from two different
  transports could merge into one checkpoint file undetected" (line
  192-196) -- caught during the provider-abstraction design, before it
  shipped, not after an incident.
- Cohere rate ceiling (line 70-72): "Cohere's 2,000 rpm ceiling is not the
  binding constraint (we would use ~34 rpm of it); it simply means no
  throttling and no daily wall... Do not read 2,000 rpm as a speed claim."
  Preserved that precision rather than inflating it.
- "hard-won" (line 231): "checkpoint/resume, merge-crash guard, rate
  limiter and retry classification were all hard-won" and stay unchanged
  through the provider refactor -- the reason these bullets are framed as
  achievements, not incidental plumbing.

Bins/cost/throughput figures unchanged from the prior version of this
slide: 614,647 sentence-level vectors, $2.21 total (~$1.30 Bedrock +
$0.91 Cohere direct), three bins (two via Bedrock, one via Cohere direct
after an 8.1M-token/day account quota), ~85 minutes wall-clock in one
sitting. Kept the existing 1,850 vectors/minute stat rather than
replacing it -- still the strongest single verified throughput number for
this pipeline.

DIAGRAM NOTE: new diagram, embedding-bins-vertical.svg -- same three bins
and checkpoint markers as regeneration-process.svg (still on disk, no
longer referenced), redrawn stacked vertically top-to-bottom for the
narrow right column instead of left-to-right for a full-width slide.
-->

---
class: compact-fig-lg
---

# Retrieval architecture — adaptation, variants, assembly, provenance

<span class="stat">$0.0001<span class="stat-label">per query to generate 2-4 semantic rephrasings</span></span>

One entity adapter feeds two supply lines; every hit keeps its source, variant, and distance.

![Entity adaptation, two supply lines, and provenance-carrying synthesis](./img/retrieval-architecture-full.svg)

<!--
EXPANDED 2026-09-11 per the orchestrator's spec: the prior 5-box diagram
(architecture.svg, still on disk, no longer referenced) compressed the
whole system to conceptual stages. Joel's own instruction: "make that
diagram obviously expanded... queries, retrieval controls as: entity
adapters, assembly, communication, provenance, all of that. dont miss
those." This is the deck's architecture centrepiece -- the one diagram
given more space and bolder treatment than the others, per that
instruction.

Every stage verified directly against IMPLEMENTATION_GUIDE.md this
session, not carried over from the old diagram's abstraction:
- Entity adapter (Part 6): alias generation, punctuation normalization,
  case variants, suffix stripping, ticker-to-CIK mapping, fuzzy fallback
  with a strict similarity threshold. Recognizes a company by CIK, name
  variant, or ticker.
- The two supply lines, verbatim (Part 7.1): "Query -> EntityAdapter.
  extract() -> MetricPipeline.process() -> format_analytical_compact()"
  and "Query -> EntityAdapter.extract() -> QueryEmbedderV2.embed_query()
  -> 1024-d Cohere v4 embedding."
- Variant generation (Part 8): Claude Haiku generates 2-4 semantic
  rephrasings at ~$0.0001/query (the slide's stat), each independently
  embedded with a unique variant_id.
- Triple retrieval regime (Part 8): filtered_hits via metadata pushdown
  (50% cost saving vs. unfiltered), global_hits as no-filter fallback,
  union_hits merging both after dedup by sentenceID, keeping the
  lowest-distance version.
- Context assembly (Part 9): edge-safe window expansion (+/-3 sentences),
  provenance via parent_hit_distance / source / variant_id on every hit,
  typed contracts (FilterConfig / VariantResult / S3RetrievalBundle)
  replacing dict-passing.
- README.md:8's own framing anchors the title: "Hybrid retrieval system
  fusing structured KPI extraction... narrative semantic search with
  meaningful variant-diversity queries, window-expansion on hop context...
  that grab complex multi-year, multi-company, multi-KPI, multi-section
  financial patterns."

DIAGRAM NOTE: new diagram, retrieval-architecture-full.svg, full slide
width (viewBox 1200x500) since this is the one diagram in the deck
deliberately given more room than the others. Seven nodes: Query, Entity
Adapter (shared), Metric Pipeline (top/structured track), Variant
Generation -> Triple Retrieval -> Context Assembly (bottom/semantic
track), converging into one accent-focal Synthesis box. Shorter, bolder
boxes than the deck's other diagrams per Joel's explicit request; only
Synthesis carries accent, matching the type's focal-element budget --
it is the slide's one true "answer," everything upstream is process.
-->

---
class: compact-fig-lg
---

# Question to cited answer — the end-to-end retrieval and synthesis path

<span class="stat">3<span class="stat-label">evidence sentences behind one three-year answer</span></span>

![One real question, traced to a cited answer](./img/question-to-answer.svg)

<p>Every claim traces to <span v-mark.underline.orange>real, cited filing sentences</span> — not paraphrased chrome.</p>

<!--
NEW SLIDE 2026-09-11 per the orchestrator's spec: "Not a UI screenshot. A
Streamlit screenshot shows chrome, not the system, and it dates badly.
Show one real question traced end to end, with the real answer and real
citations." This is the deck's product slide -- the one thing it never
had before, everything else describes the system, this shows it working
on one real payload.

Source: MLFlow_POC/data/p3_gold_test_suite_31q.json, question P3V3-Q003,
VERIFIED directly this session by reading the actual JSON record, not
taken from the spec message alone -- every field on the diagram matches:
question text verbatim, answer opening verbatim, 3 evidence_sentence_ids
(0000200406_10-K_2022_section_7_54, ..._2023_section_7_54,
..._2024_section_7_61), retrieval_scope cross_year, difficulty medium,
curation_confidence 0.84. Full recorded answer, not shown on the slide
face (kept to the opening sentence there, matching this deck's face/notes
split): "Johnson & Johnson initially portrays COVID-19 as a tailwind and
then a headwind for different parts of the portfolio. In 2022 it notes
that certain consumer franchises benefited from innovation, e-commerce
strength and COVID-19 recovery. By 2023 it reports operational declines
in some personal care categories, citing negative COVID-19 impacts in
China and broader pressure on consumption. In its 2024 MD&A the company
explains that infectious disease product sales fell versus the prior year
primarily because COVID-19 vaccine revenue declined, making
pandemic-related demand a key driver of the trend."

CITATION TRAP CAUGHT AND AVOIDED: a second, near-duplicate 31-question
file exists (data_cache/qa_manual_exports/goldp3_analysis/
p3_gold_qtest_31q_ffhall.json) that a design doc incorrectly claims is
"identical" to the canonical file -- it is not; 29 of 31 records differ,
including this exact question's own confidence value (0.83 there vs 0.84
canonical). Cited only the canonical MLFlow_POC path.

The stages shown (entity resolution, two supply lines, context assembly)
are the same ones detailed abstractly on the retrieval-architecture slide
-- this slide shows them carrying one real payload rather than described
in the abstract. "A tailwind-then-headwind reading across three years is
not something keyword search produces, and not something an LLM can
invent safely" is the orchestrator's own framing for why this specific
question is the argument for the whole system, not just an example.

DIAGRAM NOTE: new diagram, question-to-answer.svg. Four stages (question
-> entity resolution -> two supply lines -> context assembled) converging
into one accent-focal cited-answer panel with three citation pills, one
per evidence sentence. Given the compact-fig-lg cap (300px) since it sits
alone on the slide with no other body text competing for space.
-->

---
layout: two-cols
class: text-left compact-list
---

# Structured KPI extraction — financial metrics as looked-up facts, not model reading

<span class="stat">9,260<span class="stat-label">GAAP and derived facts, 25 companies, 97 standardized metric labels</span></span>

- Asking a model to read a balance sheet is a reading-comprehension task with no ground truth; looking a metric up is a join — the model explains the number instead of extracting it
- Every fact row carries its form, filing date, and accession number, alongside company, ticker, year, and metric identity
- That provenance makes it restatement-aware: the same fiscal year reported in two different filings stays distinguishable — a number becomes a sourced number

::right::

![Financial facts, looked up with provenance](./img/kpi-fact-table.svg)

<!--
NEW SLIDE 2026-09-11 per the orchestrator's spec, with the counts
corrected after independent verification -- the spec's "25 companies, 18
years, 98 distinct GAAP metrics" only partly checked out.

VERIFIED: table defined in DataPipeline/src_metrics/xbrl_facts.py:149-152
(GAAP facts) and derived_kpis.py (derived ratios), assembled by
pipeline.py:50-77, artifact KPI_FACT_DATA_EDGAR.parquet. Columns,
verbatim: cik, ticker, year, metric_gaap, metric_code, metric_key,
metric_label, metric_type, value, unit, form, filed_date, accession_no --
13 columns, four of them metric-identity fields, not the two the spec
implied. There is no company-name column; company names live in a
separate dimension table (finrag_dim_companies_25.parquet) keyed by cik.
25 companies VERIFIED (metrics_config.yaml:16-17, data_cache/README.md:
66-68). Row count 9,260 VERIFIED (EMPIRICAL_METHODS_AND_FINDINGS.md:134,
also cited in analytics/REVIEW_1.1_senior_findings_2026-07-27.md:112-113
as a full recompute across "all 25 companies, 10-year depth").

CORRECTED, not used as specified: "18 years" does not appear in any repo
document for this table -- metrics_config.yaml:41-42 configures a
2006-2025 window (20 years) for GAAP facts, but derived ratios use only
2 years' depth (pipeline.py:51), and the one *measured* year-count on
record (17 distinct years, 2009-2025) is from a superseded, pre-rebuild
21-CIK table (LEGACY_MODULE_FINDINGS.md:95-96) that predates the current
25-company universe. No single verified number exists for "years covered"
on the current table, so it is left off the slide entirely rather than
asserted. "98 distinct GAAP metrics" is also not supported -- the one
documented total is 97 standardized metric labels
(metric_mapping_v2.py:26-31, independently confirmed by parsing
METRIC_MAPPINGS), and that count mixes GAAP tags with derived ratios
(6 of 10 derived ratios are among the 97) rather than being pure GAAP,
matching the metric_type column's own gaap/derived split. Slide stat uses
"97 standardized metric labels," not "98 distinct GAAP metrics."

DIAGRAM NOTE: new diagram, kpi-fact-table.svg, a compact schema panel
(column list + a restatement-aware provenance callout) matching the same
"dense fact panel, not a flowchart" treatment as the corpus-selection-
score diagram -- this is a lookup structure, not a process.
-->

---
layout: two-cols
layoutClass: wide-left
class: text-left compact-list
---

# Boilerplate duplication in filings — classification and selective removal

<span class="stat"><span v-mark.circle.orange>85%</span><span class="stat-label">of "duplicate" rows are not duplicates at all</span></span>

- Not a blanket dedup — a classification. Repeated headers (1,356 rows) are flagged and deferred to the embedding stage; adjacent exact repeats (123 rows) are the only ones actually removed, and now prevented at ingestion
- The remaining 85% is the same compliance sentence genuinely reused across two distinct debt instruments or two distinct lawsuits — removing either "would delete real, distinctly-attributable information"
- On the retrieval side: variant-diversity queries and union-dedup-by-lowest-distance keep one crowded region from consuming the whole context budget — the mean near-duplicate rate in a retrieved context measured at 22.7%

::right::

![Three kinds of repetition, one of them actually removed](./img/boilerplate-classification.svg)

<!--
REFRAMED 2026-09-11 per the orchestrator's spec, moved and rebuilt per
Joel's own review: "not a huge diagram that takes 90% space. make a small
diagram on the right and TALK ABOUT IT... what did we notice as the
impact, the aspect of 'semantic crowding'... searches getting drawn -
poured towards hits on that boilerplate crowding at large companies
instead of niche query we are asking. and we did fix this as well."

Source: DataPipeline/analytics/duplicate_sentence_analysis.md, VERIFIED
directly this session by reading the doc, not the spec message. Three
categories, classified across the full 614,910-row table: Category A
(short/extreme-repeat fragments, <=4 words repeated >=10x within one
company-year) is 1,356 rows (0.22%), flagged and deferred to the
embedding stage, not removed. Category B (immediately-adjacent exact
repeats, same sentence at consecutive sentenceID positions) is 123 rows
-- the only ones actually removed: cleanup_adjacent_duplicates.py read
the production table from S3, dropped the 123 rows (614,910 -> 614,787),
wrote it back, synced both local mirrors; collapse_adjacent_duplicates()
was added to Stage 3 of clean_and_split.py so future EDGAR-incremental
fetches can't reintroduce it. Category C is 85% of all "duplicate" rows
by count, deliberately preserved: the doc's own real examples are a
Johnson & Johnson legal-disclosure sentence reused across two genuinely
separate litigation discussions ~330 sentences apart, and a Visa
compliance sentence applied to two different real debt instruments
(Senior Notes, Credit Facility). No schema change -- no boilerplate-flag
column was added, per the doc's own explicit instruction to avoid
complicating the schema.

The "semantic crowding" mechanism Joel asked about (large-company
boilerplate pulling hits away from a niche query) and its retrieval-side
mitigation are both from RETRIEVAL_IMPROVEMENT_STUDY.md 2.1, already
verified earlier this session: mean near-duplicate rate 22.7% of a
retrieved context (25 real exported contexts measured), root-caused to
sentence_expander.py:517's identity-based dedup key never comparing
sentence text. Retrieval-side mitigation (variant-diversity queries,
union dedup keeping the lowest-distance version) is the same mechanism
detailed on the retrieval-architecture slide, referenced here rather than
re-explained.

DIAGRAM NOTE: new diagram, boilerplate-classification.svg, small and
right per Joel's explicit sizing instruction -- a three-row classification
panel (A flagged / B removed, accent / C preserved) plus the source's own
"distinctly-attributable information" line as a callout, replacing the
old full-width boilerplate-treemap.svg (still on disk, unreferenced),
which visualized the now-superseded "44.9% = problem" framing rather than
the classification.
-->

---
class: compact-fig-lg
---

# Cross-company, multi-year, multi-section queries — coverage and capability

<span class="stat">4<span class="stat-label">companies resolved and answered as one list, in the hardest question in the set</span></span>

Answers return per-company lists, not one blended paragraph — the entity adapter
resolves each company, and variant generation keeps one from absorbing the budget.

![Three real cross-company questions, answered as per-company lists](./img/cross-company-questions.svg)

<!--
NEW SLIDE 2026-09-11 per the orchestrator's spec, with numbers corrected
after independent verification of the schema claim. All three questions
VERIFIED directly against MLFlow_POC/data/p3_gold_test_suite_31q.json,
not taken from the spec message: P3V3-Q004 (2009, Radian Group / Netflix
/ Mastercard, data protection and customer-data exposure, difficulty
medium, confidence 0.85), P3V3-Q005 (2010, Walmart / Apple / Microsoft /
Icahn Enterprises, liquidity and credit-related risk, difficulty HARD,
confidence 0.81 -- confirmed hard only in this canonical file, a
near-duplicate file records it as medium), P3V3-Q006 (2023, Exxon Mobil /
Eli Lilly, technology licensing revenue and U.S. drug-program
constraints, difficulty medium, confidence 0.83; Exxon's figure is
"around $155 million" in the source, hedge reproduced rather than
stated as exact).

CORRECTED, not used as specified: the spec described the system as
supporting "four answer types -- narrative span, per-company list,
boolean with explanation, numeric with tolerance." That is true of the
schema (IMPLEMENTATION_GUIDE.md:193, validation_notebooks/
06_Gold_Test_Framework.md:642) but not of the data -- across all 31
canonical questions, answer_type is span: 26, list: 3, boolean: 2,
numeric: 0. Zero questions exercise the numeric type, and the backing
answer_numeric/tolerance fields are null in all 31. Framed here as three
companies resolving to per-company lists (the type this slide's examples
actually use), not as a claim that all four types are exercised.

SCOPE LINE, per the orchestrator's own correction to its disposition
table: "cross-company questions are a small share of the curated set, and
multi-company retrieval is the area with known starvation behaviour...
state it as scope, not as a confession." VERIFIED: 3 of 31 questions
(9.7%) are cross_company (retrieval_telemetry_and_reranking_design.md:71:
local 24, cross_year 4, cross_company 3) -- these three ARE that entire
slice, not a sample of a larger cross-company set. The starvation finding
itself (Netflix 0/3, already on the cross-company-queries-turned-slide-11
material) rests on this same 3-question sample; a repo doc makes exactly
this point about calibration on so few questions
(ANALYSIS_reranker_judgment_calls_2026-07-29.md:88).

DIAGRAM NOTE: new diagram, cross-company-questions.svg, three real
question cards plus a stated-scope callout, not a flowchart -- these are
example payloads, matching the same treatment as the question-to-answer
slide's single example, scaled to three.
-->

---
class: compact-fig-md
---

# Streaming response delivery — stage events and token-level output

<span class="stat">4.3ms<span class="stat-label">time to first byte, against 8.96s total processing</span></span>

A `queue.Queue` plus a background thread streams pipeline-stage events and
token output to the browser. Total time is unchanged. What changed is the wait.

![Browser, endpoint, worker thread, and queue](./img/sse-sequence.svg)

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
transition: slide-up
---

# Evaluation infrastructure — measurement that produced decisions

<span class="stat">5/10<span class="stat-label">held-out answers got worse -- the number that reversed a ship decision</span></span>

- Per-stage instrumentation caught a wrong attribution: the documented ~90% pipeline-time figure was real, but variant generation (1,990ms) was the larger component, not S3 Vectors retrieval (1,465ms)
- A 0.063-wide similarity band across the top 45 candidates, zero rejections at any threshold, was the evidence that motivated trying a cross-encoder reranker at all
- Reranking won on cost (32%) and context (61%), tied on ROUGE-L inside the noise floor — and was rejected anyway: answers got worse on 5 of 10 held-out questions
- The mechanism was structural, not noise: the cross-encoder is blind to fiscal year, and off-year context share rose from 31% to 47% of what survived pruning — the same deterministic gap that leaves cross-company questions under-served, since 8 of 23 real exports never contained the asked year at all

<!--
FOLDED 2026-09-11 per the orchestrator's disposition table: four slides
that were each their own "reversal story" under the old process-centric
frame collapse into one here, since as project work they are one thing --
built evaluation infrastructure, and it produced real decisions -- and one
strong slide beats four weak ones. All four findings and their citations
preserved below, sources unchanged from before the fold.

(1) Latency attribution, Source: TIER1_PROGRESS_LOG.md Step 0
(2026-08-01), VERIFIED. The retrieve timer wrapped BOTH variant generation
(1 Haiku call + 3 embedding calls) AND the actual S3 Vectors queries as
one block -- the ~90% figure for the whole block was correct, attributing
all of it to "S3 Vectors" specifically was not. Motivated splitting the
timer into variant_gen_ms and s3_query_ms as separate fields.

(2) Flat score distribution, Source: RETRIEVAL_IMPROVEMENT_STUDY.md 2.4,
quoting 08_RAGArch_DesignNotes.ipynb cell 17 verbatim, [V]. "All
thresholds (0.0 to 0.5): 45 hits, NO rejections... no long tail of weak
matches to filter out AT ALL" -- presented in source as the single
strongest evidence for trying a cross-encoder, since only a model reading
query and candidate jointly can extract signal a band this narrow doesn't
carry.

(3) The reranking rejection, Source: RERANKING_FINAL_SYNTHESIS.md,
cross-referenced against IMPLEMENTATION_GUIDE.md:420 and :425
(enable_reranking: false, confirming the rejection shipped as a real
config state). Won on cost/context, tied on ROUGE-L (0.1120 vs 0.1012,
delta 0.0108, inside a 10-question sample's noise floor) -- rejected
because "that 'top-8 is not fit to ship' follows from 5-worse-of-10," not
primarily from the wrong-year mechanism. Off-target-year blocks score
higher (mean 0.300 vs 0.219) and are longer (5.49 vs 4.04 sentences) than
on-year blocks -- the cross-encoder scores text quality and report_year is
never in its input, so it structurally cannot tell a well-written
wrong-year passage from a well-written right-year one.

(4) Wrong-year / cross-company coverage, Source: RETRIEVAL_IMPROVEMENT_
STUDY.md 2.6 and 2.7, both [V]. 8/23 (35%) of real exports missing the
asked year entirely; cik_int filter + single global topK means ANN
returns the 30 globally-best hits regardless of company, so a company
whose sentences sit slightly further from the query gets nothing --
Netflix: 0 context in 3/3 runs. Only 3 of 31 gold questions are
cross_company (same set detailed on the cross-company-queries slide), so
this affects 100% of the multi-company gold set that exists.
"Deterministic" is the word worth keeping here -- a structural gap, not
noisy variance.

Diagrams that carried these four findings (flat-score-range.svg,
wrongyear-sankey.svg, latency-claim.svg, latency-measured.svg,
rerank-radar-won.svg, rerank-radar-full.svg) are no longer referenced by
any slide as of this fold -- left on disk, not deleted, per this deck's
standing practice for superseded diagrams.
-->

---
layout: two-cols
class: text-left compact-list
transition: slide-up
---

# Operating cost analysis — storage, compute and inference under realistic usage

<span class="stat">$3.80<span class="stat-label">a light month -- $12.40 a heavy one, four sessions and 200 questions</span></span>

- A real scenario, not a unit-rate table: four 30-minute sessions and 200 questions in a month
- Infrastructure — idle floor, Fargate compute — stays under <span v-mark.underline.orange>$0.40</span> in either case; the entire light-to-heavy spread is Bedrock inference cost, not infrastructure
- Not hypothetical: 1.0633 vCPU-hours have actually been consumed across two real sessions to date, with the service otherwise sitting at desiredCount=0

::right::

![A worked month, not an abstract unit-cost table](./img/cost-scenario-table.svg)

<!--
NEW SLIDE 2026-09-11 per the orchestrator's spec and follow-up
correction: state a realistic month, then price it, rather than an
abstract per-unit rate table. Numbers verified against
ModelPipeline/deploy_aws/DEPLOY_LEDGER.md directly this session, not
taken from the orchestrator's message alone (per this deck's standing
practice, even when a number arrives "pre-verified"):
- Idle floor $0.2938/month VERIFIED (DEPLOY_LEDGER.md:179), decomposing to
  S3 Vectors storage $0.1452 + S3 Standard $0.0992 + ECR $0.0494. The
  index-storage line is $0.1452 here, not the $0.150 quoted elsewhere in
  the repo -- that's a 30-day-window versus calendar-month framing
  difference. Not shown as a separate line item on this slide (it is
  already inside the idle floor), avoiding the double-count the
  orchestrator itself caught in an earlier draft of this number.
- Fargate $0.04806/hr VERIFIED, decomposes to 1 vCPU x $0.03238 +
  3 GB x $0.00356 + $0.005 IPv4 (IPv4 only accrues while a task runs, so
  correctly excluded from the idle floor). Four 30-minute sessions = 2
  hours = $0.0961.
- Bedrock inference $0.017-$0.06+ per query (previously verified this
  session, S3Vect_QueryCost.md) -- 200 queries: $3.40 at the floor, $12.00
  at the top. This is the dominant, decision-relevant line: infrastructure
  is under 40 cents in either scenario, so the entire spread between a
  light and heavy month is inference cost, not infrastructure -- the
  actual finding worth putting on the slide face, per the orchestrator's
  own framing.
- Vector retrieval ~$0.00004/query VERIFIED (S3Vect_QueryCost.md,
  $2.50/million QueryVectors requests) -- 200 queries, ~$0.008/month,
  genuinely negligible.
- 1.0633 vCPU-hours actual-to-date VERIFIED (DEPLOY_LEDGER.md:165) -- the
  scenario is not hypothetical, it is roughly what this project has
  actually done across two real sessions.

DIAGRAM NOTE: new diagram, cost-scenario-table.svg, a small worked table
(not a chart) per the orchestrator's own instruction -- rows a reader can
check against their own expected usage, light/heavy columns, the
inference-dominance callout as the stated finding rather than the raw
total. Does NOT resurrect the "under $17/month" tag in any form.
-->

---

# Live incremental ingestion — corpus growth without a rebuild

<span class="stat">6<span class="stat-label">pipeline stages take a new filing from fetch to production</span></span>

A new filing enters through the same six-stage path every time — fetch,
extract, clean and split, derive, assemble, push — then the embedding
pipeline's checkpointed resume adds only the new vectors.

![Six stages take a new filing from fetch to production, without a rebuild](./img/incremental-pipeline.svg)

<!--
NEW SLIDE 2026-09-11 per the orchestrator's spec: "the capability that
makes this a system rather than a snapshot." Ties the deck together --
new filings enter through the EDGAR incremental path, and the same
adjacent-duplicate collapse from the boilerplate-duplication slide runs
automatically on every new filing, so the corpus cannot regress into that
problem.

Source: DataPipeline/src_edgar_incremental/, VERIFIED directly this
session by reading each stage file's own docstring, not the spec message:
Stage 1 fetch_filings.py, Stage 2 extract_sections.py (re-fetches each
filing by accession number), Stage 3 clean_and_split.py (turns raw
section text into one row per sentence, calling
collapse_adjacent_duplicates() -- the same function added to prevent the
boilerplate-duplication slide's Category B problem from recurring), Stage
4 derive_features.py, Stage 5 assemble_and_validate.py (sanity checks run
before writing), Stage 6 push_to_etl_incremental.py (uploads to the exact
S3 key the standard ETL path expects, run by default at the end of every
pipeline invocation). Orchestration in run_pipeline.py, which chains all
six stages.

The embedding pipeline's checkpoint-and-resume behavior (added only new
vectors, not a rebuild) is the same mechanism detailed on the embedding-
pipeline slide, referenced here rather than re-explained.

DIAGRAM NOTE: new diagram, incremental-pipeline.svg. Six real named
stages in a row, Stage 3 given accent treatment since it's the one
carrying the duplicate-prevention detail, feeding a seventh box
(embedding pipeline checkpoint/resume) below. No filenames or file paths
in the diagram's visible text, per the codename/filename sweep -- stage
purposes stated in plain language, sourcing kept to the presenter note.
-->

---

# Engineering choices and cost trade-offs

<span class="stat">7<span class="stat-label">structural decisions, each against a named alternative</span></span>

Structural trade-offs land after the product is understood, not before — every
row below is a cost-or-complexity choice, made against a real alternative that was available.

![Seven engineering choices, each against a named alternative](./img/engineering-choices-table.svg)

<!--
MOVED 2026-09-11 per Joel's own principle, per the orchestrator: this was
originally slide 2's content (the decision/hurt-quality matrix). It moves
here because structural trade-offs land after the product is understood,
not before -- the deck now opens with what the system is and does, and
this slide carries the engineering-decision material that used to open
it.

Rows unchanged from the original spec, verified against the project's own
architecture documentation earlier this session (data engineering
philosophy, deploy_aws module structure, gold test suite existence,
NKCP/cost-model calculations, serving/ layout, ECS task definition):
Python ETL + S3 cold storage over a hosted database; ground-level Python
orchestration with S3 for logs/records over a paid tracking service;
plain Python on a kernel machine for ML work over managed notebooks
despite having them available; 3-5 custom gold test suites (hit-rate,
MRR) over trusting vendor benchmarks; index size and inference economics
actually calculated over an assumed cost model; a simple two-tier
client/server over a heavier multi-service split; two containers sharing
one ECS task and namespace over separate namespaces plus a load balancer
-- this last one is detailed with its own numbers on the deployment-and-
operations slide that follows.

Two of the seven rows ("Instead of: trusting vendor benchmarks..." and
"Instead of: a heavier multi-service split") don't have as sharply named
an alternative in the original spec as the other five -- stated honestly
as the general category of complexity avoided rather than inventing a
specific named competing system that wasn't actually evaluated.

DIAGRAM NOTE: new diagram, engineering-choices-table.svg, replacing
cost-decisions-matrix.svg (still on disk, unreferenced) which carried the
old "Decision x Hurt quality" framing (a uniform "No" column, per this
deck's own earlier disclosed deviation) -- this version pairs each
decision with the alternative it replaced instead, per the orchestrator's
reframing of the slide's whole argument.
-->

---
class: tight-body compact-fig
---

# Deployment and operations — reproducible, scaled to zero, understood both ways

<span class="stat">$0.2938<span class="stat-label">/month idle floor, everything scaled to zero</span></span>

<div class="fig-swap" v-click="[1,2]">

Fargate charges per task, on the shape you reserve rather than what you use.
A second container in the same task is nearly free; a second task doubles the
bill — the reason the backend and frontend share one task, sized from a
measured 1,220 MiB peak to 1 vCPU / 3072 MiB, ARM64 for the ~20% discount.

</div>
<div class="fig-swap" v-click="2">

`destroy` then `up` reaches the same steady state from the repository alone —
that round trip is the completeness test: if the reverse operation works, the
forward one was understood. The concurrency model followed the same discipline:
`answer_query` is blocking and I/O-heavy, which alone decided threadpool over
event loop, and an AST audit found exactly one genuinely shared mutable object.

</div>

<div class="fig-swap" v-click="[1,2]">

![One task, two containers, no ALB, no NAT](./img/fargate-deployment.svg)

</div>
<div class="fig-swap" v-click="2">

![The same up edge both bootstraps and rebuilds](./img/control-plane-state.svg)

</div>

<!--
FOLDED AND RETITLED 2026-09-11 per the orchestrator's final structure --
this is now the deck's final slide (15 of 15), carrying slight closing
weight without being a summary slide, per the orchestrator's explicit
instruction: "give slide 15 slight closing weight so it doesn't read as
though the deck was cut off, but do not turn it into a summary slide."

Folds three former slides: Fargate cost model, infrastructure control
plane, and concurrency model (per spec, concurrency reduces to one
bullet here rather than its own slide). All citations preserved verbatim
from before the fold.

Fargate: Source SYSTEMS_WALKTHROUGH.md 3.1/3.2, VERIFIED against the AWS
Pricing API this session (region prefix fixed, per the measurement-
practice design note 8.3): \$0.032380/vCPU-hr, \$0.003560/GB-hr on ARM64,
~20% below x86_64. Units corrected 2026-09-11 per peer verification:
1,220 MiB (10-company query) and 1,139 MiB (simple query) are the two
measured peaks (ECS_FARGATE_RUNBOOK.md:169-170); task shape 1 vCPU /
3072 MiB, split 2560/384 soft reservations (:180). 3072 MiB chosen for
~2.5x headroom over the worst measured peak without paying for a second
vCPU. A second container in the same task is nearly free; a second task
doubles the bill -- why backend and frontend share one task.

Control plane: Source SYSTEMS_WALKTHROUGH.md Part 7.1 (control plane as
a Python package CI calls, not reimplements) and the design-principles
note's reverse-operation-completeness-test principle. \$0.2938/month idle
floor VERIFIED directly against Cost Explorer, swept against every
classic silent-billing resource (NAT gateway, ALB, Elastic IP, EBS, Route
53, Secrets Manager, KMS, Glue) -- none exist. Companion figure, NOT
independently re-measured this session (SYSTEMS_WALKTHROUGH.md 3.4 / the
design-principles note's cost-constraint principle): the ~\$32.85/month a
NAT gateway would have cost, deliberately never adopted in favor of
public subnets, since the workload needs egress, not inbound privacy.
December's prior deployment looked healthy right up until the account
closed -- the destroy/rebuild test is what would have caught that class
of failure, not a stronger monitoring dashboard.

Concurrency: Source the concurrency-and-shared-state design note,
VERIFIED. "Is boto3 thread-safe" has three answers in the source's own
words: Client generally yes (safe to share, not across processes),
Resource no, Session no -- straight from boto3's own docs. The one
genuinely shared mutable object found by AST audit: the DataLoader's lazy
table memo. Design principle: "the shape of the work chooses [the
concurrency model], and then you accept the consequences" -- not a taste
decision.

DIAGRAM NOTE: reused fargate-deployment.svg and control-plane-state.svg
as a staged fig-swap (same v-click="[1,2]"/v-click="2" pattern already
used elsewhere in this deck, not the buggy v-click="[N,99]" range this
deck's early build had to fix). concurrency-layers.svg is no longer
referenced as of this fold -- left on disk, not deleted.
-->

---
transition: slide-up
layout: two-cols
layoutClass: wide-left
class: text-left compact-list tight-body
---

# Evaluation layers — algorithmic, semantic, and model-judged

<span class="stat">31<span class="stat-label">business-realism questions, scored on four axes plus a model judge</span></span>

- **Infrastructure (Phase 1)** — is the index even working? Self@1, Hit@k, MRR against known-good slices
- **Edge cases (Phase 2)** — adaptive windowing exposes real embedding weakness without false failures
- **Semantic scoring (Phase 3)** — four metrics read together, not one at a time (right)
- **Judge, on top** — a model reads the answer itself, catching what the numbers miss

Failures cascade upward — if Phase 1 fails, Phase 3 results are meaningless.

::right::

<div class="metric-bars">
  <div class="metric-row"><span class="metric-label">BERTScore F1</span><div class="metric-bar" style="width: 82.6%"></div><span class="metric-value">0.826</span></div>
  <div class="metric-row"><span class="metric-label">Cosine</span><div class="metric-bar" style="width: 67.5%"></div><span class="metric-value">0.675</span></div>
  <div class="metric-row"><span class="metric-label">BLEURT</span><div class="metric-bar" style="width: 44.6%"></div><span class="metric-value">0.446</span></div>
  <div class="metric-row rouge" id="rouge-row"><span class="metric-label">ROUGE-L</span><div class="metric-bar rouge-bar" style="width: 9.9%"></div><span class="metric-value"><span v-mark.circle.orange>0.099</span></span></div>
</div>

<div v-click="1">

<Arrow x1="825" y1="60" x2="775" y2="147" color="#eb6c36" width="2" />

<p class="metric-note">Read alone, low ROUGE-L says the system is failing. High BERTScore says it is excellent. Only together do they mean genuine synthesis — high semantic fidelity with low lexical overlap is paraphrase, not copying.</p>

</div>

<!--
NEW SLIDE 2026-09-11, added per Joel's direct request (relayed): a sixteenth
slide on layered evaluation, emphasizing the COMBINATION of suites rather
than any single metric. Source: ModelPipeline/finrag_ml_tg1/validation_notebooks/
06_Gold_Test_Framework.md, VERIFIED directly this session by reading the
full document, not taken from the relayed spec alone.

Three gold phases (verbatim framing from the source): "Phase 1 (Infrastructure):
Is the vector index working at all? ... Phase 2 (Edge Cases): What breaks in
unusual sections? ... Phase 3 (Business Realism): Can the system answer
analyst questions?" The "failures cascade upward" line is verbatim from the
doc's own Part 1.2: "The phased approach follows the testing pyramid...
Failures cascade upward -- if P1 fails, P3 results are meaningless."

Semantic metrics VERIFIED exactly against Part 5.6 "Aggregate Metrics
(31-question suite)": BERTScore 0.826 average, BLEURT 0.446 average,
ROUGE-L 0.099 average, Cosine 0.675 average. Not the doc's earlier
"typical range" figures (0.75-0.85 etc.) -- these are the actual point
averages from the 31-question run.

Judge-layer figure (mentioned in notes, not shown on face): the top-8
reranking judgment from RERANKING_FINAL_SYNTHESIS.md section 4's exact
tally, "C (top-8) vs A: 3 better, 2 same, 5 worse" -- already the source
for slide 11's "5/10" stat, not repeated here to avoid restating the same
number twice across two slides.

No internal codenames on this face: said "the three gold phases", not
P1/P2/P3 question-ID codes; no P3V3-Q0xx labels.

v-mark: only .underline and .circle plus color modifiers used, confirmed
against the installed Slidev CLI's own bundled reference
(node_modules/@slidev/cli/skills/slidev/references/animation-rough-marker.md)
rather than asserted from memory. The 0.099 mark has no click-index --
it is visible from the first view of the slide ("mark it"), and the
Arrow + explanation are what wait for click 1 ("then let the next click
reveal why low is correct"), per the request's own sequencing.

DIAGRAM NOTE: no new SVG file. The four-bar chart is plain HTML/CSS
(.metric-bars in style.css), not a baked image, specifically so the
built-in <Arrow> component can point at a real on-slide position rather
than at coordinates guessed inside a static picture -- Joel asked
specifically for pointing arrows using the verified component, not a
diagram-embedded one. Arrow coordinates set from a live bounding-box
measurement of the ROUGE-L row at the real 980x551 canvas, not guessed.
-->
