# Embedding Generation — Progress Log

**Last updated:** 2026-07-28 (session start 2026-07-27 evening, continuing into 07-28)
**Purpose:** resume-anywhere status tracker. If you're starting fresh after `/clear` or a
new session with zero memory of this work, read this file first, in full, before touching
anything. It tells you exactly what's done, what's blocked, and the precise command to
resume. For the *remaining* S3 Vectors work (index creation is done — see §1 below; Stage 3
build onward is not), see `EMBEDDINGS_VECTORS_REVIVAL_PLAN.md` — that doc is trimmed to only
that forward-looking work; everything about embedding generation itself lives here instead.

---

## 1. Exact current state — read this first

| Bin | Years | Companies | Sentences | Status |
|---|---|---|---|---|
| **Bin 1** | 2006-2016 | all 25 | 206,959 | ✅ **DONE** — verified, cost $0.9905, 8,254,022 tokens |
| **Bin 2** | 2017-2021 | all 25 | 224,196 (after outlier skip) | ⏸️ **BLOCKED** — ~9,600 saved so far (~4.3%), see §3 |
| **Bin 3** | 2022-2025 | all 25 | ~183,536 (estimate) | ⬜ **NOT STARTED** |

**Vectors table right now:** 209,603 rows total on S3 + local
(`ML_EMBED_ASSETS/EMBED_VECTORS/cohere_1024d/finrag_embeddings_cohere_1024d.parquet`) — this
is Bin 1's 206,959 + 1,690 rows of earlier ad-hoc test data (Apple 2024/2025/2022, harmless,
legitimate real embeddings, not scaffolding to clean up).

**Config right now:** `ml_config.yaml`'s `embedding_execution.filters` is already set to
**Bin 2's exact scope** (all 25 CIKs, `year: [2017, 2018, 2019, 2020, 2021]`) — no edit needed,
just resume once unblocked (§3).

**S3 Vectors index:** ✅ created and verified today (bucket `finrag-embeddings-s3vectors`,
index `finrag-sentence-fact-embed-1024d`, 1024-d/cosine) — see
`EMBEDDINGS_VECTORS_REVIVAL_PLAN.md` §Step C. **Nothing has been inserted into it.** This was
deliberately scoped to *creation only* — see §8 below for why Stage 3 (the table that would
actually get inserted) is intentionally on hold.

**Where we are on the vectors table itself:** what your own architecture notes call the "Stage
2 - Embed Table" (`sentenceID`, `embedding_id`, `embedding` — no company/year metadata yet) is
**partially populated**: 209,603 of the eventual ~614,787 rows (Bin 1 + odds and ends). This is
the "partial Stage 2" state — Stage 3 (joining in `cik_int`/`report_year`/`section_name`/`sic`
and inserting into the index above) does not start until this table is complete.

## 2. To resume Bin 2 (once unblocked)

```bash
cd "ModelPipeline/finrag_ml_tg1/platform_core"
eval "$(aws configure export-credentials --profile mjsushanth_mlops --format env)"
/opt/homebrew/Caskroom/miniconda/base/envs/finsight-venv/bin/python -u -c "
import embedding_generation as eg
pipeline = eg.EmbeddingGenerationPipeline()
summary = pipeline.run()
print('RUN_COMPLETE:', summary)
"
```

It will auto-resume from checkpoint if one exists and matches this scope (see the checkpoint
bug in §5 — don't run an unrelated small scope in between, or it'll wipe Bin 2's checkpoint
again). After Bin 2 finishes: quick-check (merge count, dims=1024, no NaN, S3-vs-local byte
match — see §6 for the exact commands), then repeat for Bin 3 by editing
`embedding_execution.filters.year` to `[2022, 2023, 2024, 2025]` (cik_int list stays the same).

## 3. The blocker

Hit **`ThrottlingException: ... Too many tokens per day, please wait before trying again.`**
This account's Cohere Embed V4 daily token quota is **8,100,000 tokens/day, non-adjustable**,
and Bin 1 alone (8,254,022 tokens) already exceeded it. It appears to be a **rolling 24-hour
window**, not a calendar-day reset — so it won't clear until roughly 24h after Bin 1's run
(~2026-07-27 21:19 EDT), and is shared across on-demand and cross-region invocation (cross-region
debits it at 2x per token). No code fix addresses this — only time, or the pending AWS support
quota increase (§4), resolves it.

**Before retrying:** check whether enough time has passed, or check for a reply on the support
ticket. If you resume and hit the same message immediately, it hasn't cleared yet — stop again
rather than burning retry attempts against a wall that isn't moving.

## 4. AWS Support ticket (filed 2026-07-28)

Requested AWS default quota levels (not above-default) for:
- Cohere Embed V4: on-demand RPM (100 → 1,000 default), cross-region RPM (200 → 2,000),
  daily token caps (8.1M/16.2M → 216M/432M default)
- Claude Sonnet 5: found at **0 applied quota across every dimension** (input/output/cross-region
  TPM, daily caps) vs defaults like 3M/300K/6M/8.64B — essentially no usable access at all
- Context given: this account (`mjsushanth_mlops`, 908877262866) is scaling toward 1-5M row
  datasets (~40M-200M tokens), so the current caps are 5-25x too low for where this is headed,
  independent of today's immediate issue.

Check for a reply before assuming quotas are still at the reduced level.

## 5. What was actually built today (code changes, still in place)

All in `ModelPipeline/finrag_ml_tg1/platform_core/embedding_generation.py` unless noted.

1. **Stage 2 meta table regenerated** from the fresh 614,787-row/25-company Stage 1 (was
   stale at 469,252 rows/21 companies). Verified 614,787 rows, 25 companies, both S3 and local.
2. **Merge-crash guard** — `_merge_vectors_table()` no longer assumes the vectors table
   exists; degrades to a fresh seed on a real "not found" error instead of crashing after
   embeddings are already paid for. Verified against the real exception text (`OSError`,
   "not found"/"404" in message — confirmed empirically, not guessed).
3. **Cost tracking fixed** — was silently using the wrong rate (`cohere_768d`, $0.10/1M)
   instead of the real Cohere v4 rate ($0.12/1M, added to `ml_config.yaml costs.rates` as
   `cohere_1024d`). Passive (non-blocking) budget-alert print added.
4. **Checkpoint/resume mechanism** — writes progress every 50 batches to a local scratch
   parquet (`data_cache/_scratch/embedding_checkpoint.parquet`), resumes by skipping
   already-embedded sentenceIDs, reuses `embedding_id` across a resume, clears on clean
   completion. **Known bug, not yet fixed:** the checkpoint path is a single global path, not
   scoped per run/scope — a *different*, unrelated small run's successful completion will
   delete *any* other in-progress checkpoint, even one it never touched. Cost impact so far has
   been negligible (~$0.02 of re-embedded tokens once), but worth scoping the path (e.g. by a
   hash of the filter parameters) before relying on it across differently-scoped runs again.
5. **Retry/backoff, twice-corrected:**
   - v1: mirrored `s3vectors_bulk_insertion.py`'s error classification, but that service uses
     `TooManyRequestsException` while Bedrock's `InvokeModel` actually uses `ThrottlingException`
     — confirmed via botocore's real service model, not guesswork. Fixed.
   - v2: further generalized to classify by **HTTP status** (408/429 retryable, other 4xx
     fail-fast, 5xx retryable) instead of matching specific error-code name strings, since that
     also catches `ModelNotReadyException` (429) and `ModelTimeoutException` (408), which the
     name-based check would have missed.
6. **botocore's hidden internal retry disabled** for this call site specifically —
   `loaders/ml_config_loader.py::get_bedrock_client(max_attempts=None)` now accepts an optional
   override; the embedding path passes `max_attempts=1` so our own retry loop and rate limiter
   count real physical requests accurately (botocore's legacy-mode default silently retries up
   to 5x per logical call otherwise). **Left at default (unset) for other callers** — the LLM
   synthesis path (`bedrock_client.py`) has zero retry logic of its own and currently relies on
   botocore's hidden retry as its only resilience; do not change that default without giving it
   real retry logic first.
7. **`GlobalRateLimiter`** — a sliding-window limiter (module-level class in
   `embedding_generation.py`) gating *every* Bedrock call attempt, including retries, to
   `max_rpm=60` (60% of the account's real 100 RPM ceiling). This closed the actual gap: the
   earlier `target_tpm` pacing only slowed down *successful* calls, never retries — and retries
   themselves consume RPM budget even when they fail, so a throttle storm was self-reinforcing.
   Verified in isolation (fake-clock + real-clock unit tests, zero AWS calls) before being wired
   into the real pipeline. `target_tpm` pacing is kept too (orthogonal, tokens vs. requests).

## 6. Verification commands (reuse after each future bin)

```python
import polars as pl, numpy as np
vec = pl.read_parquet(".../data_cache/embeddings/cohere_1024d/finrag_embeddings_cohere_1024d.parquet")
assert vec['sentenceID'].n_unique() == len(vec)                       # no duplicate sentenceIDs
arr = np.array(vec['embedding'].to_list())
assert arr.shape[1] == 1024 and not np.isnan(arr).any()                # correct dims, no NaN
```
S3-vs-local byte check: `aws s3 cp s3://.../<file>.parquet /tmp/check.parquet && cmp /tmp/check.parquet <local path>`
(don't trust the S3 ETag directly for multipart uploads — it's not a plain MD5).

## 7. Things learned this session worth remembering

- **RPM vs TPM are independent ceilings** — you're bound by whichever you hit first, not by
  whichever number looks bigger. This account's real constraint was RPM (100), not TPM (150K,
  already at AWS default) — the opposite of what token-volume-based intuition suggests.
- **Every retry consumes real quota**, even failed ones. A `EstimatedTPMQuotaUsage` CloudWatch
  reading that looks "under quota" can be misleading — per AWS's own blog, it reflects
  *completed* usage, not the *upfront reservation* that actually drives throttling decisions.
- **The AWS Service Quotas console's "Applied account-level quota value" column can be far
  below "AWS default quota value"** for a given account — this is where the real ceiling
  showed up; CloudWatch metrics alone don't surface this, and neither does
  `service-quotas list-service-quotas`'s CLI output unless you also check the account's
  applied value against the default (the CLI doesn't print the default side-by-side by default).
- **Cross-region inference profiles trade 2x per-minute throughput for 2x daily-token debit
  rate** — a bad trade for any single job whose own token volume is already close to the daily
  cap (as ours was), even though it looks like a pure win from the per-minute numbers alone.
- **Batch Inference is not available for any Cohere Embed model** on Bedrock (confirmed against
  AWS's authoritative supported-models list) — not a fallback option for this workload.

## 8. Decision: full embedding pipeline first, Stage 3 after (recorded 2026-07-28)

Explicit call made this session, not just an open question: **do not start Stage 3 (the
meta+vectors join) or any `put_vectors` insertion until all three bins (1, 2, 3) are complete
and verified.** Reasoning:
- Building Stage 3 against partial data (Bin 1 only) would mean rebuilding/re-joining once
  Bins 2-3 land anyway — no benefit to going early here, unlike the S3 Vectors index itself
  (a one-time, idempotent, insert-independent setup step, which is why that part *was* done
  today even though embedding generation isn't finished).
- The session's owner explicitly wants a clean stopping point: finish embedding generation
  fully first (resume Bin 2 once the daily quota clears, then run Bin 3), *then* move to Stage
  3 + bulk insert + retrieval validation as one clean forward pass, not interleaved with
  quota-recovery waiting.

**So the actual next steps, in order, whenever this resumes:**
1. Check AWS support ticket reply / whether enough time has passed for the daily quota to clear.
2. Resume Bin 2 (§2), verify (§6).
3. Run Bin 3 (same command, edit `year` to `[2022, 2023, 2024, 2025]`), verify (§6).
4. Only then: open `EMBEDDINGS_VECTORS_REVIVAL_PLAN.md` and start at Step E (Stage 3 build) —
   Steps B and C in that doc are already done.

## 9. Session closed 2026-07-28 — everything above is the full state

No further embedding work happened after Bin 2 was blocked and the S3 Vectors index was
created. Code changes (§5) and the new index (S3 Vectors, above) are committed to git on
`revival/aws-infra`. A completely fresh terminal/session tomorrow can start from reading this
file top to bottom and needs nothing else from this conversation.
