# Embedding Transport Design — Bedrock | Cohere Direct

**Written:** 2026-07-29. **Status:** DESIGN ONLY. No code written, no config changed.
**Supersedes:** `EMBEDDING_PROVIDER_ABSTRACTION_DESIGN.md` (same day, earlier). That draft
proposed an ABC + adapter + factory + normalized exception hierarchy. **That approach was
deliberately rejected** in favour of simplicity: a plain dispatch and one duplicated retry
function per transport. Reasons are recorded in section 4. The verified facts from the earlier
draft are carried forward here, corrected where later checks changed them.

---

## 1. What this solves

AWS Bedrock's Cohere Embed V4 **daily token cap on account `mjsushanth_mlops` is 8,100,000
tokens/day and is not adjustable via any API** (`Adjustable: false` on all four relevant quota
codes; support-case-only; account is on Basic support with a 14h+ unanswered ticket). It has
blocked embedding generation twice. The remaining work does not fit inside that cap.

Cohere's own API runs **the same model at the same price** with **no daily cap**. This design
adds it as a second, selectable transport — carefully, with the model, dimensions and target
table all pinned so nothing else can drift.

---

## 2. Verified facts

Checked empirically today unless labelled otherwise.

### Only one table exists — your confidence signal, confirmed
```
LOCAL  data_cache/embeddings/          -> cohere_1024d  (only entry)
S3     ML_EMBED_ASSETS/EMBED_VECTORS/  -> cohere_1024d/finrag_embeddings_cohere_1024d.parquet
S3     ML_EMBED_ASSETS/S3_VECTORS_STAGING/ -> empty
```
No `cohere_768d`, no `titan_1024d`, ever, in either place. The config's multi-slot machinery has
exactly one live value. **This justifies pinning aggressively** rather than preserving optionality.

### Cost — identical on both transports
$0.12 / 1M text tokens. Bedrock side confirmed from the implied Cost Explorer rate
(`1.1407434 / 9.506195 = 0.120000` exactly); Cohere side from their pricing docs.
**Switching transports changes the quota regime, not the unit cost.**

### Remaining work — measured from the meta table
Eligible = `sentence_token_count <= 1000` (the pipeline's own outlier filter).

| Bin | Eligible | Done | Remaining | Remaining tokens |
|---|---|---|---|---|
| Bin 1 (2006-2016) | 206,959 | 206,959 | 0 | 0 |
| Bin 2 (2017-2021) | 224,196 | 129,600 | 94,596 | 3,694,660 |
| Bin 3 (2022-2025) | 183,492 | 2,644 | 180,848 | 7,162,360 |
| **Total** | | | **275,444** | **10,857,020** |

Cost to finish: **$1.30**. Full 3-bin redo if ever needed: **$2.29** (the cheap safety net).

### Throughput — CORRECTED, and it matters
Cohere's Embed limit is **"2,000 inputs / min"**, verbatim from their docs source — **inputs,
not requests**. An earlier estimate in this project's notes read it as requests/min and was
**wrong by 96x**.

| | Per-minute allowance | Daily cap | Time to finish remaining work |
|---|---|---|---|
| Bedrock (this account) | 100 rpm allowed, 60 used = 5,760 inputs/min | **8.1M tokens** | hard-stops at ~75% -> **multi-day** |
| Cohere direct | 2,000 inputs/min = **~20.8 calls/min** | none published | **~2.3-3.2 h, one sitting** |

So Cohere is actually **3x slower per minute** than AWS allows. The win is not speed — it is
that **there is no wall**. Batches are always exactly 96 texts (verified against yesterday's
log: `(8,640 - 4,800) / 40 batches = 96`), so a request-based limiter converts cleanly:
`max_rpm = 2000/96 x safety`.

### Keys — found, with non-standard names
Present in `.aws_secrets/aws_credentials.env` (modified today, already gitignored at
`.gitignore:215`). Variable **names** only:
```
cohere_direct_apiprod_trialk1        cohere_direct_apiprod_trialk1_nam   <- note: truncated "_nam"
cohere_direct_apiprod_k1             cohere_direct_apiprod_k1_name
cohere_direct_apiprod_k2             cohere_direct_apiprod_k2_name
```
Config must reference **these exact names** — not an invented `COHERE_API_KEY`. My earlier draft
assumed the latter; that was wrong.

### Trial vs production keys — decisive for the plan
| | Cost | Embed rate limit | Monthly cap |
|---|---|---|---|
| Trial | **free** ("evaluation keys (free but limited in usage)") | 2,000 inputs/min | **1,000 API calls / month** |
| Production | paid | 2,000 inputs/min (**identical**) | none |

Two consequences:
1. **The trial key cannot do the bulk run** — 2,870 calls needed vs 1,000/month = 2.9x over.
2. **The trial key is free and rate-identical**, so *all* validation and calibration work costs
   **$0**. Only the bulk run needs the production key.

Budget discipline: 1 call = 96 sentences = 0.1% of the monthly trial allowance. A 50-call
experiment costs 5% of it. Plan experiments in calls, not sentences.

### Environment — no change needed
`cohere 7.0.8` is installed in the **`finsights_revival`** conda env, and **7.0.8 is the latest
release on PyPI** (checked today — nothing newer exists). That env also has polars 1.43.0,
boto3/botocore 1.43.56, pyarrow 22.0.0, mmh3, and `MLConfig()` loads successfully in it
(verified: resolves `cohere.embed-v4:0`, 1024-d, correct vectors path).

**Decision: run from `finsights_revival`. Zero installs, zero updates.** The env we have been
using (`finsight-venv`) does not have `cohere` — do not add it there; use the env that is
already correct.

### Cohere SDK surface — introspected, not guessed
```
cohere.ClientV2.embed(self, model, input_type, texts, images, inputs,
                      max_tokens, output_dimension, embedding_types,
                      truncate, priority, request_options)
```
- Vectors: `resp.embeddings.float_` — **trailing underscore** (pydantic alias for `float`)
- Exact billing: `resp.meta.billed_units.input_tokens` (Bedrock does not return this in-body)
- Errors: `TooManyRequestsError`, `BadRequestError`, `UnauthorizedError`, `InternalServerError`
  all subclass `ApiError`, whose `__init__(headers, status_code, body)` means **`.status_code`
  is always present**

### Three API differences that silently corrupt data if missed
1. **`output_dimension` defaults to 1536.** Valid: 256/512/1024/1536. Omit it and you get 1536-d
   vectors that will not match the index. This is the single highest-risk silent failure here.
2. **`truncate` vocabulary differs.** Bedrock body uses `"RIGHT"`; native v2 uses
   `NONE|START|END`. Passing `"RIGHT"` natively is a bad request.
3. **The SDK retries internally.** `RequestOptions(max_retries=0)` is required, or our rate
   limiter miscounts real requests — the identical trap already fixed on the Bedrock side via
   `get_bedrock_client(max_attempts=1)`.

---

## 3. The root-cause finding — and the central simplification

**`_filter_sentences()` does not exclude already-embedded sentences.** It filters the meta table
by `cik_int` and `report_year` only. The *only* thing that stops the pipeline re-embedding work
it already paid for is the **ephemeral 483 MB scratch checkpoint**. The durable vectors table —
the actual source of truth, sitting in both S3 and local cache — is **never consulted** to decide
what work remains.

That one weakness is the root of every checkpoint worry we have had:

| Symptom | Real cause |
|---|---|
| "What do we do with the 129,600 hanging rows?" | they exist *only* in scratch |
| Deleting a checkpoint is expensive | it would re-embed all 224,196 of Bin 2 |
| Cross-transport contamination risk | scratch is the resume authority, and it is transport-blind |
| The global-path collision bug matters so much | ditto |

### The fix: resume from the vectors table, not the checkpoint
Exclude sentenceIDs already present in the merged vectors table, **in addition to** the
checkpoint. Consequences, all of which are things you asked for:

- The checkpoint becomes **pure crash-insurance: disposable.** Losing it costs at most the last
  <50 batches, never the run.
- **Transport switching becomes safe by construction** — the vectors table is transport-blind, and
  if Step 0 confirms the spaces match, a row is a row.
- **Small hanging remainders just get re-embedded**, exactly as you proposed. Worst case is
  50 batches x 96 texts = 4,800 sentences ~ 192k tokens = **$0.023**. Two cents. Not worth any
  salvage machinery — so we will **not** build an abort-flush.
- **The hotfix script gets a clear, simple job** (section 8).

This is the best change in the whole design because it **removes** a dependency rather than
adding machinery.

---

## 4. Design principles adopted

1. **Pin, don't parameterise.** 1024-d, Cohere Embed v4, one table. Every alternative is
   commented out with a policy note explaining it is not a drop-in option.
2. **One switch, single-purpose.** `transport` selects *only* which API endpoint is called. It
   must never influence dimensions, model, or destination table. Conflating those is exactly what
   created the P0 bug below.
3. **Duplication over abstraction, here.** Two transports with genuinely different error
   vocabularies get two retry functions. An ABC + normalized-exception hierarchy would be more
   elegant and *less* readable, and would put a layer of indirection between us and the one thing
   that has repeatedly bitten us — provider-specific error semantics. Two ~55-line functions we
   can read side by side beat one clever one. The cost (a future retry fix must be applied twice)
   is bounded: there are exactly two transports and one is about to go dormant.
4. **Fail loud on identity, fail safe on transport.** A wrong dimension or model must crash
   immediately. An unrecognised error shape must degrade to today's behaviour, never to something
   new.
5. **Validate free, pay once.** All experiments on the free trial key; production key only for
   the bulk run.

---

## 5. Config design

### The P0 bug this must kill
`ml_config_loader.py:176-178` — for *any* non-Bedrock provider, `embeddings_path()` hardcodes
`provider = 'cohere_768d'`. Flip the old switch and the vectors path resolves to the **768-d**
file instead of the 1024-d one holding all 209,603 existing vectors. Then
`_merge_vectors_table()` finds nothing, hits its own "not found" degradation path, and **seeds a
fresh table** — silently orphaning everything. No error, no warning.

Root cause is **vocabulary**: the word "provider" means two different things in this codebase —
the API vendor (`embedding.default_provider`) and the storage slot
(`data_ml.embeddings.<slot>`). The code conflated them.

**Fix:** separate the words, and make slot resolution explicit rather than inferred.
`provider=None` resolves to a single canonical slot from config; it never looks at the transport.
The explicit-slot callers (Stage 3: `s3vectors_table_preparation.py`,
`stage3_config_validation.py`, `data_preparation.py:212`) keep working untouched.

```yaml
data_ml:
  embeddings:
    canonical_slot: cohere_1024d   # PINNED. The one and only vectors table.
                                   # Verified 2026-07-29: no other slot has ever held data.
    base_path: ML_EMBED_ASSETS/EMBED_VECTORS
    cohere_1024d: { ... unchanged ... }
    # cohere_768d / titan_1024d entries: retained for schema compatibility only.
    # NEVER written to. See embedding policy note 3.
```

### The embedding block

```yaml
# ============================================================================
# EMBEDDING
# ============================================================================
# PROJECT POLICY -- READ BEFORE EDITING ANYTHING IN THIS BLOCK
#
#  1. DIMENSIONS ARE PINNED AT 1024. Every table, index, query path and model
#     call in this project is 1024-d. BOTH APIs default to 1536 and will
#     silently return 1536-d vectors if output_dimension is omitted. Changing
#     1024 anywhere means rebuilding the S3 Vectors index AND re-embedding the
#     entire corpus. It is not a tuning knob.
#  2. THE MODEL IS COHERE EMBED V4, AND NOTHING ELSE. Not Titan, not Cohere
#     v3, not another Cohere v4 variant. Alternatives are commented out on
#     purpose -- they produce DIFFERENT VECTOR SPACES and are not drop-in.
#  3. THERE IS EXACTLY ONE VECTORS TABLE: data_ml.embeddings.cohere_1024d.
#  4. `transport` selects ONLY which API endpoint is called. It must never
#     influence dimensions, model choice, or destination table.
#  5. A future transport change SHOULD arguably get its own table. We have
#     deliberately chosen one shared table, valid ONLY while Step 0 (vector
#     space equivalence) holds. If Step 0 ever fails, revisit this.
# ============================================================================
embedding:

  # ---- THE ONLY SWITCH IN THIS BLOCK ---------------------------------------
  #   bedrock       -> AWS Bedrock InvokeModel, model cohere.embed-v4:0
  #   cohere_direct -> Cohere POST /v2/embed,   model embed-v4.0
  # Same model, same 1024-d space, same $0.12/1M. Differs ONLY in quota regime:
  #   bedrock       8.1M tokens/day HARD CAP (non-adjustable on this account)
  #   cohere_direct no daily cap; 2,000 inputs/min
  transport: bedrock

  # Identity of the embedding space. Shared by BOTH transports, pinned.
  spec:
    dimensions: 1024              # POLICY: pinned. See note 1.
    model_family: cohere_embed_v4 # POLICY: pinned. See note 2.
    input_type: search_document   # corpus ingest; queries use search_query
    max_texts_per_call: 96        # hard API ceiling, both transports
    max_tokens_per_call: 128000
    max_tokens_per_sentence: 1000 # outlier filter

  bedrock:
    region: us-east-1
    model_id: cohere.embed-v4:0
    truncate: RIGHT               # Bedrock vocabulary (native uses END)
    max_rpm: 60                   # account ceiling 100, 40% headroom
    target_tpm: 100000            # account ceiling 150,000
    timeout_seconds: 60
    # NOT OPTIONS -- different vector spaces. See policy note 2.
    # titan_v2:        amazon.titan-embed-text-v2:0
    # cohere_embed_v3: cohere.embed-english-v3

  cohere_direct:
    model_id: embed-v4.0
    truncate: END                 # native vocabulary (Bedrock uses RIGHT)
    # Key env-var names exactly as they appear in
    # .aws_secrets/aws_credentials.env. Values NEVER live in this file.
    # POLICY: trial key is FREE but capped at 1,000 API calls/MONTH -- it
    # CANNOT complete a bulk run (needs ~2,870). Use trial for all experiments
    # and notebooks; switch to prod only for the real run.
    api_key_env_trial: cohere_direct_apiprod_trialk1
    api_key_env_prod:  cohere_direct_apiprod_k1
    use_key: trial                # trial | prod
    max_inputs_per_min: 2000      # documented; IDENTICAL for trial and prod
    rate_safety_factor: 0.9       # -> max_rpm = floor(2000/96*0.9) = 18
    timeout_seconds: 60
    sdk_max_retries: 0            # our retry loop owns retry; do not raise
```

### Startup assertions — fail loud on identity
At pipeline construction, before any API call:
```
assert spec.dimensions == 1024
assert spec.model_family == "cohere_embed_v4"
assert transport in ("bedrock", "cohere_direct")
assert resolved model_id == the pinned id for that transport
assert canonical_slot dimensions == spec.dimensions
```
Cheap, and turns a silent corpus-corrupting misconfiguration into an immediate crash.

---

## 6. Code design

One new module, plus surgical edits. **No ABC, no factory, no shared exception hierarchy.**

### `platform_core/embedding_transports.py` (NEW, ~130 lines)
Holds only what is genuinely transport-specific and shareable:
- `CohereDirectHardStop` / `BedrockHardStop` exceptions (section 7)
- `resolve_transport_spec(config) -> TransportSpec` — a small frozen dataclass carrying the
  resolved, asserted identity (`transport, model_id, dimensions, input_type, truncate,
  max_texts_per_call, max_rpm, target_tpm, timeout_seconds`). Mirrors the existing
  `EmbeddingRuntimeConfig` pattern in `rag_modules_src/utilities/query_embedder_v2.py`.
- `build_cohere_client(config) -> cohere.ClientV2` — key selection (trial vs prod), clear error
  if the env var is missing.
- `validate_vectors(vectors, n_texts, dimensions)` — the one genuinely shared guard, because it
  is identical for both and it is the 1536-d tripwire.

### `platform_core/embedding_generation.py` — edits

Dispatch, deliberately a plain if/else:
```python
def _embed_batch(self, batch):
    """Dispatch to the active transport.

    Deliberately a plain branch, not a provider abstraction. The two
    transports have genuinely different error vocabularies, and each retry
    loop is tuned to its own provider's documented failure modes. See
    EMBEDDING_TRANSPORT_DESIGN.md section 4 for why duplication was chosen.
    """
    if self.spec.transport == "cohere_direct":
        return self._call_cohere_api(batch)
    return self._call_bedrock_api(batch)
```

`_call_bedrock_api()` — **structure unchanged**. Two changes only: the hard-stop check
(section 7), and reading identity from `self.spec` instead of `config.bedrock_*`.

`_call_cohere_api()` — NEW, structurally parallel, ~55 lines:
```python
def _call_cohere_api(self, batch):
    """Cohere /v2/embed with the same backoff shape as _call_bedrock_api.

    Intentionally a near-duplicate. Cohere's error classes and their meanings
    are different enough that sharing one classifier would obscure both.
    """
    texts = [item['text'] for item in batch]
    attempt, delay = 0, 0.5

    while attempt < DEFAULT_MAX_RETRIES:
        self.rate_limiter.acquire()
        try:
            resp = self.cohere_client.embed(
                model=self.spec.model_id,                  # "embed-v4.0"
                input_type=self.spec.input_type,
                texts=texts,
                embedding_types=["float"],
                output_dimension=self.spec.dimensions,     # 1024 -- else 1536
                truncate=self.spec.truncate,               # "END"
                request_options=RequestOptions(
                    timeout_in_seconds=self.spec.timeout_seconds,
                    max_retries=0,                         # our loop owns retry
                ),
            )
            vectors = resp.embeddings.float_               # trailing underscore
            validate_vectors(vectors, len(texts), self.spec.dimensions)
            if resp.meta and resp.meta.billed_units:
                self.billed_tokens += resp.meta.billed_units.input_tokens
            return vectors

        except ApiError as e:
            status = getattr(e, "status_code", None) or 500
            body = str(getattr(e, "body", "")).lower()

            # HARD STOP: monthly/quota exhaustion. Retrying cannot clear it.
            if status in (429, 402, 403) and any(
                    w in body for w in ("month", "quota", "billing", "trial")):
                raise CohereDirectHardStop(
                    f"cohere {status}: {body}") from e

            if status in (408, 429) or status >= 500:      # transient
                attempt += 1
                if attempt >= DEFAULT_MAX_RETRIES:
                    raise
                sleep_time = min(delay + random.random() * 0.25, 4.0)
                print(f"  Retry {attempt}/{DEFAULT_MAX_RETRIES} "
                      f"(cohere {status}), waiting {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                delay *= 2
                continue

            raise                                          # 4xx: fail fast
    raise RuntimeError("retry logic error - exhausted retries without return")
```

Other edits, all small:
- `__init__`: resolve `self.spec` first, run the startup assertions, then build the rate limiter
  from `self.spec.max_rpm`. **`max_rpm=60` must stop being a hardcoded constructor default** — it
  is an AWS-specific number and would over-drive Cohere by 3x.
- `_generate_embeddings_batch()`: exclude sentenceIDs already in the vectors table (section 3);
  call `self._embed_batch(...)`.
- `_update_meta_table()`: provenance from `self.spec.model_id` / `.dimensions`, not
  `config.bedrock_*`. The column will legitimately hold both spellings — honest lineage. Safe:
  `embedding_model` is not part of the S3 Vectors metadata schema, so nothing downstream filters
  on it.
- `CHECKPOINT_PATH` -> `checkpoint_path(transport, filter_scope_hash)`. With section 3 in place
  this is belt-and-braces rather than load-bearing.

---

## 7. Hard-stop design (the "third exception"), in full

You asked for this thoroughly, so here it is from first principles.

### The problem in plain terms
HTTP **429** normally means *"you are going too fast — wait a moment and retry."* Retrying after a
short backoff is the correct, standard response.

AWS reuses the **same 429 and the same exception name** (`ThrottlingException`) for a completely
different situation: *"you have consumed your entire daily allowance."* Retrying that today can
**never** succeed.

Our retry loop cannot tell them apart. So on 2026-07-28 it did the standard thing — 7 attempts
with escalating backoff (0.66s -> 1.20 -> 2.16 -> 4.00 -> 4.00 -> 4.00, capped at 4s) — and then
crashed anyway. Two costs: ~20 wasted seconds, and a crash whose traceback obscures the actual
cause (a quota decision made hours earlier by a previous run).

### The only available discriminator
The message text. We captured both shapes verbatim:
```
daily cap : "Too many tokens per day, please wait before trying again."
transient : "Too many requests, please wait before trying again."   (standard throttle)
```
There is no distinct error code, no distinct HTTP status, no `Retry-After` header to rely on. So
substring matching on the message is not a shortcut — **it is the only signal the API exposes.**

### Making brittleness safe
String matching on error messages is brittle: AWS could reword it. The design makes that
harmless by choosing the direction of failure:

| Scenario | Behaviour | Cost |
|---|---|---|
| Match works | immediate clean abort with a useful message | none |
| AWS rewords, match fails | falls through to the transient path -> retries -> exhausts -> crashes | **~20 s — exactly today's behaviour** |
| False positive (transient wrongly seen as fatal) | would abort a recoverable run | **must not happen** |

So the rule is: **match narrowly, default to transient.** `"tokens per day"` is specific to the
daily cap; an ordinary throttle message does not contain it. And critically — never invert this
into "treat all 429s as fatal," which would abort on ordinary throttles and be far worse than the
current bug.

### What happens on detection
Deliberately minimal:
1. Do **not** retry. Do **not** sleep.
2. Do **not** flush the checkpoint. (Per section 3 the checkpoint is disposable and the vectors
   table is the resume authority; worst case is $0.023 of re-embedding.)
3. Raise a distinct exception, caught once at `run()` level, which prints an operator-facing
   report and exits non-zero:
```
EMBEDDING HALTED - provider quota exhausted (not a bug, not a transient error)

  transport      : bedrock
  reason         : daily token cap (8,100,000/day, non-adjustable)
  embedded this run: 41,280 sentences
  durable total  : 170,880 / 224,196 in scope
  remaining      : 53,316 sentences (~2,138,000 tokens, ~$0.26)
  checkpoint     : <path>  (disposable; safe to delete)

  Next options:
    1. wait for the rolling 24h window to free capacity, re-run unchanged
    2. set embedding.transport: cohere_direct  (no daily cap) and re-run
```
4. **No auto-retry-tomorrow, no CloudWatch introspection inside the pipeline.** "When can I
   retry?" is a separate diagnostic concern (section 8) — the pipeline stays dumb and honest.

### The symmetric case nobody has hit yet — Cohere
This is the part worth flagging: **Cohere has the same structural problem.** The trial key is
capped at **1,000 API calls/month**, and Cohere's docs do **not** state what error that produces
(UNVERIFIED). It is very likely a 429 — the same status as an ordinary rate limit. So the trial
key can produce a *permanent-for-this-month* 429 that looks exactly like *slow down*.

Therefore `_call_cohere_api()` gets the same treatment: a narrow match on
`("month", "quota", "billing", "trial")` across statuses 429/402/403, defaulting to transient.
Same fail-safe direction, same reasoning. Designing this in now costs nothing; discovering it
during a bulk run costs a confusing multi-hour failure.

**Do not try to discover the real message by exhausting the trial cap.** Match defensively and
move on.

---

## 8. Migration sequence — careful, staged, no fast switch

Each step is independently verifiable, and nothing destructive happens before Step 3.

| # | Step | Why / gate |
|---|---|---|
| 0 | **Vector-space equivalence test** (trial key, ~1 call, **$0**) | THE GATE. Re-embed ~20 sentences already in Bin 1 via Cohere direct with identical params; cosine vs stored vectors. `>= 0.9999` -> GO. `< 0.99` -> STOP, one shared table is invalid, fall back to a full 3-bin redo on one transport ($2.29) + move `QueryEmbedderV2` too. |
| 1 | **Config restructure only** — no code, no run | Add `spec`/`transport`/`canonical_slot` + policy comments; leave `transport: bedrock`. Verify: `MLConfig()` loads; `embeddings_path(None)` returns the **cohere_1024d** path; startup assertions pass. |
| 2 | **P0 regression guard** | Assert `embeddings_path(None)` resolves to cohere_1024d under **both** transport values. This is the test that protects the 209,603 existing vectors. |
| 3 | **Hotfix script: fold the checkpoint into the vectors table** | `platform_core/checkpoint_merge_hotfix.py`. Reads the 129,600-row scratch checkpoint, dedupes on `sentenceID`, appends to the cohere_1024d table, writes S3 + local, then prints a before/after audit. After this the durable table holds 339,203 rows and the checkpoint is deletable. **Idempotent, dry-run by default.** |
| 4 | **Resume-from-table change** | Implement section 3. Verify: with the checkpoint deleted, a Bin 2 dry-run reports exactly **94,596** remaining, not 224,196. This is the decisive test that the new resume logic works. |
| 5 | **Code the Cohere path** (`_call_cohere_api`, transports module, hard-stop handling) | Unit-checkable without spending: bad model id -> fast fail; forced dim mismatch -> loud crash. |
| 6 | **Trial calibration run** (trial key, ~20-40 calls, **$0**) | ~2,000-4,000 sentences. Measures the real rate limit empirically (the inputs-vs-requests ambiguity), confirms vectors merge into the existing table, confirms row counts and no duplicate sentenceIDs. |
| 7 | **Bulk run on production key** — finish Bin 2 (94,596) | ~$0.44, ~55 min. Then `EMBEDDING_PROGRESS_LOG.md` section 6 checks: unique IDs, dims 1024, no NaN, S3-vs-local byte match. |
| 8 | **Bin 3** (180,848) | ~$0.86, ~2.5 h. Same checks. |
| 9 | **Serving smoke test** | A real query returns cited hits — confirms query-side Bedrock vectors still retrieve against a mixed-transport corpus. |

Optional side tool: a small `quota_window_report.py` that pulls hourly `AWS/Bedrock`
`InputTokenCount` and prints when the rolling 24h window frees enough capacity. Useful if we ever
go back to Bedrock; explicitly **not** part of the pipeline.

---

## 9. Notebook plan (experiments, persisted and readable)

New folder `platform_core/transport_validation_nbs/`, matching the repo's existing notebook
convention. All on the **free trial key**. Total budget: **< 60 of 1,000 monthly calls (6%)**.

| Notebook | Purpose | Calls | Cost |
|---|---|---|---|
| `01_vector_space_equivalence.ipynb` | Step 0. 20 known Bin-1 sentences re-embedded via Cohere; cosine distribution, min/mean/max; dim assertion; **explicit GO/NO-GO verdict cell** | ~1 | $0 |
| `02_rate_limit_calibration.ipynb` | Resolve inputs-vs-requests empirically: ramp batch rate, record 429s, derive the real sustainable `max_rpm` | ~20-30 | $0 |
| `03_error_shape_probe.ipynb` | Capture real error bodies for bad model id, bad dimension, bad key — so the hard-stop matcher is written against observed strings, not guesses | ~5 | $0 |
| `04_merge_audit.ipynb` | Before/after audit around the hotfix script and the trial run: per-bin counts, dim check, NaN check, duplicate check, provenance mix | 0 | $0 |

Each notebook ends with a markdown summary cell so results are readable without re-running.

---

## 10. What I deliberately did NOT design

- **No provider abstraction / ABC / factory.** Rejected per your direction and section 4.
- **No second table for the new transport.** Acknowledged as arguably correct; deferred, and
  valid only while Step 0 holds. Recorded as policy note 5 in the YAML so the tradeoff is visible
  at the point of change.
- **No abort-flush checkpoint salvage.** Worst case $0.023; not worth the code.
- **No changes to serving.** `QueryEmbedderV2` stays on Bedrock, untouched. It already enforces
  `output_dimension=1024` and validates returned dims. Consolidating it onto the new spec is a
  sensible future cleanup, out of scope now. (Note: it defines its own local
  `EmbeddingProviderError`; the new module uses distinct names to avoid ambiguity.)
- **No changes to Stage 3, the S3 Vectors index, or the KPI supply line.**
- **No multi-key parallelism.** Two production keys exist; using both to double throughput is
  possible but adds concurrency to a deliberately sequential pipeline. Not now.
- **No environment changes.** `cohere 7.0.8` is already the latest; `finsights_revival` is ready.

---

## 11. Open items

1. **`cohere_direct_apiprod_trialk1_nam`** looks truncated (`_nam` vs `_name`). Cosmetic — the
   key-name variable, not the key itself — but worth fixing while we are in that file.
2. **Which production key** — `k1` or `k2`? Design defaults to `k1`; confirm before the bulk run.
3. **Is `co.embed(...)` or `co.v2.embed(...)` correct for `ClientV2`?** Introspection confirms
   `ClientV2.embed` exists with the right signature; Cohere's docs show both spellings in
   different places. Notebook 01 settles it in one call.
4. **Undocumented Cohere daily caps** — none published, but absence of documentation is not
   absence of a limit. Watch during the first bulk run (UNVERIFIED).
5. **Trial-key commercial-use terms** — docs call them "evaluation keys." Fine for validation;
   the bulk run uses the production key regardless.
