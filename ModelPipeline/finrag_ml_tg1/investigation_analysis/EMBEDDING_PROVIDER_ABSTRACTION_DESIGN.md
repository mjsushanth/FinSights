# Embedding Provider Abstraction — Design (Bedrock | Direct Cohere)

> ## SUPERSEDED — DO NOT IMPLEMENT THIS DOCUMENT
> **Replaced by `EMBEDDING_TRANSPORT_DESIGN.md` (same day, later).** The approach below —
> an ABC + two adapters + factory + normalized exception hierarchy — was **deliberately
> rejected** in favour of a simpler design: a plain if/else dispatch with one duplicated
> retry function per transport, plus project-wide pinning of 1024-d / Cohere Embed v4 /
> one table. See section 4 of the replacement doc for the reasoning.
>
> Two facts in this document were later found **wrong** and are corrected in the replacement:
> - Cohere's Embed limit is **2,000 inputs/min, not requests/min** (this doc's throughput
>   estimate was off by 96x).
> - The API key env var is **not** `COHERE_API_KEY`; the real names are
>   `cohere_direct_apiprod_{trialk1,k1,k2}`.
>
> Retained only as a record of the rejected alternative and its verified-fact gathering.

**Written:** 2026-07-29. **Status:** SUPERSEDED. Nothing was implemented from it.
**Problem it solves:** AWS Bedrock's Cohere Embed V4 daily token cap on account
`mjsushanth_mlops` is **8,100,000 tokens/day and non-adjustable via API**. It has now
blocked embedding generation twice (Bin 1 tail, then Bin 2 at 57.8%). The remaining work
does not fit inside that cap. This design adds a **selectable second transport** — Cohere's
own API — behind one small interface, so the same pipeline can finish the job without the
cap, at identical cost.

**Companion docs:** `EMBEDDING_PROGRESS_LOG.md` (run state), `EMBEDDINGS_VECTORS_REVIVAL_PLAN.md`
(Stage 3 onward), `.claude/PROJECT_STATE.md` (roadmap).

---

## 1. Verified facts this design rests on

Everything below was checked empirically today, not assumed. Labelled where it wasn't.

### Cost — identical on both transports
| | Rate | Source |
|---|---|---|
| Bedrock `cohere.embed-v4:0` | $0.12 / 1M tokens | CE implied rate `1.1407434 / 9.506195 = 0.120000` exactly |
| Cohere native `embed-v4.0` | $0.12 / 1M text tokens | Cohere docs (+3 independent trackers) |

**Switching transports does not change unit cost.** It only changes the quota regime.

### Quotas — the entire reason to switch
| | Bedrock (applied) | Bedrock (AWS default) | Cohere production key |
|---|---|---|---|
| Daily tokens | **8,100,000** | 216,000,000 | none published (UNVERIFIED — absence of docs is not absence of a cap) |
| Requests/min | 100 | 1,000 | 2,000 |
| Adjustable via API? | **No** (`Adjustable: false`) | — | n/a (email support) |

`aws service-quotas request-service-quota-increase` returns
`IllegalArgumentException: quota is not adjustable` for all four relevant quota codes
(`L-F1BB08BB`, `L-795ADAB0`, `L-BE5FD99B`, `L-EB8C1F30`). Support-case-only, and the account
is on **Basic support** (`aws support describe-cases` -> `SubscriptionRequiredException`),
14h+ unanswered.

### Remaining work — measured from the actual meta table
Eligible = `sentence_token_count <= 1000` (the pipeline's own outlier filter).

| Bin | Eligible | Done | Remaining | Remaining tokens |
|---|---|---|---|---|
| Bin 1 (2006-2016) | 206,959 | 206,959 | 0 | 0 |
| Bin 2 (2017-2021) | 224,196 | 129,600 | 94,596 | 3,694,660 |
| Bin 3 (2022-2025) | 183,492 | 2,644 | 180,848 | 7,162,360 |
| **Total** | | | **275,444** | **10,857,020** |

- Cost to finish: **$1.30**
- vs AWS daily cap: **1.34x** the cap -> guaranteed 2+ more days of stop/start
- API calls needed at 96 texts/call: **~2,870**
- Wall time: the pipeline is **sequential** (one call in flight), so at the ~1.75s/batch
  observed yesterday this is **~85 minutes — one sitting, not days.** Cohere's 2,000 rpm
  ceiling is not the binding constraint (we would use ~34 rpm of it); it simply means *no
  throttling and no daily wall*, which is the entire point. Do not read 2,000 rpm as a speed
  promise — realizing it would require concurrency this pipeline deliberately does not have.
- Full 3-bin redo, if ever needed: 19,111,042 tokens = **$2.29** (cheap safety net)

### Correction to yesterday's cost conclusion
Yesterday's note said the pipeline "undercounts the real bill by 15.2%, budget ~$1.15/bin".
The arithmetic was right but the interpretation was wrong. Reconciled exactly today:

```
CloudWatch on-demand  (UTC 2026-07-28)  9,277,163
CloudWatch cross-region                   229,032
                                       -----------
total                                   9,506,195
Cost Explorer UsageQuantity x 1M        9,506,195   <- EXACT MATCH
```
The delta vs the pipeline's tracked 8,254,022 is **not per-run waste**. A CE daily row
aggregates *every* run in that UTC day: the cross-region experiment (229,032) plus the
aborted Bin 2 first attempt, ad-hoc test embeds, and billed-but-discarded retries
(1,023,141 combined). Per-bin cost should be estimated from token counts (as in the table
above), **not** by scaling a daily CE row. Real remaining cost is **$1.30, not ~$2.30**.

Also worth carrying forward: EDT/UTC skew. Bin 1 ran 2026-07-27 evening EDT, which is
2026-07-28 UTC — that is why it appeared on the "07-28" CE row.

### Cohere SDK surface — introspected, not guessed
`cohere 7.0.8` is **already installed in the `finsights_revival` conda env**, which also
has polars 1.43.0, boto3/botocore 1.43.56, pyarrow 22.0.0, mmh3. **No installs needed** —
this env can run the whole pipeline. (The env we have been running, `finsight-venv`, does
*not* have `cohere`.)

```
cohere.ClientV2.embed(self, model, input_type, texts, images, inputs,
                      max_tokens, output_dimension, embedding_types,
                      truncate, priority, request_options)
```
- Response: `EmbedByTypeResponse(response_type, id, embeddings, texts, images, meta)`
- Vectors: `resp.embeddings.float_` — **trailing underscore** (field alias is `float`)
- Exact billing: `resp.meta.billed_units.input_tokens` — Bedrock does not give this in-body
- Errors: `TooManyRequestsError`, `BadRequestError`, `UnauthorizedError`,
  `InternalServerError` **all subclass `ApiError`**, and
  `ApiError.__init__(headers, status_code, body)` -> **`.status_code` always available**

That last point is the load-bearing one: the existing HTTP-status-based retry
classification transfers 1:1 to Cohere. No new classification philosophy needed.

### Three API differences that will silently corrupt data if missed
1. **`output_dimension` defaults to 1536**, valid values 256/512/1024/1536. Must pass
   `1024` explicitly or vectors mismatch the 1024-d S3 Vectors index. (Same trap already
   documented for Bedrock in `CLAUDE.md`.)
2. **`truncate` vocabulary differs**: Bedrock body uses `"RIGHT"`; native v2 API uses
   `NONE|START|END`. Passing `"RIGHT"` natively is a bad request.
3. **The SDK retries internally.** `RequestOptions(max_retries=N)` must be set to `0`, or
   our rate limiter miscounts physical requests — the exact bug fixed on the Bedrock side
   yesterday via `get_bedrock_client(max_attempts=1)`.

---

## 2. GO / NO-GO GATE — Step 0, do this before writing any code

**Bin 1's 206,959 vectors came from Bedrock `cohere.embed-v4:0`. Bins 2-3 would come from
native `embed-v4.0`. If those are not the same vector space, mixing them corrupts retrieval
in a way that is very hard to detect later.**

This also gates the *serving* path: `QueryEmbedderV2`
(`rag_modules_src/utilities/query_embedder_v2.py`) builds query vectors via **Bedrock**,
reading `embedding.bedrock.models.*` directly and enforcing `output_dimension = 1024`. It
stays on Bedrock in this design, so query vectors must live in the same space as a corpus
that would then be partly native-Cohere.

**Test (cost: ~800 tokens, about $0.0001):**
1. Take ~20 `sentenceID`s already embedded in Bin 1; pull their stored vectors from
   `data_cache/embeddings/cohere_1024d/finrag_embeddings_cohere_1024d.parquet`.
2. Re-embed the same sentence texts via native Cohere with **identical** parameters:
   `model="embed-v4.0"`, `input_type="search_document"`, `embedding_types=["float"]`,
   `output_dimension=1024`.
3. Cosine-similarity each pair.

| Result | Decision |
|---|---|
| mean cosine >= 0.9999 | **GO.** Same space. Proceed with this design as written. |
| 0.99 - 0.9999 | **PAUSE.** Same family, not bit-identical. Decide explicitly whether drift is acceptable; prefer the redo below. |
| < 0.99 | **NO-GO as written.** Different space. Fall back: re-embed all 3 bins on one transport ($2.29) and move `QueryEmbedderV2` to the same transport. |

Do not skip this. It is the cheapest decisive experiment available and it de-risks the
whole plan.

---

## 3. Two pre-existing landmines this work must fix

Found while tracing the config path today. **The first one would silently destroy Bin 1's
work the moment the provider switch is flipped.**

### P0 — `embeddings_path()` sends non-Bedrock providers to the 768-d path
`loaders/ml_config_loader.py:176-178`:
```python
else:
    # Direct API provider fallback
    provider = 'cohere_768d'
```
Set `default_provider: cohere` and the vectors path resolves to
`ML_EMBED_ASSETS/EMBED_VECTORS/cohere_768d/finrag_embeddings_cohere_768d.parquet`
instead of the `cohere_1024d` file holding all 209,603 existing vectors. Consequence chain:
`_merge_vectors_table()` reads a non-existent table -> hits its own "not found" degradation
path -> **seeds a fresh table** -> Bin 1's 209,603 vectors are silently orphaned.

**Fix (a simplification — deletes the branch rather than patching it):** storage layout
describes the *vector space*, not the *transport*. Both `cohere.embed-v4:0` and
`embed-v4.0` are cohere/1024-d.
```python
if provider is None:
    dims = self.embedding_dimensions              # already provider-aware
    model_id = str(self.embedding_model).lower()  # already provider-aware
    family = "titan" if "titan" in model_id else "cohere"
    provider = f"{family}_{dims}d"
```
Safe: the `embedding_model` / `embedding_dimensions` / `embedding_batch_size` legacy
properties have **zero consumers outside `ml_config_loader.py`** (verified by grep), so
reshaping them breaks nothing.

### P1 — checkpoint path collides across providers
`CHECKPOINT_PATH` is one global file (`data_cache/_scratch/embedding_checkpoint.parquet`).
Already a known bug; two transports **escalate it from annoying to a correctness risk** —
a Bedrock-run and a Cohere-run checkpoint would collide, and vectors from two different
transports could merge into one checkpoint file undetected. Because this change creates the
risk, fixing it belongs in this change: scope the filename by
`{provider}_{hash(filter_params)}`.

### Also fix (directly motivated by yesterday's loss)
- **Flush the checkpoint before aborting on quota exhaustion.** Checkpoints write every 50
  batches; yesterday the run reported 131,520 embedded but only 129,600 were saved — about
  **1,920 sentences of already-paid-for work lost**. Flushing on the abort path recovers it.
- **`_update_meta_table()` hardcodes `config.bedrock_model_id` / `bedrock_dimensions`**
  (lines ~560-561) into the meta table's provenance columns. Must read from the active
  provider instead. Safe: `embedding_model` is *not* part of the S3 Vectors metadata schema
  (which carries `cik_int`, `report_year`, `section_name`, `sic`, `sentence_pos` filterable
  and `embedding_id`, `section_sentence_count`, `sentenceID` non-filterable), so nothing
  downstream filters on it. The column will legitimately hold both spellings — that is
  honest lineage, not a defect.

---

## 4. High-level design

### The seam
The entire provider-specific surface is **one operation**: *given a list of texts, return a
list of 1024-d float vectors (plus billed token count if the provider reports it)*.

`_call_bedrock_api()` today conflates three concerns:

| Concern | Provider-specific? | Where it goes |
|---|---|---|
| request/response marshalling | **yes** | -> provider adapter |
| error classification | **yes** | -> provider adapter, normalized to shared exceptions |
| retry loop + rate limiting | no | **stays in the pipeline, unchanged** |

Everything else in the pipeline — meta load, filtering, token-aware batching, checkpointing,
merge, meta update, S3 save, cost tracking — is already transport-agnostic and **must not be
duplicated**. That is the argument against a parallel standalone Cohere script: the
checkpoint/resume, merge-crash guard, rate limiter and retry classification were all hard-won
debugging wins (see `EMBEDDING_PROGRESS_LOG.md` section 5). Two copies means two places to fix
every future bug, and invites exactly the config/code divergence already flagged as P1 in
`EMBEDDINGS_VECTORS_REVIVAL_PLAN.md`.

### Architecture

```
                    ml_config.yaml
              embedding.default_provider: bedrock | cohere
                            |
                            v
                    build_provider(MLConfig)          <- factory, one decision point
                       /              \
        BedrockCohereProvider     CohereNativeProvider
        (boto3 invoke_model)      (cohere.ClientV2.embed)
                       \              /
                        v            v
                  EmbeddingProvider.embed(texts) -> EmbedResult
                  translates native errors into:
                    TransientEmbedError        (retry)
                    PermanentEmbedError        (fail fast)
                    DailyQuotaExhaustedError   (abort now, do not retry)
                            |
                            v
    EmbeddingGenerationPipeline  -- UNCHANGED except the call site --
      load meta -> filter -> [batch -> rate_limiter -> provider.embed -> retry]
        -> checkpoint -> merge -> update meta -> save to S3 + local
                            |
                            v
                 AWS S3 (final tables, always)
```

**AWS is not removed.** Only the embedding *transport* becomes selectable. S3 storage, the
S3 Vectors index, Stage-3 staging, KPI supply line and all serving stay exactly as they are —
matching the stated intent that final tables still go to AWS storage.

### Why `DailyQuotaExhaustedError` is its own type
Yesterday's crash: Bedrock returns `ThrottlingException` **with HTTP 429** for both a
transient per-minute throttle *and* the hard daily cap. The retry loop cannot tell them apart,
so it burned all 7 attempts (~20s of escalating backoff) against a wall that could not move,
then crashed. Splitting the daily case out converts that into an immediate, clean, checkpointed
abort. This is a real defect fix that fell out of the observed failure, not speculative
polish.

---

## 5. Low-level design

### Files touched — one new, three edited
| File | Change | Approx size |
|---|---|---|
| `platform_core/embedding_providers.py` | **NEW** | ~200 lines |
| `platform_core/embedding_generation.py` | edit call site + retry classification + 2 provenance lines + checkpoint scoping | ~35 lines changed |
| `loaders/ml_config_loader.py` | fix `embeddings_path()` (P0), reshape legacy props, add provider-config accessor, real `_load_ml_credentials()` | ~25 lines changed |
| `.aws_config/ml_config.yaml` | replace commented `cohere:` stub with a real block; add rate knobs to both providers | ~20 lines |

One new module, not three. The two adapters are ~40 lines each implementing one small
interface, and the point is to read them side by side to confirm they produce identical
vectors. Splitting into `base.py` + `bedrock_provider.py` + `cohere_provider.py` would be
over-engineering at this scale and would not match house style (`embedding_generation.py` is
~710 lines, single-purpose).

### `platform_core/embedding_providers.py` (pseudocode)

```python
"""
Transport adapters for sentence embedding generation.

One interface, two transports: AWS Bedrock and Cohere's own API. Selected by
ml_config.yaml embedding.default_provider. The pipeline owns batching, retry,
rate limiting and checkpointing; adapters own only request marshalling and
error translation.

Mirrors the resolved-runtime-config pattern already used by
rag_modules_src/utilities/query_embedder_v2.py::EmbeddingRuntimeConfig.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

MAX_TOKENS_PER_INPUT = 128000


# ---- normalized error vocabulary -----------------------------------------

class EmbedTransportError(Exception):
    """Base for all embedding-transport failures."""


class TransientEmbedError(EmbedTransportError):
    """Retryable: throttle (429), timeout (408), any 5xx."""


class PermanentEmbedError(EmbedTransportError):
    """Not retryable: bad request, auth failure, unknown model, dim mismatch."""


class DailyQuotaExhaustedError(EmbedTransportError):
    """Provider period-level cap hit. Retrying inside this run cannot help.

    Split out from TransientEmbedError because of the 2026-07-28 Bin 2 failure:
    Bedrock returns ThrottlingException/429 for BOTH a transient per-minute
    throttle and the non-adjustable 8.1M-tokens/day cap, so the retry loop
    burned all 7 attempts against an immovable wall before aborting.
    """


# ---- value objects --------------------------------------------------------

@dataclass(frozen=True)
class EmbedResult:
    vectors: List[List[float]]
    billed_input_tokens: Optional[int]   # None if provider does not report it


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    provider: str            # "bedrock" | "cohere"
    model_id: str
    dimensions: int          # 1024 -- MUST be passed to both APIs explicitly
    input_type: str          # "search_document" for corpus ingest
    max_texts_per_batch: int # 96 on both
    max_rpm: int
    target_tpm: int          # 0 disables TPM self-throttle
    timeout_seconds: int


# ---- interface ------------------------------------------------------------

class EmbeddingProvider(ABC):
    def __init__(self, runtime: ProviderRuntimeConfig) -> None:
        self.runtime = runtime

    @abstractmethod
    def embed(self, texts: List[str]) -> EmbedResult:
        """One synchronous call, no internal retry.

        MUST translate native exceptions into the EmbedTransportError
        hierarchy. MUST NOT retry -- the pipeline owns retry and the rate
        limiter must count real physical requests.
        """

    def _validate(self, vectors: List[List[float]], n_texts: int) -> None:
        """Shared post-call guard. Catches the silent 1536-d default, which is
        the highest-risk silent failure in this migration."""
        if len(vectors) != n_texts:
            raise PermanentEmbedError(
                f"count mismatch: got {len(vectors)}, sent {n_texts}")
        for v in vectors:
            if len(v) != self.runtime.dimensions:
                raise PermanentEmbedError(
                    f"dim mismatch: got {len(v)}, expected {self.runtime.dimensions}")


# ---- Bedrock adapter (wraps today's proven call) --------------------------

class BedrockCohereProvider(EmbeddingProvider):
    def __init__(self, runtime, boto_client) -> None:
        super().__init__(runtime)
        self._client = boto_client        # built with max_attempts=1

    def embed(self, texts):
        body = json.dumps({
            "texts": texts,
            "input_type": self.runtime.input_type,
            "embedding_types": ["float"],
            "output_dimension": self.runtime.dimensions,
            "max_tokens": MAX_TOKENS_PER_INPUT,
            "truncate": "RIGHT",           # Bedrock vocabulary
        })
        try:
            resp = self._client.invoke_model(
                body=body, modelId=self.runtime.model_id,
                accept="*/*", contentType="application/json")
        except ClientError as e:
            raise self._translate(e) from e

        vectors = json.loads(resp["body"].read())["embeddings"]["float"]
        self._validate(vectors, len(texts))
        # best-effort exact billing; header is not always present
        billed = _header_int(resp, "x-amzn-bedrock-input-token-count")
        return EmbedResult(vectors, billed)

    @staticmethod
    def _translate(e) -> EmbedTransportError:
        err = e.response.get("Error", {})
        code, msg = err.get("Code", ""), err.get("Message", "")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 500)

        # Bedrock gives ThrottlingException/429 for BOTH the per-minute throttle
        # and the daily cap; the message text is the only discriminator the API
        # exposes. Brittle by necessity -- but fail-safe: if the phrase changes,
        # this degrades to TransientEmbedError, i.e. exactly today's behaviour.
        if "tokens per day" in msg.lower():
            return DailyQuotaExhaustedError(f"{code}: {msg}")
        if status in (408, 429) or status >= 500:
            return TransientEmbedError(f"{code} ({status}): {msg}")
        return PermanentEmbedError(f"{code} ({status}): {msg}")


# ---- Cohere native adapter -----------------------------------------------

class CohereNativeProvider(EmbeddingProvider):
    def __init__(self, runtime, cohere_client) -> None:
        super().__init__(runtime)
        self._client = cohere_client       # cohere.ClientV2(api_key=...)

    def embed(self, texts):
        try:
            resp = self._client.embed(
                model=self.runtime.model_id,              # "embed-v4.0"
                input_type=self.runtime.input_type,
                texts=texts,
                embedding_types=["float"],
                output_dimension=self.runtime.dimensions, # else defaults to 1536
                truncate="END",                           # native vocab, NOT "RIGHT"
                request_options=RequestOptions(
                    timeout_in_seconds=self.runtime.timeout_seconds,
                    max_retries=0,     # our loop owns retry (cf. botocore fix)
                ),
            )
        except ApiError as e:
            raise self._translate(e) from e

        vectors = resp.embeddings.float_   # trailing underscore; alias is "float"
        self._validate(vectors, len(texts))

        billed = None
        if resp.meta and resp.meta.billed_units:
            billed = resp.meta.billed_units.input_tokens   # exact, unlike Bedrock
        return EmbedResult(vectors, billed)

    @staticmethod
    def _translate(e) -> EmbedTransportError:
        # Every cohere error subclasses ApiError, which always carries
        # .status_code -- so the same HTTP-status classification works.
        status = getattr(e, "status_code", None) or 500
        body = str(getattr(e, "body", ""))
        if status in (408, 429) or status >= 500:
            return TransientEmbedError(f"cohere {status}: {body}")
        return PermanentEmbedError(f"cohere {status}: {body}")


# ---- factory: the single decision point ----------------------------------

def build_provider(config) -> EmbeddingProvider:
    name = config.embedding_provider          # existing MLConfig property
    runtime = _resolve_runtime(config, name)  # reads embedding.<name>.*

    if name == "bedrock":
        return BedrockCohereProvider(
            runtime, config.get_bedrock_client(max_attempts=1))
    if name == "cohere":
        api_key = os.getenv(config.cohere_api_key_env)
        if not api_key:
            raise PermanentEmbedError(
                f"{config.cohere_api_key_env} not set; expected it in "
                f".aws_secrets/aws_credentials.env")
        return CohereNativeProvider(runtime, cohere.ClientV2(api_key=api_key))

    raise ValueError(f"unsupported embedding provider: {name!r}")
```

### `embedding_generation.py` — the edits

`_call_bedrock_api()` becomes `_embed_with_retry()`. Structure is preserved; only the
try-body and the except-arms change.

```python
def _embed_with_retry(self, batch):
    texts = [item["text"] for item in batch]
    attempt, delay = 0, 0.5

    while attempt < DEFAULT_MAX_RETRIES:
        self.rate_limiter.acquire()          # unchanged: gates every attempt
        try:
            result = self.provider.embed(texts)
            if result.billed_input_tokens is not None:
                self.billed_tokens += result.billed_input_tokens   # exact accounting
            return result.vectors

        except DailyQuotaExhaustedError:
            # Retrying cannot clear a period cap. Persist paid work, then abort.
            self._write_checkpoint(...)      # NEW: recovers up to 49 batches
            raise

        except PermanentEmbedError:
            raise                            # bad request / auth / dim mismatch

        except TransientEmbedError as e:
            attempt += 1
            if attempt >= DEFAULT_MAX_RETRIES:
                self._write_checkpoint(...)  # NEW: same reasoning
                raise
            sleep_time = min(delay + random.random() * 0.25, 4.0)
            print(f"  Retry {attempt}/{DEFAULT_MAX_RETRIES} ({e}), "
                  f"waiting {sleep_time:.2f}s...")
            time.sleep(sleep_time)
            delay *= 2

    raise RuntimeError("retry logic error - exhausted retries without return")
```

Other edits in this file:
- `__init__`: `max_rpm=None, target_tpm=None`; build `self.provider = build_provider(self.config)`
  first, then derive the limiter from `self.provider.runtime.max_rpm` (explicit args still
  override). **`max_rpm=60` must stop being a hardcoded default** — it is tuned to AWS's
  100 rpm and would throttle Cohere to 3% of its 2,000 rpm ceiling.
- `_generate_embeddings_batch()`: drop the `bedrock` / `model_id` / `input_type` /
  `dimensions` locals; read `self.provider.runtime`.
- `_update_meta_table()`: `config.bedrock_model_id` -> `self.provider.runtime.model_id`;
  `bedrock_dimensions` -> `.dimensions`.
- `CHECKPOINT_PATH` -> per-run function of provider + filter-scope hash (P1).
- `run()` / `_print_summary()`: print the active provider, and report both estimated and
  billed tokens when the provider supplies the latter.

### `ml_config.yaml` — the switch

```yaml
embedding:
  default_provider: bedrock        # bedrock | cohere   <-- THE ONLY SWITCH

  bedrock:
    region: us-east-1
    models:
      cohere_embed_v4: { model_id: cohere.embed-v4:0, dimensions: 1024,
                         batch_size: 96, input_type: search_document }
      # ... existing entries unchanged
    default_model: cohere_embed_v4
    max_rpm: 60                    # NEW: real ceiling 100, 40% headroom
    target_tpm: 100000             # NEW: real ceiling 150000
    timeout_seconds: 60            # NEW

  cohere:                          # NEW -- replaces the commented-out stub
    api_key_env: COHERE_API_KEY    # NAME ONLY. Never the secret itself.
    models:
      cohere_embed_v4: { model_id: embed-v4.0, dimensions: 1024,
                         batch_size: 96, input_type: search_document }
    default_model: cohere_embed_v4
    max_rpm: 1000                  # prod key ceiling 2000/min, 50% headroom
    target_tpm: 0                  # 0 = disabled; Cohere publishes no TPM cap
    timeout_seconds: 60
```

Note the block is **structurally symmetric** with `bedrock` (`models` + `default_model`), so
the MLConfig accessors stay symmetric too. This differs from the old commented-out stub
(which was flat, `embed-english-v3.0`, 768-d) — that stub's shape and values are both wrong
for this use and should be replaced, not uncommented.

### Secret handling — a home already exists
`ml_config_loader.py` already has `_load_ml_credentials()` documented as *"Load ML API keys
from `.aws_secrets/aws_credentials.env` (same file)"*, currently a `pass` stub relying on
`load_dotenv()` having loaded that whole file into `os.environ`. So:

- Add `COHERE_API_KEY=...` to the **existing** `.aws_secrets/aws_credentials.env`.
- That exact path is already gitignored (`.gitignore:215`). No new file, no new ignore rule.
- Make `_load_ml_credentials()` real: when `default_provider == "cohere"`, assert the key is
  present and fail with a clear message if not (mirroring the existing AWS-credential
  validation), instead of failing later at first API call.
- YAML stores only the env-var **name**, never the value.

---

## 6. Verification plan

Run in order; each step gates the next.

| # | Step | Pass criterion |
|---|---|---|
| 0 | **Vector compatibility** (section 2) | mean cosine >= 0.9999 vs stored Bin 1 vectors |
| 1 | Config loads on both settings | `MLConfig()` OK with `default_provider` = `bedrock`, then `cohere` |
| 2 | **P0 regression guard** | `embeddings_path()` returns the `cohere_1024d` path under **both** providers. This is the test that protects Bin 1's 209,603 vectors. |
| 3 | Adapter parity, 1 batch of 5 | both providers return 5 vectors, each exactly 1024-d |
| 4 | Error translation | force a bad model id -> `PermanentEmbedError`, not a retry storm |
| 5 | Rate limiter derivation | limiter reports 60 rpm for bedrock, 1000 for cohere |
| 6 | **Small live run** (~2,000 sentences, ~$0.01) on cohere | vectors merge into the existing 1024-d table; row count grows by exactly the expected amount; no duplicate `sentenceID` |
| 7 | Checkpoint scoping | a bedrock-scoped and a cohere-scoped checkpoint coexist without collision |
| 8 | Finish Bin 2 (94,596 remaining) | then re-run `EMBEDDING_PROGRESS_LOG.md` section 6 checks: unique IDs, dims 1024, no NaN, S3-vs-local byte match |
| 9 | Bin 3 (180,848) | same checks |
| 10 | Serving smoke test | a real query returns cited hits, confirming query-side Bedrock vectors still retrieve against the mixed corpus |

Step 6 is the real go/no-go for the bulk run — never go straight from unit checks to 275K
sentences.

---

## 7. Rollback

Cheap and complete, by construction:
- **Revert = one YAML line** (`default_provider: cohere` -> `bedrock`). The Bedrock path is
  untouched code, not a rewrite.
- The vectors parquet is append-and-dedupe (`unique(subset=['sentenceID'], keep='last')`), so
  a bad partial run is corrected by re-running the affected scope, not by surgery.
- Worst case (Step 0 fails outright, or spaces drift): re-embed all three bins on a single
  transport for **$2.29**. That number is the reason this whole plan is low-risk.
- Nothing in this design touches the S3 Vectors index, Stage-3 staging, the KPI supply line,
  or serving.

---

## 8. Recommendation

**Proceed — gated on Step 0.**

For: unit cost is provably identical ($0.12/1M both sides); the specific blocker (a
non-adjustable 8.1M/day cap) disappears; RPM headroom goes 100 -> 2,000 against a remaining
workload of only ~2,870 calls, turning 2+ days of stop/start into one sitting; no dependency
on an unanswerable Basic-support ticket; and the refactor is genuinely net-positive for the
codebase — it deletes the P0 path landmine, fixes the quota-retry defect that wasted retries
yesterday, stops losing up to 49 batches of paid work on abort, and gains exact token
accounting from `meta.billed_units`.

Against, honestly stated: vector-space compatibility is unproven until Step 0 runs; a new
auth surface is introduced; the query path stays on Bedrock, creating a cross-transport
dependency on those spaces matching; ~200 new lines land in a working pipeline; and Cohere's
lack of a *documented* daily cap is not proof that none exists (UNVERIFIED — worth watching
during the first bulk run).

Scope discipline: this is one new module plus surgical edits to three existing files. It does
**not** touch serving, Stage 3, the S3 Vectors index, or the KPI line, and it does not
consolidate `QueryEmbedderV2` onto the new abstraction (a sensible future cleanup — note that
module already defines its own local `EmbeddingProviderError`, so the new hierarchy uses
distinct names to avoid ambiguity).

---

## 9. Open questions

1. **Cohere account tier** — is the production key on a paid plan with billing configured?
   A trial key is capped at 5 embed inputs/min and would be unusable for 275K sentences.
2. **Undocumented daily caps on Cohere** — treat as unknown; watch the first bulk run.
3. **Env decision** — run from `finsights_revival` (has cohere 7.0.8 + polars + boto3, ready
   now) or add `cohere` to `finsight-venv` (the env used so far)? Recommend the former: zero
   installs. Not doing either without explicit go-ahead.
4. **`co.embed(...)` vs `co.v2.embed(...)`** — introspection confirms `ClientV2.embed` exists
   with the right signature; Cohere's own docs show both spellings in different places.
   Confirm with a one-line call at implementation time rather than trusting either doc.
