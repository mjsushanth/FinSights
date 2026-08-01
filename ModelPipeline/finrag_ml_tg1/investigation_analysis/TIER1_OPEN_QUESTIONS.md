# TIER 1 — OPEN QUESTIONS FOR JOEL

Unlike `TIER1_PROGRESS_LOG.md`, this file is **mutable**. Items get added when blocked and
struck through when resolved.

Rule for autonomous runs: **never end a turn with a question.** If something needs Joel's
judgment, write it here with enough context to answer cold, then move to the next queue
item. Idling is the one unacceptable outcome.

Each item: what is blocked, why it needs a human, what I did instead, and what I would do
under each possible answer — so the answer is a single word, not a conversation.

---

## OPEN

### Q1 — Is a slower first query acceptable in exchange for faster subsequent ones?
**Status:** OPEN, but proceeding under an assumption.
**Context:** Change 1 caches the RAG object graph at module level. The first query in a
fresh container still pays the full ~1,700 ms build; every later one pays zero. On ECS,
"first query after `up`" is exactly the demo query.
**Assumption I am proceeding under:** yes, acceptable — the alternative is warming at
container start, which moves the cost into ECS startup where nobody is watching a spinner.
**If you disagree:** say "warm at startup" and I will call `_get_components()` from a
FastAPI startup hook instead, trading ~1.7 s of container boot for a fast first query.

### Q2 — New scope found by Step 0: variant generation is the larger serial cost, not S3 Vectors
**Status:** OPEN. Not acted on — out of the three approved Tier 1 changes.
**Context:** Step 0 measurement (12 real runs, 2026-08-01, see `TIER1_PROGRESS_LOG.md`)
found `variant_gen_ms` median 1990.3 ms > `s3_query_ms` median 1465.1 ms. The one Haiku
rephrase call + up to 3 Cohere embeddings (`semantic_variants` block, `count: 3`,
`temperature: 0.7`) is now the single largest sub-cost in the old "retrieve" block —
larger than actually querying S3 Vectors. This falsifies the `CLAUDE.md` claim
"`retrieve` (S3 Vectors) is ~90% of the time" — that 90% figure describes the whole
block, most of which is an LLM call, not S3 Vectors itself.
**Why this needs Joel:** fixing this is a quality/design decision, not a mechanical
latency fix like changes 1/2/4a. Three candidate levers, none evaluated here:
  (a) Set `enable_variants: false` — removes ~2s but changes retrieval recall/quality.
      Cannot be decided without the gold set (same caveat as the reranking decision).
  (b) Run variant generation concurrently with base retrieval (this IS partially in
      the original change-3 design already — base retrieval never depended on variant
      generation). Worth revisiting even with change 3 otherwise abandoned, since this
      slice alone doesn't touch `_deduplicate_hits` ordering at all (base hits and
      variant hits are still collected in the same order, just the wall-clock overlaps).
  (c) Reduce `semantic_variants.count` from 3, or drop to a cheaper/faster model for
      the rephrase call — pure cost/quality trade, needs gold-set evidence.
**What I would do under each answer:**
  - "leave it, out of scope for Tier 1" -> no action, close this item.
  - "try (b) only" -> this is a narrower, lower-risk version of change 3 (only
    overlaps variant-gen with base retrieval, doesn't touch the 5-way S3 fan-out) —
    I would design and gate it the same way (ordering-safe, parity-tested with
    `enable_variants: false` as the isolation control) before touching code.
  - "correct the CLAUDE.md claim now" -> low-risk doc fix, I can do this without
    further authorization since it's a factual correction backed by this measurement,
    not a design change. Will do this opportunistically during WRITEUP regardless,
    flagged clearly as a doc correction, not a code change.

---

## RESOLVED

*(none yet)*
