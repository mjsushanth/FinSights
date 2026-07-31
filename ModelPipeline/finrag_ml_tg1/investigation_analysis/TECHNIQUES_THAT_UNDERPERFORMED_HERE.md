# Techniques That Underperformed on This Corpus, Despite Being Fundamentally Sound

Short research-analysis note, not a critique of the techniques themselves. Every item below is
textbook-correct, widely taught, and works well in general or in the specific benchmarks it was
published against. The point is narrower: **fit to *this* data** (SEC 10-K sentence-level
financial text) is a separate question from soundness, and this project's own measurements
(not received wisdom) are the evidence for each entry. Same logic as BM25 being excellent on
short, keyword-dense queries and mediocre on long, paraphrase-heavy ones — the algorithm isn't
wrong, the data-technique fit is.

1. **Cross-encoder reranking (Cohere Rerank 3.5).** Textbook two-stage retrieval, and published
   well on a near-identical financial-QA benchmark (FinDER, +15.5pp correctness). Here: real
   measured harm at the shipped config, because (a) it is metadata-blind — never sees
   `report_year` — while SEC risk-factor/MD&A prose is heavily copy-pasted year over year, so the
   reranker cannot tell "right answer" from "same sentence, wrong year"; (b) it scores by length
   (r=+0.285), which systematically buries single-sentence numeric facts under longer boilerplate
   agglomerations. See `RERANKING_FINAL_SYNTHESIS.md`.

   **Deep-learning intuition — how a cross-encoder is trained, and why that specific training
   shape produces exactly this failure.** A cross-encoder is not two separate embeddings compared
   by cosine similarity (that's a bi-encoder, see #3). It concatenates `[query ; passage]` into
   one sequence, runs it through a single transformer with full self-attention — every query token
   can attend to every passage token and vice versa — and reduces the final layer (usually the
   `[CLS]` position) through a small head to one relevance score. Training is typically pairwise
   or pointwise: for a query, a known-relevant passage, and one or more hard negatives (often mined
   from a weaker retriever's high-scoring misses), the loss pushes the relevant pair's score above
   the negatives' (margin loss) or toward 1 while negatives go toward 0 (cross-entropy). Two
   consequences follow directly from that shape, not from anything specific to Cohere's model:
   - **Length inflates the score mechanically.** With full cross-attention, a longer passage
     simply offers more tokens for query tokens to find *some* attention signal in. If any
     sub-span is topically adjacent to the query — even loosely — pooling across a longer sequence
     accumulates more of that signal than pooling across one short, precise sentence would. This is
     the documented "verbosity bias" in BERT-style rerankers, and it is exactly the r = **+0.285**
     figure: that's the Pearson correlation coefficient between block length (sentence count) and
     `relevanceScore` across all 910 scored blocks in this project's own data — a moderate, positive,
     measured linear relationship between "how much text" and "how relevant the model says it is,"
     independent of whether the text actually answers the question. (Sec 3.3 of
     `RERANKING_FINAL_SYNTHESIS.md` also checked whether this fully explains the gold/non-gold score
     gap — it doesn't; there's a real relevance signal underneath the length bias, the two effects
     coexist and add.)
   - **The model was never taught that near-identical text can be systematically wrong.** The
     training pairs for a general-purpose reranker come from corpora (web search logs, MS MARCO-style
     passage collections, general QA) where two passages with nearly identical wording essentially
     never occur as a matched "same content, different validity" pair at scale. Nothing in a
     pairwise/pointwise relevance loss ever penalizes "this passage is topically perfect but
     temporally wrong," because that specific axis of hard negative — same company, same section,
     same sentence, one number changed, one year later — does not exist in the model's training
     distribution. SEC 10-K boilerplate is unusually, structurally repetitive year over year in a
     way general web text is not, so the model is being asked to make a discrimination it was never
     shown examples of needing to make. Boilerplate is bad for a cross-encoder specifically because
     it is *long* (triggers the length bias) *and* near-duplicated across a dimension (fiscal year)
     the model has no training signal, and no input field, to condition on at all.

2. **Fixed top-K / top-N cutoff, at either the retrieval or reranking stage.** The default,
   least-questioned choice in most RAG tutorials. Measured here: a single global N cannot serve
   both single-fact questions (where aggressive pruning helped, `RERANKING_FINAL_SYNTHESIS.md`
   Sec 4, Q008) and multi-entity breadth questions (where it silently dropped named companies).
   Matches the published finding that dynamic/adaptive passage selection beats rigid top-K when
   query difficulty is heterogeneous — this corpus's mix of `local` vs `cross_company`/`cross_year`
   questions is exactly that heterogeneity.

   **Deep-learning intuition — where exactly the cutoff stops helping.** A ranked list from either
   the ANN retriever or the reranker is a proxy for "probability this block is relevant," sorted
   descending. A fixed `N` implicitly assumes the *number of relevant items* is constant across
   queries — that the true answer always lives in roughly the same-sized slice of the ranking. It
   doesn't: a `local` single-fact question genuinely has one right sentence, so its "relevant mass"
   is concentrated at rank 1; a `cross_company` question naming four firms needs at least four
   *structurally separate* blocks (this project's own block grouping guarantees a block never spans
   two companies), so its relevant mass is spread across the ranking with a hard floor beneath which
   truncation is mathematically guaranteed to cut a required company (`guidance`-derived floor:
   `N < 4` fails any question needing 4 distinct `(company, year, section)` groups, *no matter how
   good the scoring is*). A single global `N` is therefore not "sometimes too small" — it is being
   asked to be the correct answer to two different questions (how much text does a single fact need
   vs. how many independent entities does this query touch) that have no common right answer. This
   is precisely why the published ranked-list-truncation literature finds *oracle* (per-query)
   cutoffs beat every fixed cutoff by a wide, significant margin, while no fixed constant — 8, 16, or
   otherwise — closes much of that gap: the fix has to be a function of the query, not a better
   constant.

3. **Symmetric bi-encoder query/document embedding** (using the same `input_type` for queries and
   corpus, "same model, so it should be fine"). Textbook-wrong for asymmetric retrieval (query
   is short and interrogative, answer is long and declarative) and was fixed this session
   (`EMBEDDING_INPUT_TYPE_ASYMMETRY.md`). The theory is unambiguous and well-published (Cohere's
   own docs state it explicitly). What's notable is how *small* the measured real-world payoff was
   once fixed: the offline margin check found the correct `search_query` role beat the buggy
   `search_document` role on only 5 of 10 test questions, not a clean sweep — a case where a
   textbook-mandatory fix mattered less in practice than the theory predicts, likely because
   10-K prose's heavy lexical repetition (boilerplate) partially swamps the query/document role
   distinction either way.

   **Deep-learning intuition — the actual training objective, and why fixing it barely moved the
   number.** A bi-encoder like Cohere Embed v4 is one shared transformer tower used twice: once
   conditioned as `search_query`, once as `search_document` (the conditioning is a role signal fed
   in with the input, not a different set of weights). It is trained with a contrastive loss —
   InfoNCE — over batches of `(query_i, passage_i⁺)` pairs, typically with in-batch negatives plus
   mined hard negatives:
   ```
   L_i = -log [ exp(cos(q_i, d_i⁺) / τ) / Σ_j exp(cos(q_i, d_j) / τ) ]
   ```
   where `q_i` is encoded in the query role and every `d_j` (correct and incorrect) is encoded in
   the document role. Read that loss literally: gradient descent only ever rewards the model for
   pulling a **query-role** vector toward its matching **document-role** vector, and pushing it away
   from non-matching document-role vectors. There is no term anywhere in that objective that shapes
   query-role-to-query-role geometry, or document-role-to-document-role geometry — the model is
   never trained on, and has no reason to produce sensible output for, comparing two vectors encoded
   in the *same* role. That is exactly why using `search_document` for both a question and its
   answer (the bug that was fixed) silently converts an asymmetric retrieval problem into a
   same-role passage-similarity problem the model was never asked to be good at.
   The theory is airtight; the muted 5/10 real-world result is best explained by what the fix does
   and does not touch. Financial QA over 10-Ks has unusually high lexical overlap between a question
   and its answer compared to open-domain QA — a question naming a company, a metric, and a year
   will frequently find those same tokens verbatim inside the correct sentence — so a large share of
   "find the right passage" signal here comes from shared vocabulary/entities that a same-role
   (wrong) encoding can still partially exploit; the role correction sharpens something that wasn't
   entirely broken to begin with, on this specific kind of query. It also does nothing at all about
   entry #1's independent failure mode: fixing which *role* a query is encoded in cannot fix the fact
   that many of the retrieved candidates are near-duplicate passages from the wrong fiscal year. Two
   separate bugs were live at once; correcting one and re-measuring end-to-end will always look
   smaller than the theory for that one fix alone would predict, because the other bug is still
   absorbing part of the error budget.

4. **LLM-driven query variant expansion** (rephrasing the user's query into 2-3 semantic variants
   before embedding, to widen recall). Standard query-expansion practice. Implemented in this
   codebase (`VariantPipeline`) but its own design docs flag that nobody has confirmed it earns
   its cost: the retrieval telemetry that could measure `n_hits_per_variant` was only built this
   session, and the honest 3-arm/top-N investigation deliberately ran with variants *off* to keep
   comparisons clean — meaning the variant pipeline's actual contribution is still unmeasured,
   which is itself the finding: a taught-as-standard technique running in production for months
   with no evidence it helps.

5. **Sparse/lexical retrieval fused with dense (BM25-style hybrid search).** The most commonly
   recommended fix for exactly this project's documented failure mode (boilerplate/definitions
   beating numeric answers on pure semantic similarity). Seriously considered and ranked in
   `RETRIEVAL_IMPROVEMENT_STUDY.md` Sec 4 alongside reranking and hybrid fusion, but not adopted
   ahead of fixing three more basic bugs first (the query-embedding role bug, the year-filter bug,
   dedup not checking text) — an example of a well-taught remedy being correctly *deprioritized*
   rather than proven useless, worth distinguishing from the other entries here.

6. **Fine-grained (sentence-level) retrieval granularity.** Published work (Dense X Retrieval,
   EMNLP 2024) shows proposition/sentence-level units outperform passage-level units at a fixed
   compute budget, and this project retrieves at sentence level by design. In isolation this is
   fine. It composes badly with entry #1: a single retrieved sentence, correct as a fact, becomes
   a 1-sentence block that the cross-encoder systematically under-scores (mean 0.161 vs
   0.292-0.364 for 4+-sentence blocks) purely because it is short. Two individually sound choices
   — fine-grained retrieval, cross-encoder reranking — actively undermine each other here.

7. **Context-window neighbor expansion (±N sentences around a hit) as a blanket recall booster.**
   Standard RAG pattern for giving the generator surrounding context. Measured cost here: it
   inflates block length going into the reranker, which (per #1's length bias) makes the
   boilerplate-crowding problem *worse*, not better — and a real implementation bug in the window
   boundary clamp (fixed this session, see `sentence_expander.py`) had been silently dropping many
   expansion windows entirely for months before this investigation's telemetry could even see it.

**The common thread, stated once rather than seven times:** none of these techniques are broken
in general. Every one of them assumes either (a) metadata the model can't see (year, company)
doesn't matter as much as it does in a temporally-repetitive filing corpus, or (b) length and
lexical overlap are reliable relevance signals, which is precisely backwards for boilerplate-heavy
legal/financial prose where the *longest*, most *textually similar* passage is disproportionately
likely to be a repeated disclosure rather than the specific figure being asked about.
