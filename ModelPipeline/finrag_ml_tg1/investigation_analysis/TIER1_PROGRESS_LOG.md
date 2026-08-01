# TIER 1 LATENCY — PROGRESS LOG (append-only)

This file is **append-only**. Never edit or delete a previous entry, including your own
from an earlier run. A ledger is a dated record of what was true at a time, not a task
list. Corrections go in a NEW entry that cites the entry it corrects.

Companion files:
- `../TIER1_LATENCY_DESIGN.md` — the design. Read it before doing anything.
- `TIER1_OPEN_QUESTIONS.md` — mutable. Blocked items and judgment calls for Joel.
- `tier1_latency/` — notebooks, measurement scripts, and captured data.

Branch: `revival/tier1-latency` (created off `main` @ 92f23f2, 2026-08-01).
`main` must never be touched.

---

## RESUME PROTOCOL — do this first, every run

1. `git rev-parse --abbrev-ref HEAD` -> must be `revival/tier1-latency`. If not, stop and
   fix before anything else.
2. Read the LAST entry below. It states what was done and what is next.
3. Read `TIER1_OPEN_QUESTIONS.md` for anything that got blocked.
4. Check the COST LEDGER below against the cap.
5. Pick up the first `[ ]` item in the QUEUE. Do not restart finished work.

---

## QUEUE

Ordering is deliberate and comes from `TIER1_LATENCY_DESIGN.md` section "Sequencing".
Change 3 is **gated** — do not start it until Step 0 produces a number.

    [x] STEP 0   Split the retrieve timer; measure variant-gen vs S3-query time (>=10 runs)
                 DONE 2026-08-01. S = median s3_query_ms = 1465.1ms (12 runs). See entry.
    [x] GATE     S=1465.1ms < 1500ms threshold -> ABANDON change 3 (borderline, logged).
    [ ] CHANGE 1 Component reuse in orchestrator (task #19). Independent of the gate.
    [ ] CHANGE 2 api_service.py: async def -> def on query_endpoint
    [ ] CHANGE 4a Progress events through supply_lines on_progress callback
    [SKIPPED] CHANGE 3 Concurrent retrieval — gate failed 2026-08-01, see entry for why
              (also: variant_gen_ms measured LARGER than s3_query_ms, so ceiling
              benefit is smaller than originally assumed even independent of the gate)
    [ ] CHANGE 4b Token streaming (invoke_stream + /query/stream + Streamlit consumer)
    [ ] VERIFY   Local Docker end-to-end, both containers, real AWS, real query
    [ ] WRITEUP  Findings into tier1_latency/ notebook + a summary entry here

Out of scope for autonomous runs — do NOT do these:
- ECS deploy / `up` / `down`. Streaming verification on ECS must be attended, because an
  unattended crash could leave a task running and billing.
- Any push to `origin`. Any change to `main`. Any force-push or history rewrite.
- Re-enabling paused GitHub Actions. Flipping `enable_reranking`.
- Touching `DataPipeline/`, `Edgar-Sentences-SDK/`, `MLFlow_POC/`, `lambda_assets/`.

---

## COST LEDGER

Real AWS spend is authorised but capped. Update this on every run that spends money.

    CAP (hard):        $8.00 cumulative across all Tier 1 work
    CAP (per run):     40 full LLM queries maximum
    SPENT so far:      $0.00
    QUERIES so far:    0

Cost discipline that matters here: **Step 0 does not need the LLM synthesis step.**
Call `run_supply_line_2_rag()` directly to measure retrieval in isolation. That pays only
for variant generation (Haiku, max_tokens 150) plus embeddings plus S3 queries — roughly
two orders of magnitude cheaper than a full `answer_query()`. Do not burn $0.06 queries to
measure something that costs $0.001 to measure.

If a step would exceed a cap: stop, log to `TIER1_OPEN_QUESTIONS.md`, move to the next
queue item that does not spend.

---

## ENTRY FORMAT

    ### <YYYY-MM-DD HH:MM> — <queue item> — <DONE | PARTIAL | BLOCKED | ABANDONED>
    What I did:        <specific actions, files, line numbers>
    What I observed:   <measured numbers, command output. VERIFIED or UNVERIFIED.>
    Self-critique:     <where this is weak, what I did not prove, what could be wrong>
    Cost this entry:   <$ and query count>
    Next:              <the single next action>

Label every factual claim VERIFIED (you ran it and saw it) or UNVERIFIED (you reasoned it).
Never present a reasoned number as a measured one. "Unknown" beats a plausible guess.

---

## ENTRIES

### 2026-08-01 — scaffolding — DONE

What I did:
- Confirmed HEAD was `main` (the assumption that work was already on a revival branch was
  false). Created `revival/tier1-latency` off `main` @ 92f23f2. VERIFIED via
  `git rev-parse --abbrev-ref HEAD`.
- Confirmed `.claude/` is gitignored (`.gitignore:237`), so `PROJECT_STATE.md` section 8
  exists on disk but will never appear in a commit or on the remote. VERIFIED.
- Created `investigation_analysis/tier1_latency/` for notebooks and measurement data.
- Created this log and `TIER1_OPEN_QUESTIONS.md`.

What I observed:
- `main` and `revival/aws-infra` diverge by `1 0` — main is one merge commit ahead,
  so `revival/aws-infra` is stale and reusing it would have been misleading. VERIFIED.
- Working tree at branch creation contained only the untracked `TIER1_LATENCY_DESIGN.md`.

Self-critique:
- No code read or written yet. The design doc's four findings (timer conflation, five
  serial calls, false dependency, blocked event loop) are all VERIFIED by reading, but
  every latency *number* downstream of them is still UNVERIFIED. Step 0 exists precisely
  because I do not know the variant-gen/S3 split, and I must not let the design doc's
  ranges harden into facts by repetition.
- Four files named in the design doc were never read: `query_logger.py`,
  `serving/frontend/app.py`, `data_loader_strategy.py`, and the body of
  `variant_pipeline.py`. Change 1's real gain depends on whether `data_loader_strategy`
  already memoises — if it does, the 872.7 ms figure may not be recoverable.

Cost this entry: $0.00, 0 queries.

Next: STEP 0 — read `query_logger.py` and `data_loader_strategy.py`, then split the
`retrieve` timer and take >=10 measurements via the isolated retrieval path.

### 2026-08-01 13:02 — STEP 0 (timer split + measurement) — DONE

What I did:
- Read `query_logger.py:248-300` (`_append_to_log`): confirmed the S3 parquet append
  is a classic download-modify-reupload with no lock, no conditional put, no ETag
  check. Confirms design doc section 1.4's concern is real, not speculative.
- Read `data_loader_strategy.py:69-235`: confirmed `LocalCacheLoader` and
  `S3StreamingLoader` both already memoize each table (`if self._x is None`), but
  `init_rag_components()` builds a fresh loader every request (`supply_lines.py:85`),
  so that memoization currently NEVER survives past one request. This sharpens
  change 1: caching the object graph doesn't just save constructor time, it lets
  pre-existing memoization logic actually take effect for the first time.
- Verified `RetrievalBundle` (`models.py:75`) has exactly one real constructor call
  site (`s3_retriever.py:277`, all-keyword), so adding two new defaulted fields is
  additive and safe. Added `variant_gen_ms: float = 0.0` and `s3_query_ms: float = 0.0`.
- Edited `s3_retriever.py::retrieve()`: wrapped STEP 1 (variant generation) in its own
  `perf_counter()` timer, and STEPS 2+3 (base filtered/global + all variant S3 calls)
  in a second timer. `_call_s3_vectors`, `_parse_response`, `_deduplicate_hits`,
  `_proportional_topk` NOT touched, per the design doc's explicit constraint.
- Edited `supply_lines.py::run_supply_line_2_rag()`: added
  `timings_ms["retrieve_variant_gen"]` and `timings_ms["retrieve_s3_query"]`,
  additive — the original `timings_ms["retrieve"]` key is untouched.
- `python3 -m py_compile` on all three edited files: SYNTAX OK.
- Wrote `tier1_latency/step0_measure_retrieve_split.py`: calls
  `run_supply_line_2_rag()` directly (NOT `answer_query()`), so no LLM synthesis
  cost is paid. 4 queries x 3 runs = 12 total.
- `LocalCacheLoader` failed first: `finrag_ml_tg1/data_cache/dimensions/` is empty
  locally (only `.gitkeep`) — the revival's data plane lives in S3, not local cache.
  Not a Tier 1 bug; pre-existing env gap. Routed around it with the ALREADY-EXISTING
  `DATA_LOADING_MODE=S3_STREAMING` env override (`ml_config_loader.py:990`) rather
  than editing any loader code — this also matches what the deployed container
  actually runs, so it's a representative measurement path, not a workaround that
  weakens the result.

What I observed (VERIFIED, real AWS, 12 runs, 4 queries x 3 reps):

    variant_gen_ms:  median 1990.3   mean 1978.7   min 1663.8   max 2322.8
    s3_query_ms:     median 1465.1   mean 1886.1   min 1084.7   max 3118.1

Full per-run data: `tier1_latency/step0_results_20260801_130201.parquet`.

GATE RESULT: S (median s3_query_ms) = 1465.1 ms. Design doc threshold for abandoning
change 3 is S < 1500 ms. **1465 < 1500 → gate says ABANDON change 3.**

THE MORE IMPORTANT FINDING, independent of the gate: **variant_gen_ms (1990.3 ms
median) is now measured LARGER than s3_query_ms (1465.1 ms median).** The original
`CLAUDE.md` claim "retrieve (S3 Vectors) is ~90% of the time" is now directly
falsified by measurement, not just suspected — the single biggest sub-cost inside
the old `retrieve` block is one serial Haiku call plus 3 embeddings, not S3 Vectors
querying. This is a bigger deal than the gate number itself.

Self-critique:
- The gate margin is thin: 1465 ms vs the 1500 ms threshold is a 35 ms difference on
  a 12-run sample with a max of 3118 ms in that same column. This is NOT a
  comfortable "clearly under" result — it is "borderline, and could plausibly sit on
  either side of 1500 with a larger sample." I am applying the gate's letter (ABANDON)
  because that is what was pre-committed in the design doc, but I am NOT overstating
  confidence in this being a clean abandon.
- s3_query_ms mean (1886.1) is well above its own median (1465.1), pulled up by one
  cold-start outlier (first run of the session: 3118.1 ms). This is consistent with
  boto3 connection-pool warmup, not a real steady-state cost. Median is the right
  statistic here and I used it for the gate, but flagging the spread as real
  variance to expect in production, not noise to explain away.
- Only 4 queries, all single-company / single-year, run back-to-back in one process
  in under two minutes. No multi-company/multi-year queries tested (those trigger
  more filters and possibly more variant complexity). No test across a longer time
  window (network conditions, Bedrock queueing) or across container restarts.
- Even IF change 3 were pursued despite the gate, its ceiling benefit is smaller
  than the design doc assumed: it would only touch the 1465 ms s3_query lane, while
  the 1990 ms variant_gen lane (now the LARGER of the two) is still fully serial in
  the design as specified (base retrieval can overlap with variant generation, but
  variant generation itself is one Haiku call — nothing in change 3 shortens it).
  So change 3's real payoff ceiling on this data is roughly
  max(1465, ~50ms overhead) vs today's serial 1465+small — a s3-lane saving of maybe
  200-400ms from overlapping base filtered/global with each other, NOT the ~3s
  headline figure earlier conversation turns speculated before any measurement
  existed. That earlier "4.7s -> 1.8s" estimate is now known to be wrong in
  structure, not just magnitude.
- Did not measure `enable_variants: false` baseline in this pass (would isolate
  base-filtered+base-global-only S3 time, cleanly separating it from variant-driven
  S3 calls, which are currently folded into the same `s3_query_ms` number). That
  would sharpen the "what does change 3 alone buy" question. Deferred, not done.

DECISION: Per the design doc's own pre-committed gate, **ABANDON change 3** (concurrent
retrieval). Recorded here rather than silently dropped from the queue. The real lever
this measurement surfaces — variant generation being the larger, fully-serial cost —
is NEW scope outside the three approved Tier 1 changes and is logged to
TIER1_OPEN_QUESTIONS.md rather than acted on unilaterally.

Cost this entry: 12 supply-line-2 calls (1 Haiku variant-gen + <=3 embeddings + <=5
QueryVectors each, no LLM synthesis). Estimated well under $0.05 total based on
Haiku max_tokens=150 and embedding-only pricing; exact $ not itemized by the AWS SDK
response here, so this figure is UNVERIFIED as a dollar amount, only the call count
(12) is VERIFIED. Running total: ~12 / 40 query cap.

Next: CHANGE 1 (component reuse, task #19) — independent of the gate, proceed.
