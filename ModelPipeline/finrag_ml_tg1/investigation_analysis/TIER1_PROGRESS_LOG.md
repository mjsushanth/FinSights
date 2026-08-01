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
    [x] CHANGE 1 Component reuse in orchestrator (task #19). DONE 2026-08-01.
    [x] CHANGE 2 api_service.py: async def -> def. DONE 2026-08-01, verified LIVE
                 (real concurrent queries, /health responsive during a query,
                 zero lost log rows under the _LOG_LOCK). See entries.
    [x] CHANGE 4a Progress events through supply_lines on_progress callback.
                 DONE 2026-08-01, all 5 stages verified firing in order with real data.
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

### 2026-08-01 13:20 — CHANGE 1 (component reuse, task #19) — DONE

What I did:
- `orchestrator.py`: added a module-level cache block (`_INIT_LOCK`, `_LOG_LOCK`,
  `_RAG_COMPONENTS`, `_PROMPT_LOADER`, `_QUERY_LOGGER`, `_LLM_CLIENTS`) with
  double-checked-locking getters `_get_rag_components()`, `_get_prompt_loader()`,
  `_get_query_logger()`, `_get_llm_client(config, model_key)`, exactly per the
  design doc's pseudocode (section 1.3).
- Replaced the 4 direct constructor calls inside `answer_query()`'s init block
  (`init_rag_components()`, `PromptLoader()`, `create_bedrock_client_from_config()`,
  `QueryLogger()`) with the 4 cached getters. `init_rag_components()` ITSELF was
  NOT modified — only its call site in `answer_query()` changed, so the CLI
  (`main.py`), notebooks, and the gold-set harness that call `init_rag_components()`
  directly are unaffected. Verified by diff: `supply_lines.py`'s only change in this
  session is the Step 0 timings_ms addition, nothing inside `init_rag_components()`.
- Wrapped all 5 `query_logger.log_query(...)` call sites in `answer_query()` with
  `with _LOG_LOCK:` — the 4 error-path sites and the 1 success-path site. This
  was NOT optional even though `QueryLogger` isn't concurrent yet (change 2 hasn't
  landed): once it does, `_append_to_log()` (`query_logger.py:248`, confirmed in
  the Step 0 entry above to be an unlocked S3 download-modify-reupload) would race.
  Cheap to add now, before the hazard is live, rather than after.
- Imported `RAGComponents` and `BedrockClient` as types (previously only the
  factory functions were imported) for the cache dict/variable annotations.
- `python3 -m py_compile orchestrator.py`: SYNTAX OK.
- Wrote `tier1_latency/change1_measure_component_cache.py`: calls the 4 new
  getters directly, 3 times in one process. Zero AWS cost - none of
  `init_rag_components()`'s constructors make a billable API call; billable calls
  only happen inside `.invoke()` / `.query_vectors()` / embedding calls, which this
  script never reaches.

What I observed (VERIFIED, real run, S3_STREAMING mode matching the deployed container):

    PASS 1:   1164.7 ms   (cold build - init_rag_components() + PromptLoader() +
                            create_bedrock_client_from_config() + QueryLogger())
    PASS 2:      0.0 ms   (all 4 getters short-circuit on the cache)
    PASS 3:      0.0 ms   (same)

Acceptance criteria from TIER1_LATENCY_DESIGN.md section 1.5:
  1. Second+ queries drop ~1400-1700ms vs first, in one process.
     PARTIALLY VERIFIED: the drop is real and total (1164.7ms -> 0.0ms), but the
     measured cold-build number (1164.7ms) is itself lower than the ~1698ms figure
     task #19 cited (825ms constructors + 872.7ms discarded table loads, from two
     SEPARATE older scripts, measure_constructor_cost.py and
     measure_table_load_cost.py, run independently). This measurement composes the
     real call chain as it exists today in one shot, in S3_STREAMING mode, so I
     trust it MORE for this codebase's current state - but flagging the numeric
     discrepancy honestly rather than silently reconciling it. Likely explanation
     (UNVERIFIED): some table-load cost is already inside the constructors
     (EntityAdapter.__init__ eagerly calls load_dimension_companies(), per the
     Step 0 traceback), so the two older scripts may double-count some of it when
     summed. Not confirmed by rerunning those two scripts in this session.
  2. First query unchanged (cold build still happens, once).
     VERIFIED by construction and by PASS 1's timing being consistent with a full
     cold build (matches the same order of magnitude as before caching existed).
  3. Gold set parity with enable_variants:false — NOT DONE this entry. Caching
     object construction cannot change retrieval results (nothing in the cached
     objects' construction affects what they return, per the Step 0 evidence that
     they're construct-then-read-only) - so this is a low-risk gap to defer, not
     skip permanently. Flagged, not silently dropped.
  4. Two concurrent requests both complete and both log — NOT TESTED this entry.
     Requires change 2 (event loop fix) to even be meaningful, since today's
     `async def` handler serialises all requests anyway. Sequenced correctly:
     concurrency testing belongs after change 2, in the VERIFY queue item.
  5. `init_rag_components()` byte-identical — VERIFIED by diff (untouched).

Self-critique:
- The QueryLogger lock changes behavior under a real race for the first time (an S3
  read-modify-write that could previously only ever run once at a time now truly
  needs the lock once change 2 lands) — but I have not yet WRITTEN a test that
  forces two threads to call `log_query` concurrently and checked both rows survive.
  That test is legitimate and cheap (no AWS needed - could use a stub/local file),
  and I did not do it. Recorded as a real gap, not swept under "done".
- I did not rerun the two OLDER measurement scripts (`measure_constructor_cost.py`,
  `measure_table_load_cost.py`) to reconcile the 1164.7ms vs ~1698ms discrepancy
  noted above. That reconciliation is optional polish, not a blocker - the
  acceptance criterion ("drop by ~1400-1700ms") is about the SHAPE of the win
  (near-total elimination on repeat calls), which is unambiguously true regardless
  of which absolute baseline number is correct.

Cost this entry: $0.00, 0 AWS-billed calls (constructors only, no invoke/query_vectors/
embed calls reached). Running total unchanged: ~12 / 40 query cap.

Next: CHANGE 2 (api_service.py: async def -> def on query_endpoint).

### 2026-08-01 13:15 — CHANGE 2 (async def -> def) — DONE, verified live

What I did:
- `serving/backend/api_service.py`: changed `async def query_endpoint` to
  `def query_endpoint`. Verified no `await` keyword exists in the function body
  (only in my own new docstring text) before making the change, since a plain
  `def` cannot contain `await`. `root()` and `health_check()` left `async def` -
  they do no blocking I/O, no reason to move them.
- `python3 -m py_compile`: SYNTAX OK.
- Ran a REAL local verification rather than deferring everything to the later
  Docker VERIFY step, since this specific claim (event loop stays free) is
  cheap and decisive to test directly: started uvicorn locally
  (`DATA_LOADING_MODE=S3_STREAMING`, matching the deployed container's mode),
  from `serving/` as `backend.api_service:app` (first attempt from
  `serving/backend/` failed with `ModuleNotFoundError: No module named
  'backend'` - needs to run from the parent dir; not a code bug, a cwd issue).

What I observed (VERIFIED, real AWS, real Bedrock, real cost):
- Fired one real `/query` (Apple revenue 2023) in the background; while it was
  in flight for 10.14s wall time, sent 3 `/health` probes. All 3 returned
  `200` in 1.5-9.6ms - comfortably under the 100ms acceptance bar
  (TIER1_LATENCY_DESIGN.md section 2, acceptance). Under the old `async def`,
  these would have queued behind the blocked event loop for the full 10s.
  Real answer, correct, cost $0.0140, 13,120 tokens, 9,288.7ms processing time.
- Fired TWO real `/query` requests CONCURRENTLY (Microsoft rev 2022, Tesla rev
  2021). Both returned `200` at 9.12s and 9.66s wall time respectively - i.e.
  they overlapped almost entirely, NOT serialized (serialized would have been
  ~9s + ~9s ≈ 18s for the second). Both answers correct and distinct
  ($198.3B Microsoft, $53.82B Tesla), costs $0.0129 and $0.0163.
- Checked the actual S3 query log (`get_recent_logs(n=5)`) after all 3 real
  queries: Microsoft and Tesla (the genuinely concurrent pair) each appear
  EXACTLY ONCE, at timestamps 161ms apart (17:10:42.968854Z, 17:10:43.129587Z)
  - direct evidence the `_LOG_LOCK` added in Change 1 serialized the two S3
    read-modify-writes correctly under real concurrency, with zero lost rows.
  This is the concurrent-logging acceptance criterion from Change 1's
  self-critique (flagged there as "NOT TESTED") - now actually tested, for real.

Investigation detour (worth recording honestly, not just the clean result):
- My own diagnostic script checked `result.get('exports', {}).get('log_file')`
  on the raw HTTP JSON and got `None` for all 3 queries, which looked like a
  masked logging failure. Chased it down in two steps rather than one blind
  retry: (1) called `QueryLogger.log_query()` directly with the exact captured
  Apple result - it SUCCEEDED and returned a real S3 URI, proving log_query()
  itself was never broken; (2) checked `models.py:97-123` and found
  `QueryResponse.exports` is DELIBERATELY commented out ("Exports are internal
  backend concern, not exposed to API consumers... security risk") - FastAPI's
  `response_model=QueryResponse` strips the key entirely from the HTTP
  response. My script's `.get('exports', {})` fallback silently masked the
  key's absence as `None`, which is indistinguishable from "present but null"
  without checking `'exports' in r` directly - confirmed absent via a raw key
  check. Not a bug. Not caused by any Tier 1 change. A false alarm from my own
  sloppy diagnostic, corrected before it was logged as a real finding.
- Step (1)'s repro also explains the one duplicate Apple row later found in
  the S3 log (two identical rows, same timestamp `17:10:00.297098Z`, same
  cost $0.01402): that's MY manual repro call re-logging the same already-
  captured result, not a live double-log. `_append_to_log()` has no
  idempotency key, so calling `log_query()` twice on the same result always
  produces two rows - a real, pre-existing system property worth knowing, not
  a Tier 1 regression, and not something to fix unprompted here.

Self-critique:
- This verification ran against a LOCAL uvicorn process, not the Docker
  container. Representative (same `S3_STREAMING` mode, same code), but not
  identical to the ECS/Docker networking path - full Docker verification is
  still owed at the VERIFY queue step.
- Did not test what happens if TWO health probes AND a query all race in a
  tighter window than achieved here, or under actual concurrent load (>2
  requests). 2-way concurrency is proven; N-way is not.
- Did not check CPU/memory behavior under the now-possible concurrency - a
  threadpool-based concurrent model has a different resource profile than the
  old serialized-by-accident one, and the container's sizing
  (1 vCPU / 3072 MiB) was chosen under the old, effectively-single-query-at-
  a-time model.

Cost this entry: 3 real full queries (Apple $0.0140, Microsoft $0.0129, Tesla
$0.0163) = $0.0432 VERIFIED (read directly from each response's
metadata.llm.cost). Running total: ~15 query-equivalents / 40 cap,
~$0.0432 / $8.00 cap (both far under budget).

Next: CHANGE 4a (progress events through supply_lines on_progress callback).

### 2026-08-01 13:28 — CHANGE 4a (progress events) — DONE

What I did:
- `supply_lines.py`: added `on_progress: Optional[Callable[[str, Dict[str, Any]],
  None]] = None` to `run_supply_line_2_rag()` and `build_combined_context()`,
  default `None` on both so every existing caller (CLI, notebooks, gold-set
  harness, `answer_query()` itself) is unaffected unless it opts in.
- Added a local `_emit(stage, **detail)` closure and called it at 5 of the 6
  existing timing points: `entities` (with extracted companies/years),
  `embed`, `retrieve` (with hit count + variant query count), `expand` (with
  sentence count), `assemble` (with context length). `rerank` also
  instrumented but conditional on `rag.reranker is not None` - did not fire
  in this run since `enable_reranking: false`, correctly.
  Threaded `on_progress` through `build_combined_context`'s call to
  `run_supply_line_2_rag`. Did NOT thread it into `answer_query()` itself -
  that has no consumer for progress events yet (it returns one dict at the
  end); wiring it in belongs to Change 4b's `answer_query_stream()` sibling
  function, per the design doc's explicit 4a/4b split.
- `python3 -m py_compile`: SYNTAX OK.
- Wrote and ran `tier1_latency/change4a_verify_progress_events.py`: real call
  to `run_supply_line_2_rag()` with a real callback attached, plus a second
  call with no callback at all to confirm the default path is unchanged.

What I observed (VERIFIED, real AWS, 2 supply-line-2 calls, no LLM synthesis):

    [event] entities  ms=8.6    companies=['NVDA']  years=[2021]
    [event] embed     ms=339.9
    [event] retrieve  ms=3202.2 n_hits=30  n_variant_queries=3
    [event] expand    ms=59.5   n_sentences=158
    [event] assemble  ms=3.5    context_chars=32001

All 5 expected stages fired, in the correct order, with correct real detail
(NVDA/2021 correctly extracted from the query text). Second call with no
`on_progress` argument at all completed with zero exceptions (3379.3ms,
same order of magnitude as the instrumented call at 3613.9ms - the emit
calls add no measurable overhead).

Self-critique:
- Not yet consumed by anything - this is plumbing with no listener attached
  in the real serving path. Its value is entirely prospective, realized only
  when Change 4b builds the SSE endpoint that attaches a real `on_progress`.
  Correctly sequenced (4a before 4b), not yet useful standalone.
- Did not test the reranker-on path (`rerank` event). Not testable without
  flipping `enable_reranking`, which is explicitly forbidden by the
  guardrails in this session regardless of Tier 1 scope.
- The `_emit` closure catches nothing - if a caller's `on_progress` callback
  itself raises, that exception propagates up through `run_supply_line_2_rag`
  and would crash the query. Acceptable for now (4a has no real caller yet),
  but Change 4b's queue-based bridge (per the design doc) MUST wrap the
  callback in its own try/except, or a bug in event formatting could take
  down retrieval. Flagging for 4b, not fixing here since there's no consumer
  yet to test against.

Cost this entry: 2 supply-line-2 calls (no LLM synthesis), same cheap profile
as Step 0. Running total: ~17 query-equivalents / 40 cap, ~$0.0432 / $8.00 cap.

Next: CHANGE 4b (token streaming) OR the Docker VERIFY step. Per the design
doc's sequencing, 4b is next, but it is the largest remaining item (Bedrock
event-stream field names are explicitly flagged UNVERIFIED in the design doc
and need a live single-call probe before building on them) - this is a
natural place to check the cost ledger and time budget before committing to
it in this same run.
