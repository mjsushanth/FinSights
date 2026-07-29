# Embedding Generation — Progress Log

**Last updated:** 2026-07-29 (early hours). **Read this first** if resuming with no context.

---

## 1. Current state

| Bin | Years | Sentences | Status |
|---|---|---|---|
| **Bin 1** | 2006-2016 | 206,959 | **DONE** |
| **Bin 2** | 2017-2021 | 224,196 | **DONE** (2026-07-29 04:18) |
| **Bin 3** | 2022-2025 | 183,492 eligible | **NOT STARTED** — 2,644 done (old ad-hoc test data), 180,848 remaining |

**Vectors table: 433,799 rows**, durable in S3 + local, byte-identical
(`1,558,533,985` both sides).
`ML_EMBED_ASSETS/EMBED_VECTORS/cohere_1024d/finrag_embeddings_cohere_1024d.parquet`

**Meta table: 614,787 rows**, of which 433,799 have `embedding_id` set — exactly consistent
with the vectors table.

**Overall: 433,799 / 614,647 eligible = 70.58%.**
**Remaining: 180,848 sentences / 7,162,360 tokens / ~$0.86.**

Integrity checks on the final table all PASS: no duplicate `sentenceID`, all dims exactly 1024,
zero NaN. Scratch checkpoint auto-cleared on clean completion.

**Config is still set to Bin 2's scope.** To run Bin 3, edit
`ml_config.yaml embedding_execution.filters.year` to `[2022, 2023, 2024, 2025]` (CIK list
unchanged, all 25).

## 2. Resume command

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
Auto-resumes from checkpoint if one exists and matches the configured scope.

## 3. The blocker — and an important correction to how it behaves

Bedrock Cohere Embed V4 on this account: **8,100,000 tokens/day, rolling 24h window,
NOT adjustable.** Confirmed `Adjustable: false` on all four relevant quota codes
(`L-F1BB08BB`, `L-795ADAB0`, `L-BE5FD99B`, `L-EB8C1F30`);
`request-service-quota-increase` returns `IllegalArgumentException`. Support-case-only, and
the account is on **Basic support** (`describe-cases` -> `SubscriptionRequiredException`), so
the pending ticket has no SLA and went unanswered for 14h+.

**KEY LEARNING: enforcement LAGS — you can overshoot the cap.** On 2026-07-29 the trailing-24h
total was already ~8.9M (roughly 800k **past** the 8.1M cap), yet a further 133k tokens went
through with zero retries and finished Bin 2. So:
- do not assume "cap reached" means "nothing more will work"
- **always probe with one tiny request before concluding you are blocked**
- small top-up runs can slip through even when the window looks exhausted

Probe (~30 tokens, instant):
```python
b.invoke_model(body=json.dumps({'texts':['probe'],'input_type':'search_document',
    'embedding_types':['float'],'output_dimension':1024,'max_tokens':128000,
    'truncate':'RIGHT'}), modelId='cohere.embed-v4:0', accept='*/*',
    contentType='application/json')
```

Corollary: hourly CloudWatch buckets **underestimate** available headroom. A projection of
~74,800 sentences on 2026-07-29 actually delivered **91,200** (~22% more).

## 4. Code changes in place

`platform_core/embedding_generation.py` unless noted.

1. **Stage 2 meta table regenerated** from the fresh 614,787-row / 25-company Stage 1
   (was stale at 469,252 / 21 companies).
2. **Merge-crash guard** — `_merge_vectors_table()` degrades to a fresh seed on a real
   "not found" instead of crashing after embeddings are already paid for.
3. **Cost tracking fixed** — was using `cohere_768d` ($0.10/1M); real rate is $0.12/1M, added
   as `cohere_1024d` in `costs.rates`.
4. **Checkpoint/resume** — writes every 50 batches to
   `data_cache/_scratch/embedding_checkpoint.parquet`, resumes by skipping done sentenceIDs,
   reuses `embedding_id`, clears on clean completion.
   *Known bug, unfixed:* single global path, not scoped per run — an unrelated run's clean
   completion deletes any other in-progress checkpoint.
5. **Retry/backoff by HTTP status** (408/429 retry, other 4xx fail fast, 5xx retry) rather than
   error-code names — Bedrock's `InvokeModel` uses `ThrottlingException`, not
   `TooManyRequestsException`, and status-based classification also catches
   `ModelNotReadyException` (429) / `ModelTimeoutException` (408).
6. **botocore's hidden retry disabled at this call site** —
   `get_bedrock_client(max_attempts=1)`. Left at default for other callers; the LLM synthesis
   path has no retry of its own and relies on it.
7. **`GlobalRateLimiter`** — sliding window over *every* attempt including retries,
   `max_rpm=60` (60% of the account's real 100 RPM).
8. **HARD STOP on the daily cap (added 2026-07-29).** See section 5.

## 5. Hard stop on daily quota — why and how

**Problem:** Bedrock returns `ThrottlingException` with HTTP **429** for *two different things*:
- a transient per-minute throttle — `"Too many requests..."` — retrying **works**
- the daily token cap — `"Too many tokens per day..."` — retrying **cannot work**

Same exception name, same status code. The retry loop could not tell them apart, so on the
daily cap it worked the full 7-attempt ladder (~16s) and crashed anyway, with a traceback that
made a routine quota decision look like a code bug.

**Fix:** `DAILY_CAP_MESSAGE_MARKER = 'tokens per day'` checked *before* the status-based
classification; raises `DailyTokenQuotaExhausted` immediately and prints a readable halt block
naming the checkpoint path and next steps.

**Why the brittleness is safe:** the message text is the *only* discriminator the API exposes —
no distinct code, status, or `Retry-After`. The match is deliberately narrow and **falls through
to the transient path** if it misses, so if AWS rewords the message, behaviour degrades to
exactly the pre-fix retry-then-crash — never worse. **Do NOT broaden this to "all 429s are
fatal"**: that would abort recoverable runs on ordinary throttles, a far worse failure mode.

Verified by simulated `ClientError` (no AWS calls), 4/4 PASS:
daily cap -> aborts after 1 call; transient -> still retries all 7; bad request -> still fails
fast; reworded daily cap -> degrades to retry path. Not yet triggered in a live run (nothing
throttled during the run that closed Bin 2).

## 6. Verification commands

```python
import polars as pl
v = pl.scan_parquet("data_cache/embeddings/cohere_1024d/finrag_embeddings_cohere_1024d.parquet")
s = v.select([pl.len().alias("rows"), pl.col("sentenceID").n_unique().alias("uniq"),
              pl.col("embedding").list.len().min().alias("dmin"),
              pl.col("embedding").list.len().max().alias("dmax")]).collect()
nan = v.select(pl.col("embedding").list.eval(pl.element().is_nan().any())
               .list.first().sum()).collect()
# expect rows == uniq, dmin == dmax == 1024, nan == 0
```
Use `scan_parquet`, never `read_parquet` — the table is 1.56 GB.
S3-vs-local: compare byte sizes (do not trust the multipart ETag as an MD5).

## 7. Cost reality

**Reconciled exactly** — Cost Explorer `UsageQuantity x 1M` == CloudWatch `InputTokenCount`
sum == **9,506,195** for UTC 2026-07-28.

Important: a **CE daily row aggregates every run in that UTC day**, not one run. Comparing a
single run's tracked tokens to a daily CE row overstates "waste" — the 15.2% gap once suspected
as per-run retry waste was mostly the cross-region experiment (229,032) plus an aborted Bin 2
start and ad-hoc embeds. **Estimate per-bin cost from token counts, not by scaling a CE row.**

Also: **EDT/UTC skew.** Bin 1 ran the evening of 07-27 EDT, which is 07-28 UTC — that is why it
appeared on the "07-28" CE row.

Costs so far: Bin 1 ~$1.14 billed. Bin 2 ~$0.44 + $0.016. Remaining Bin 3 ~$0.86.

## 8. Other learnings worth keeping

- **RPM and TPM are independent ceilings** — bound by whichever hits first. This account's real
  constraint was RPM (100), not TPM (150k, already at AWS default).
- **Every retry consumes real quota**, even failed ones.
- **Service Quotas' "applied account-level" value can sit far below "AWS default"** — that is
  where the real ceiling showed up; CloudWatch alone does not surface it.
- **Cross-region inference debits the daily token cap at 2x** — a bad trade when a job's own
  volume is already near the cap. Reverted to on-demand 2026-07-27.
- **Batch Inference is not available for any Cohere Embed model** on Bedrock.
- Batches are always exactly **96 texts** (the token cap of 128k is never the binding
  constraint at ~39 tokens/sentence), so a request-based rate limiter converts cleanly.
- The progress print shows **>100%** when resuming from a checkpoint: the numerator counts
  checkpoint + new, the denominator only the remaining work. Cosmetic only.

## 9. Next steps

1. Set `embedding_execution.filters.year` to `[2022, 2023, 2024, 2025]`.
2. Probe first (section 3). Bin 3 needs 7,162,360 tokens — close to a full day's cap on its own,
   so expect **two sittings**. The window frees meaningful capacity as the previous day's large
   buckets age out.
3. Verify (section 6), then go to `EMBEDDINGS_VECTORS_REVIVAL_PLAN.md` **Step E** (Stage 3 build)
   — Steps B and C there are already done.

**Shelved (deliberately):** a direct-Cohere-API transport as a way around the daily cap. Fully
designed and costed in `EMBEDDING_TRANSPORT_DESIGN.md` — same model, same $0.12/1M, no daily
cap, ~2.3h for all remaining work — but parked in favour of just finishing on Bedrock. That doc
also records a **real unfixed landmine (P0)**: `ml_config_loader.py:176-178` sends any
non-Bedrock provider to the `cohere_768d` path, which would silently orphan the existing
vectors table. Read it before ever flipping `embedding.default_provider`.
