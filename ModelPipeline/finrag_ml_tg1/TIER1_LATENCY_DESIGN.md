# Tier 1 Latency Design — Component Reuse, Retrieval Concurrency, Streaming

Status: DESIGN ONLY. No code written. Nothing deployed.
Author: design pass, 2026-08-01
Scope: three changes only. Everything else in the system is out of scope.

Companion reading:
- `PIPELINE_LATENCY_ANALYSIS.md` — per-stage breakdown this plan builds on
- `investigation_analysis/EMPIRICAL_METHODS_AND_FINDINGS.md` section 3.5b — the sub-stage table
- `CLAUDE.md` Performance section — the figures this document partially corrects

---

## 0. What reading the code changed

Four findings that invalidate or reshape the original framing. These come from reading
`s3_retriever.py`, `supply_lines.py`, `orchestrator.py`, `bedrock_client.py`,
`api_service.py`, and `ml_config.yaml` — not from estimation.

### 0.1 The `retrieve` timer does not measure only S3 Vectors

`supply_lines.py:241-248` wraps `rag.retriever.retrieve(...)` in a single timer named
`retrieve`. But `S3VectorsRetriever.retrieve()` **STEP 1** (`s3_retriever.py:206-219`)
calls `VariantPipeline.generate()`, which is:

    1 Bedrock Haiku call    (semantic_variants: temperature 0.7, max_tokens 150, count 3)
    3 entity extractions    (one per generated variant)
    3 embedding calls       (Cohere embed-v4 via Bedrock, 1024-d)

All inside the timer. So the measured **4,667 ms is a Haiku round-trip plus three
embedding round-trips plus the S3 queries**, not 4,667 ms of S3 Vectors.

The claim in `CLAUDE.md` that "`retrieve` (S3 Vectors) is ~90% of the time" attributes an
LLM rephrase call and three embedding calls to S3 Vectors. The 90% figure for the *block*
is correct; the attribution to S3 Vectors is not.

**Consequence: the size of the concurrency win in section 3 is currently UNKNOWN.** Step 0
below exists to measure it before spending eight hours on it.

### 0.2 There are five serial S3 queries, not three

From `ml_config.yaml` (`enable_global: true`, `enable_variants: true`, `count: 3`) and the
control flow in `s3_retriever.py`:

    base    filtered  topK=30    <- _retrieve_for_embedding, line 316
    base    global    topK=15    <- _retrieve_for_embedding, line 336   (serial after filtered)
    variant 1 filtered topK=15   <- retrieve() loop, line 243           (serial)
    variant 2 filtered topK=15   <- serial
    variant 3 filtered topK=15   <- serial
    -----------------------------------------
    5 fully serial QueryVectors calls

### 0.3 Base retrieval does not depend on variant generation

This is the largest structural finding. `base_embedding` is a **parameter** of `retrieve()`
— it is already computed before the call (`supply_lines.py:233`). Base filtered and base
global therefore have **no data dependency on variant generation at all**, yet the current
code runs variant generation first (STEP 1) and base retrieval second (STEP 2).

So the win is not merely fan-out; it is removing a false dependency:

    NOW      [ variant gen ] -> [ base f ] -> [ base g ] -> [ v1 ] -> [ v2 ] -> [ v3 ]
    TARGET   lane A: [ base f | base g ]                        (concurrent, starts at t=0)
             lane B: [ variant gen ] -> [ v1 | v2 | v3 ]        (concurrent within itself)
             critical path = max(lane A, lane B)

### 0.4 `async def` on the query endpoint blocks the event loop

`api_service.py:164` is `async def query_endpoint(...)` and calls `answer_query(...)`,
which is fully synchronous and blocks for 9.6 s. A blocking call inside `async def` occupies
the event loop for its whole duration, so:

- exactly one query can be in flight per container, ever
- `GET /health` cannot be served while a query runs (ECS health checks compete with users)
- streaming cannot work — the event loop must be free to flush chunks

This is pre-existing and independent of the three changes, but it is a **prerequisite** for
change 3 and it is a one-word fix (`async def` -> `def`, letting FastAPI run the handler in
its threadpool).

---

## Step 0 — Split the timer before optimising (PREREQUISITE, ~45 min)

Acceptance criterion: a measured breakdown of the 4,667 ms into variant generation versus
S3 queries, over at least 10 real runs.

Change: `s3_retriever.py`, inside `retrieve()`, record two sub-timings and attach them to
the returned `RetrievalBundle` (or emit via the existing telemetry path in
`utilities/retrieval_telemetry.py`, which already receives `timings_ms`).

    # s3_retriever.py, retrieve()
    t0 = perf_counter()
    ... STEP 1 variant generation ...
    timings["variant_gen_ms"] = (perf_counter() - t0) * 1000

    t0 = perf_counter()
    ... STEP 2 + STEP 3 all S3 calls ...
    timings["s3_query_ms"] = (perf_counter() - t0) * 1000

Also instrument `_call_s3_vectors` per call, so we learn the per-call latency and whether
the five calls are uniform or whether `topK=30` filtered dominates.

**Decision gate.** Let `S` = measured `s3_query_ms`.

    S > 2,500 ms   -> change 3 (concurrency) is worth 4-8 h. Proceed.
    S in 1,500-2,500 -> proceed, but expect ~1.2-1.8 s saved, not 3 s.
    S < 1,500 ms   -> ABANDON change 3. The time is in variant generation, and the
                      correct lever is a cheaper/parallel variant path or
                      enable_variants: false, both of which are quality decisions
                      requiring the gold set, not latency work.

This gate is the whole reason to do Step 0. Without it, change 3 is a bet.

---

## Change 1 — Component reuse in the orchestrator (task #19)

Target: eliminate ~1,698 ms/request (825 ms constructors + 872.7 ms discarded table loads).

### 1.1 The defect

`orchestrator.py:142-161` constructs the entire object graph on **every call** to
`answer_query()`:

    config         = MLConfig()                                  # line 144  (singleton, cheap)
    rag_components = init_rag_components()                       # line 148  (EXPENSIVE)
    prompt_loader  = PromptLoader()                              # line 152  (YAML file reads)
    llm_client     = create_bedrock_client_from_config(...)      # line 156  (boto3 client)
    query_logger   = QueryLogger()                               # line 160  (S3/parquet setup)

`init_rag_components()` (`supply_lines.py:68-146`) calls `create_data_loader(config)` at
line 85 and injects that one loader into `EntityAdapter`, `MetricPipeline`,
`SentenceExpander`, and `ContextAssembler`. It also builds a second boto3 client inside
`S3VectorsRetriever.__init__` (`s3_retriever.py:125`). All of it is thrown away when the
request returns.

### 1.2 Why caching is safe here — verified, not assumed

The risk with sharing components across requests is per-request mutable state on `self`.
Checked mechanically across every component in `RAGComponents`:

    grep for `self.<attr> = ...` assignments in any method other than __init__, across:
      entity_adapter.py, sentence_expander.py, context_assembler.py,
      variant_pipeline.py, query_embedder_v2.py, metadata_filters.py,
      metric_pipeline/src/pipeline.py

    RESULT: zero hits in all seven files.

Every component is constructed-then-read-only. `run_supply_line_2_rag()` confirms the usage
shape — every call is `rag.<component>.<method>(query, ...)` returning a value, with all
mutable state in function locals (`timings_ms`, `bundle`, `unique_sents`).

boto3 clients: documented thread-safe for concurrent calls when the client is created once
and shared; only mutations to `meta`/`exceptions` are unsafe, which this code does not do.

**Conclusion: the object graph is safe to build once and share.** This retires the main
risk on change 1.

### 1.3 Design

Module-level memo in `orchestrator.py` with double-checked locking. `init_rag_components()`
itself is **not modified** — so the CLI (`synthesis_pipeline/main.py`), the notebooks, and
the gold-set harness that call it directly are completely unaffected. The cache lives only
in the serving entry point.

    # orchestrator.py, new module-level block

    import threading

    _INIT_LOCK = threading.Lock()
    _COMPONENTS: Optional[RAGComponents] = None
    _PROMPT_LOADER: Optional[PromptLoader] = None
    _QUERY_LOGGER: Optional[QueryLogger] = None
    _LLM_CLIENTS: Dict[Optional[str], BedrockClient] = {}
    _LOG_LOCK = threading.Lock()


    def _get_components() -> RAGComponents:
        """Build the RAG object graph once per process. Thread-safe."""
        global _COMPONENTS
        if _COMPONENTS is None:                 # fast path, no lock contention
            with _INIT_LOCK:
                if _COMPONENTS is None:         # re-check under lock
                    _COMPONENTS = init_rag_components()
        return _COMPONENTS


    def _get_llm_client(config, model_key: Optional[str]) -> BedrockClient:
        """One client per model_key. model_key varies per request, so this is keyed."""
        if model_key not in _LLM_CLIENTS:
            with _INIT_LOCK:
                if model_key not in _LLM_CLIENTS:
                    _LLM_CLIENTS[model_key] = create_bedrock_client_from_config(
                        config, model_key
                    )
        return _LLM_CLIENTS[model_key]

`_get_prompt_loader()` and `_get_query_logger()` follow the same shape as `_get_components()`.

Then `orchestrator.py:142-161` becomes:

    config         = MLConfig()                       # already a singleton, leave as-is
    rag_components = _get_components()
    prompt_loader  = _get_prompt_loader()
    llm_client     = _get_llm_client(config, model_key)
    query_logger   = _get_query_logger()

Diff size: roughly 40 added lines, 4 changed lines, in one file.

### 1.4 The one open risk: QueryLogger concurrency

`QueryLogger.log_query()` appends to `query_logs.parquet` in S3. Two concurrent requests
appending to the same object is a read-modify-write race — last writer wins, one query's
log is silently lost.

Today this cannot happen (section 0.4: the event loop serialises everything). After the
0.4 fix it can. Mitigation, chosen for being minimal rather than clever: wrap the two
`log_query` call sites in `answer_query` with `_LOG_LOCK`. Logging is off the critical path
for perceived latency, so serialising it costs nothing that matters.

`query_logger.py` has NOT been read in this design pass. Read it before implementing to
confirm the append is in fact read-modify-write and that there is no existing lock.

### 1.5 Acceptance criteria

1. `processing_time_ms` on the **second and subsequent** queries in one process drops by
   1,400-1,700 ms versus the first.
2. First query is unchanged (cold build still happens, just once).
3. Gold set: identical answers to pre-change on a fixed set with `enable_variants: false`.
4. Two concurrent requests both produce complete, correct responses, and both appear in
   `query_logs.parquet`.
5. `init_rag_components()` is byte-identical to before. The CLI still runs.

### 1.6 Effort and risk

2-3 hours. Low risk. Single file. Fully reversible. **Do this one first regardless of the
Step 0 outcome** — it is already measured, already diagnosed, and independent of everything
else.

---

## Change 2 — Free the event loop (PREREQUISITE for change 4, ~15 min)

`api_service.py:164`:

    -@app.post("/query", response_model=QueryResponse, tags=["Query"])
    -async def query_endpoint(request: QueryRequest):
    +@app.post("/query", response_model=QueryResponse, tags=["Query"])
    +def query_endpoint(request: QueryRequest):

FastAPI runs a non-`async` handler in its threadpool, so the event loop stays free.
`GET /health` becomes answerable during a query, and concurrent queries become genuinely
concurrent — which is exactly why change 1's thread-safety verification had to come first.

Acceptance: `curl /health` returns in under 100 ms while a query is in flight.

Note: this makes real concurrency possible, which raises the unauthenticated-endpoint spend
question (no rate limit, no auth, real Bedrock cost per query). Out of scope here, but it
moves from theoretical to live. Flagging, not fixing.

---

## Change 3 — Concurrent retrieval (GATED on Step 0)

### 3.1 Design

Restructure `S3VectorsRetriever.retrieve()` into two concurrent lanes, per section 0.3.
`_call_s3_vectors`, `_parse_response`, `_deduplicate_hits`, and `_proportional_topk` are
**not modified**. Only the orchestration inside `retrieve()` changes.

    def retrieve(self, base_embedding, base_query, filtered_filters, global_filters):
        with ThreadPoolExecutor(max_workers=8) as pool:

            # Lane A: base retrieval. No dependency on variants. Starts immediately.
            fut_base = pool.submit(
                self._retrieve_for_embedding,
                embedding=base_embedding,
                filtered_filters=filtered_filters,
                global_filters=global_filters,
                variant_id=0,
                enable_global=self.enable_global,
                top_k_filtered=self.top_k_filtered,
                top_k_global=self.top_k_global,
            )

            # Lane B: variant generation is serial (one LLM call), then fan out.
            variant_queries, variant_embeddings = [], []
            if self.enable_variants:
                try:
                    variant_queries, variant_embeddings = \
                        self.variant_pipeline.generate(base_query)
                except Exception:
                    logger.error(...)   # existing graceful-degradation behaviour

            fut_variants = [
                pool.submit(
                    self._retrieve_for_embedding,
                    embedding=var_emb,
                    filtered_filters=filtered_filters,
                    global_filters=None,
                    variant_id=i,
                    enable_global=False,
                    top_k_filtered=self.top_k_filtered_variants,
                    top_k_global=0,
                )
                for i, var_emb in enumerate(variant_embeddings, start=1)
            ]

            # ORDERED collection - see 3.2. Never as_completed().
            all_hits = list(fut_base.result())
            for fut in fut_variants:
                all_hits.extend(fut.result())

        union_hits = self._deduplicate_hits(all_hits)
        ... bundle assembly unchanged ...

Optional second-order win, only if Step 0 shows base filtered+global are individually slow:
push the filtered/global split inside `_retrieve_for_embedding` into the pool too. Deferred
— it complicates the ordering guarantee below for a smaller gain.

### 3.2 Why this preserves results exactly — parity by construction

`_deduplicate_hits` (`s3_retriever.py:458`) is **order-sensitive in two places**:

1. `best = min(hits, key=lambda h: h.distance)` — `min` returns the *first* minimum, so
   on an exact distance tie the winner depends on list order. That changes the surviving
   hit's singular `.source` / `.variant_id` fields.
2. `deduped.sort(key=lambda h: h.distance)` — Python's sort is stable, so ties retain
   pre-sort order, which is `defaultdict` insertion order, which is input order.

Exact float ties are not hypothetical in this corpus: 10-K risk-factor boilerplate repeats
near-verbatim across years, so near-duplicate sentences with identical distances are
plausible. If ties land at the `max_hits_before_expansion: 30` cutoff, `_proportional_topk`
could select a different subset.

**The fix is the collection order, not a tie-breaker.** Submitting in a fixed order and
collecting via `fut.result()` in that same submission order — base filtered, base global,
v1, v2, v3 — reproduces the serial `all_hits` list *element for element*. Every downstream
stage then sees identical input and produces identical output.

This is why the design forbids `as_completed()`. Using it would make results depend on
network jitter, which is precisely the class of bug that is invisible in testing and
surfaces as unexplained answer drift.

### 3.3 How to actually test parity, given nondeterminism already present

`semantic_variants.temperature: 0.7` means variant queries differ run to run, so variant
embeddings differ, so hits differ. **Exact parity across two runs is already impossible
with variants ON.** Any "results changed" test with variants on measures the LLM's
sampling, not the concurrency change.

So the parity gate is two-phase:

    Phase A - DETERMINISTIC (this is the real gate)
      Set enable_variants: false. Only base filtered + global run, both deterministic.
      Run the gold set serially, capture ordered (sentence_id, embedding_id, distance)
      per query. Apply the change. Re-run. Assert byte-identical sequences.
      This isolates the concurrency change completely.

    Phase B - AGGREGATE (sanity, not proof)
      Restore enable_variants: true. Run the gold set N=5 times before and after.
      Compare distributions of hit count, recall@k, and the off-year contamination rate
      already defined in investigation_analysis/RERANKING_FINAL_SYNTHESIS.md.
      Assert no distributional shift. Cannot assert equality, and should not claim to.

### 3.4 Thread-safety specifics

- `self.s3v_client` is created once in `__init__` (line 125) and only has `query_vectors`
  called on it. Documented-safe boto3 usage.
- Default botocore `max_pool_connections` is 10; peak concurrency here is 5. Headroom is
  adequate. If `semantic_variants.count` is ever raised above 8, pass
  `botocore.config.Config(max_pool_connections=...)` at client construction.
- `_parse_response` reads `self.min_similarity` only. No writes.
- Existing per-call `try/except` graceful degradation is preserved: an exception inside a
  worker surfaces at `fut.result()`, so wrap each `.result()` to keep today's
  "empty list on failure, do not crash the pipeline" behaviour.
- `ThreadPoolExecutor` is created and torn down per call. At this QPS the ~1 ms cost is
  irrelevant and it avoids a module-global pool outliving a request.

### 3.5 Acceptance criteria

1. Phase A parity: byte-identical hit sequences, variants off.
2. `s3_query_ms` (from Step 0) drops to roughly the slowest single call.
3. Phase B: no distributional shift in recall@k or contamination rate.
4. A forced S3 failure on one lane still yields a usable answer from the others.

### 3.6 Effort and risk

4-8 hours including both test phases. **Medium risk** — the only change in this plan that
can alter answers. Gated on Step 0. Abandon without regret if `S < 1,500 ms`.

---

## Change 4 — Streaming (progress events, then tokens)

Split deliberately into 4a and 4b. 4a carries almost no risk and delivers most of the
perceived benefit; 4b is the polish.

### 4.0 The blocker found in `bedrock_client.py`

Two facts change the design:

1. `invoke()` uses `self.client.invoke_model(...)` (line 151) with the raw Anthropic
   messages body, **not** the Converse API. The streaming counterpart is therefore
   `invoke_model_with_response_stream`, not `converse_stream`. Migrating to Converse is a
   larger, separate change and is out of scope.
2. **`clean_llm_response(raw_content)` at line 163 runs on the complete response text.**
   A response cannot be cleaned before it has fully arrived. This is the central design
   constraint on token streaming, and it is easy to miss until it produces mangled output.

Options considered for (2):

    (a) Stream raw tokens, then emit one final "replace" event with the cleaned text.
        Simple, no cleaner rewrite, no divergence between shown and logged text.
        Cost: a possible visible re-render at the end.
    (b) Buffer to safe boundaries (newline) and clean each flush.
        Requires the cleaner to be chunk-idempotent. It was not written to be.
    (c) Never clean streamed output; clean only the logged copy.
        Rejected: what the user sees and what is logged would differ.

**Chosen: (a).** And it is cheap to de-risk — `bedrock_client.py:164-166` already prints raw
versus cleaned length on every call, so the logs can tell us how often the cleaner changes
anything before we build this. If the diff is usually nil, the re-render is invisible.

### 4a. Progress events (low risk, high perceived value)

The instrumentation already exists — `run_supply_line_2_rag` records `timings_ms` at six
points (`supply_lines.py:224-269`). Add an optional callback that fires at those same
points. Default `None` means byte-identical behaviour for every existing caller.

    # supply_lines.py signature additions (default None => no behaviour change)
    def run_supply_line_2_rag(
        query: str,
        rag: RAGComponents,
        on_progress: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Tuple[...]:

        def _emit(stage: str, **detail: Any) -> None:
            if on_progress is not None:
                on_progress(stage, detail)

        ...
        timings_ms["embed"] = (perf_counter() - t0) * 1000
        _emit("embed", ms=timings_ms["embed"])          # <- one added line per stage

Six added `_emit(...)` lines plus the helper. `build_combined_context` threads the callback
through. No control flow changes.

Event protocol, newline-delimited JSON over SSE:

    {"type":"stage","stage":"entities","ms":11,"detail":"AAPL, 2023"}
    {"type":"stage","stage":"embed","ms":338}
    {"type":"stage","stage":"variants","ms":1204,"detail":"3 variants"}
    {"type":"stage","stage":"retrieve","ms":2610,"detail":"38 hits / 3 filings"}
    {"type":"stage","stage":"assemble","ms":47,"detail":"11,204 chars"}
    {"type":"token","text":"Apple"}
    {"type":"replace","text":"<cleaned full answer>"}
    {"type":"done","metadata":{...}}
    {"type":"error","error":"...","stage":"retrieval"}

### 4b. Token streaming

New method on `BedrockClient`, alongside `invoke()` — `invoke()` is **not** modified, so the
CLI, the batch harness, and `answer_query()` are untouched:

    def invoke_stream(self, system: str, user: str) -> Iterator[Tuple[str, Any]]:
        """Yield ("text", str) per delta, then one ("final", dict) matching invoke()'s
        return shape so response packaging and cost tracking are unchanged."""
        body = { ... identical to invoke() ... }
        response = self.client.invoke_model_with_response_stream(
            modelId=self.model_id, body=json.dumps(body)
        )
        input_tokens = output_tokens = 0
        stop_reason = "unknown"
        parts: List[str] = []

        for event in response["body"]:
            payload = json.loads(event["chunk"]["bytes"])
            kind = payload.get("type")
            if kind == "message_start":
                input_tokens = payload["message"]["usage"]["input_tokens"]
            elif kind == "content_block_delta":
                text = payload["delta"].get("text", "")
                parts.append(text)
                yield ("text", text)
            elif kind == "message_delta":
                output_tokens = payload["usage"]["output_tokens"]
                stop_reason = payload["delta"].get("stop_reason", stop_reason)

        raw = "".join(parts)
        yield ("final", {
            "content": clean_llm_response(raw, log_changes=True),
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "cost": self._calculate_cost(input_tokens, output_tokens),
            "model_id": self.model_id,
            "stop_reason": stop_reason,
        })

TO VERIFY AT IMPLEMENTATION TIME: the exact event `type` strings and the location of
`usage` in the Bedrock event stream for Haiku 4.5. The structure above reflects the
Anthropic messages streaming format; confirm against a live single-call probe before
building on it. Do not assume.

New orchestrator function, sibling to `answer_query()` — which is **not** modified:

    def answer_query_stream(query, model_root, ...) -> Iterator[Dict[str, Any]]:
        """Same pipeline as answer_query, yielded as events instead of returned as a dict.
        Reuses _get_components() etc. from change 1."""
        # 1. yield stage events via on_progress -> a queue.Queue, drained here
        # 2. yield {"type":"token"} per ("text", ...) from invoke_stream
        # 3. on ("final", ...): build the SAME create_success_response() dict,
        #    call query_logger.log_query() under _LOG_LOCK, then yield
        #    {"type":"replace"} and {"type":"done", "metadata": ...}
        # 4. every existing except-block maps to {"type":"error","stage": ...}

Note the plumbing detail: `on_progress` is a synchronous callback fired deep inside the
call stack, while the generator needs to *yield* from the top. A `queue.Queue` written by
the callback and drained by the generator is the straightforward bridge; the alternative is
running `build_combined_context` in a worker thread and draining the queue until it
completes. The latter is cleaner and composes with change 2's threadpool handler.

New FastAPI endpoint. `/query` is left exactly as it is, so the Streamlit UI can fall back
and the eval harness is unaffected:

    @app.post("/query/stream", tags=["Query"])
    def query_stream_endpoint(request: QueryRequest):
        def event_source() -> Iterator[str]:
            for event in answer_query_stream(...):
                yield f"data: {json.dumps(event)}\n\n"
        return StreamingResponse(event_source(), media_type="text/event-stream")

Streamlit side (`serving/frontend/app.py`): consume with `requests`/`httpx`
`stream=True`, and drive two widgets from one loop — an `st.status()` for stage events and
an `st.empty()` accumulating token text. `st.write_stream()` alone is insufficient because
it consumes a pure text generator and this stream is multiplexed.

### 4c. Verification requires a real deploy

Streaming behaves differently in a container than on localhost. Must confirm on ECS:

- uvicorn does not buffer the SSE response
- Streamlit's rerun cycle does not restart the request mid-stream
- no intermediate buffering — helped here by the architecture having **no ALB**; the
  browser talks to Streamlit and Streamlit talks to FastAPI over localhost

Cost: one `up`, a handful of queries, one `down`. Roughly 30 minutes of task runtime,
a few cents of Fargate plus real Bedrock spend per query.

### 4d. Acceptance criteria

1. First stage event reaches the browser within ~500 ms of submit.
2. First token appears at roughly `retrieval_complete + LLM TTFT`, not at total completion.
3. Final answer text is identical to what non-streaming `/query` returns for the same
   query, variants off.
4. `cost`, `input_tokens`, `output_tokens` in the `done` event match the non-streaming path.
5. The query still lands in `query_logs.parquet` exactly once.
6. `/query` still works unchanged; the CLI still works unchanged.

### 4e. Effort and risk

4a: 2-3 hours, low risk. 4b: 4-6 hours, medium-low. Verification: 1 hour including deploy.

---

## Sequencing

    Step 0   Split the retrieve timer                    45 min   -> gates change 3
    Change 1 Component reuse (task #19)                  2-3 h    -> independent, do first
    Change 2 async def -> def                            15 min   -> gates change 4
    Change 4a Progress events                            2-3 h    -> best value-per-risk
    Change 3 Concurrent retrieval  [IF Step 0 passes]    4-8 h    -> only answer-affecting one
    Change 4b Token streaming                            4-6 h
    Verify   Deploy, measure, tear down                  1 h

Total if Step 0 passes the gate: roughly two days. If it fails, roughly one day and a
documented finding explaining why the retrieval concurrency work was not done — which is
a better artifact than the code would have been.

## Expected outcome (honest ranges, not a single number)

    Today                              9.6 s blank, then everything at once
    After change 1                     ~7.9 s blank
    After 1 + 2 + 4a                   ~0.5 s to first feedback, ~7.9 s to answer
    After 1 + 2 + 4a + 4b              ~0.5 s feedback, first token ~5 s
    After all, if change 3 lands       ~0.5 s feedback, first token ~3-4 s

The first-token figures depend on Step 0's measurement and on Bedrock's own TTFT, neither
of which is known yet. They are ranges, not commitments.

## Files touched

    finrag_ml_tg1/rag_modules_src/rag_pipeline/s3_retriever.py       Step 0, change 3
    finrag_ml_tg1/rag_modules_src/synthesis_pipeline/orchestrator.py change 1, 4b
    finrag_ml_tg1/rag_modules_src/synthesis_pipeline/supply_lines.py change 4a
    finrag_ml_tg1/rag_modules_src/synthesis_pipeline/bedrock_client.py change 4b
    serving/backend/api_service.py                                   change 2, 4b
    serving/frontend/app.py                                          change 4b

Explicitly NOT touched: `init_rag_components()`, `BedrockClient.invoke()`, `answer_query()`,
`_deduplicate_hits()`, `_proportional_topk()`, `_call_s3_vectors()`, `POST /query`,
`ml_config.yaml` (except the temporary `enable_variants` toggle during Phase A testing,
reverted after), `enable_reranking`, `DataPipeline/`, `Edgar-Sentences-SDK/`, `MLFlow_POC/`,
`lambda_assets/`.

## Not read during this design pass — read before implementing

    query_logger.py                 is the parquet append read-modify-write? existing lock?
    serving/frontend/app.py         current call site and widget structure
    data_loader_strategy.py         does it already memoise? affects change 1's real gain
    variant_pipeline.py             full body; only generate()'s docstring and fast path read

## Pre-existing issues found, flagged not fixed

Per the repo's surgical-changes rule, these are recorded and left alone:

1. `bedrock_client.py:164-166` — three `print()` calls in library code, against the
   project's own "never print() in library code" rule.
2. `orchestrator.py:430` — `print()` in `answer_query_batch`.
3. `CLAUDE.md` Performance section attributes the whole `retrieve` block to S3 Vectors
   (section 0.1 above). Worth correcting once Step 0 produces the real split.
4. `orchestrator.py` `answer_query` takes `model_root: Path` and never uses it. Callers
   including `api_service.py:196` pass it faithfully.
5. No rate limit or spend ceiling on the unauthenticated `/query` endpoint. Change 2 makes
   concurrent abuse practically reachable.
