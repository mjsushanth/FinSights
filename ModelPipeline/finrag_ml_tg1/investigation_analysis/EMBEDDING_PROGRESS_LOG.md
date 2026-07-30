# Embedding Generation — Progress Log

**Last updated:** 2026-07-30. **Read this first** if resuming with no context.

> **PIPELINE FULLY COMPLETE END TO END.** Embedding: 614,647 / 614,647 eligible = 100%.
> Stage 3 built AND `PutVectors` bulk-inserted into the live S3 Vectors index — done, not
> pending. Retrieval, synthesis, and serving (backend + frontend) have all been run and
> verified against real AWS this session. See "2026-07-30 — full-system live verification"
> below for the update that supersedes the "deferred, pending a go-ahead" line further down
> (kept for history, not deleted — that line was accurate at the time it was written, just
> stale now).

## 2026-07-30 — full-system live verification

Every stage/table re-verified directly (not from docs) in one pass: local file present, S3
object present, sizes match, local timestamp precedes or matches cloud upload timestamp
(local-then-upload, as designed). No stage is missing, stale, or generated-but-never-uploaded.

| Table | Local | S3 | Order |
|---|---|---|---|
| Stage 1 (fact sentences) | 37.5MB, 07-27 | 35.8MB, 07-27 03:09 | local→cloud |
| Metrics/KPI fact table | 79.4KB, 07-27 17:37 | 77.5KB, 07-27 17:37 | matched exactly |
| Merged embeddings (all bins) | 2.29GB, 07-29 08:05 | 2.1GiB, 07-29 08:05:26 | local→cloud |
| Stage 2 (meta+embeds) | 64.8MB, 07-29 19:01 | 61.8MB, 07-29 19:08 | local (19:01) → cloud (19:08) |
| Stage 3 (S3 Vectors staging table) | 2.30GB, 07-29 19:18 | 2.1GiB, 07-29 19:18:02 | local→cloud, same minute |

**S3 Vectors index confirmed live and populated by direct query** (not by re-reading this doc's
older claim below): queried `finrag-sentence-fact-embed-1024d` with a real 1024-d Cohere
embedding, got 5 real hits back with real metadata (`sentenceID`, `cik_int`, `report_year`,
mixed `bedrock_cohere_v4`/`cohere_direct_v4` embedding-batch provenance) — proof the bulk
insert genuinely landed, not just that a doc says it did.

**Full pipeline + serving smoke test, same session:** `synthesis_pipeline/main.py` CLI ran
end-to-end against real AWS (14,558 in / 2,555 out tokens, $0.0273, real cited answer, real S3
context/response exports). FastAPI backend (`:8000`) and Streamlit frontend (`:8501`) both
started, backend `/health` and `/query` both returned correctly, frontend confirmed wired to
the backend at its default `BACKEND_URL`. Nothing left to build or generate — this is a live,
answering system on the new AWS account.

---

**Since 08:20, 2026-07-29 (historical — superseded by the update above):**
- Stage 2's `embedding_id` (+4 sibling columns) backfilled for all 180,848 Bin 3 rows — they were
  never stamped because Bin 3 ran through the standalone notebook, not the production pipeline.
  Non-null count: 433,799 -> 614,647. Local + S3 re-synced, byte-verified. Notebook 06 §11.
- **Stage 3 built and uploaded**: `s3vectors_table_preparation.py`, provider `cohere_1024d` —
  614,647 rows, 10 columns, 0 hash collisions, all 20 years present. Staged at
  `ML_EMBED_ASSETS/S3_VECTORS_STAGING/cohere_1024d/`. ~~Not yet inserted into the S3 Vectors
  index.~~ (This was true when written; the bulk insert ran later the same session and is
  confirmed live as of 2026-07-30 above.)

---

## 1. Current state — DONE

| Bin | Years | Eligible | Status | Transport |
|---|---|---|---|---|
| **Bin 1** | 2006-2016 | 206,959 | **DONE** | Bedrock |
| **Bin 2** | 2017-2021 | 224,196 | **DONE** (2026-07-29 04:18) | Bedrock |
| **Bin 3** | 2022-2025 | 183,492 | **DONE** (2026-07-29 07:31) | Cohere direct |

**Vectors table: 614,647 rows / 2,293,538,065 B**, local and S3 verified **byte-identical** —
matched on exact size *and* on a locally recomputed multipart composite ETag
(`b47a120c6558e28f55f3770d18f1e9fa-35`, 64 MB parts).
`ML_EMBED_ASSETS/EMBED_VECTORS/cohere_1024d/finrag_embeddings_cohere_1024d.parquet`

**Meta table: 614,787 rows.** 614,647 eligible (`sentence_token_count <= 1000`); the 140 outliers
(53 / 43 / 44 by bin) are excluded by design, consistently across all three bins.

**Bin 3 run:** 180,848 sentences, 1,884 calls, **104.3 min, zero retries**,
7,555,061 billed tokens = **$0.9066**. 76 shard checkpoints. Notebook
`platform_core/06_Bin3_CohereDirect_Embeddings.ipynb` (sections 8-10 hold the full acceptance test).

**Full-table validation — all PASS** (notebook 06 §8-10):

- unique `sentenceID`, no nulls, every vector exactly 1024-d, no NaN, no Inf, no degenerate vectors
- coverage by two-way anti-join: nothing missing, nothing orphaned, outliers correctly unembedded
- **every one of the 20 report years at 100%** (2006-2025)
- continuity: 3,000-row sample bit-identical to the pre-merge table; **0 collisions**
- provider parity: L2 norm mean 1.0 in all three bins, cross-bin spread **0.00e+00** — Bedrock and
  Cohere-direct vectors sit in one coherent space, measured on the real table rather than a probe

**Total regeneration cost: ~$2.21** (~$1.30 Bedrock for Bins 1-2 + $0.9066 Cohere for Bin 3),
against the ~$5 originally estimated.

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

Embedding is finished; nothing in this document needs re-running. What remains:

1. **Stage 3** — `EMBEDDINGS_VECTORS_REVIVAL_PLAN.md` **Step E**: join meta + vectors and bulk
   insert into the S3 Vectors index, which exists but is still **empty**. Steps B and C are done.
   This gates all retrieval measurement (~$0.50 one-time, ~$0.15/mo).
2. **Cleanup, now safe** — the 76 Bin 3 shards (636 MB, `data_cache/embeddings/_bin3_shards/`) and
   `finrag_embeddings_cohere_1024d.parquet.premerge_bak` (1.5 GB) are redundant. The Seagate
   archive `FinSights_Backup_20260729/` holds the pre-merge table independently.

**Not done, deliberately:** the Bin 3 standalone parquet was not uploaded to S3. Its vectors are
all in the merged table, so it is a convenience copy only.

**Housekeeping found 2026-07-29:** one **stale incomplete multipart upload** from 2026-07-28 on the
vectors key. Orphaned parts accrue storage silently — they do not appear in `s3 ls`. Small (~$0.03/mo)
but worth an `abort-multipart-upload` plus a lifecycle rule to auto-abort incomplete uploads:
`aws s3api list-multipart-uploads --bucket sentence-data-ingestion-mjs`

**Superseded:** `EMBEDDING_TRANSPORT_DESIGN.md` shelved the direct-Cohere transport in favour of
finishing on Bedrock. That call was reversed — the cap made it necessary and Bin 3 ran on Cohere
direct, in one sitting with zero retries. The **P0 landmine** that doc flagged
(`ml_config_loader.py` routing any non-Bedrock provider to the `cohere_768d` path, which would
silently orphan the vectors table) is **fixed**: `embeddings_path()` and `embeddings_metadata_path()`
now resolve `provider=None` through `data_ml.embeddings.canonical_slot`.
