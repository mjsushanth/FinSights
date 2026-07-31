# Architecture rule: cloud is the source of truth

This applies to both `src_aws_etl/` and `src_edgar_incremental/`, and to any
future module that reads or produces the sentence fact table. Keep this in
mind before adding a new stage, a new script, or a new local file path.

## The rule, plainly

1. **When starting work, read from the cloud (S3), not a local file.** A
   local copy can be stale in a way S3 can't be - someone else (or a
   different session) may have merged new data since the last local sync.
2. **When work produces a result, write it to the cloud first.** S3 is the
   durable, shared record. A file that only exists on one laptop isn't the
   real result yet.
3. **Local `data_cache/` copies are a brief, automatic mirror - not a
   second source of truth.** They exist so code and notebooks can read a
   fast local file instead of hitting S3 every time, and so the RAG runtime
   (`ModelPipeline`) has something to actually load. They should always be
   *derived from* the last cloud write, never edited by hand, and never
   trusted over the S3 copy if the two ever disagree.

## How this is enforced in code today (2026-07-27)

- `src_aws_etl/etl/merge_pipeline.py` reads both the base (final-or-historical)
  and the incremental input from S3 (`ETLConfig.s3_uri(...)`), writes the
  merged result to S3 first, and **only then** syncs it to both local
  mirrors automatically (`MergePipeline.sync_local_data_cache()`, called
  right after the S3 upload in `run()`). The sync is best-effort and never
  blocks the merge from succeeding - S3 having the correct data is what
  actually matters.
- `src_edgar_incremental/push_to_etl_incremental.py` (Stage 6) is the
  required last step of `run_pipeline.py` - it pushes the pipeline's output
  straight to the exact S3 key `ETLConfig.incr_path` resolves to, so
  `merge_pipeline.py` finds it automatically with zero manual upload or
  config-editing step in between. `run_pipeline.py --no-push` exists only
  for pure local debugging and should not be the normal way to run it.
- `src_edgar_incremental/assemble_and_validate.py`'s schema-compatibility
  check reads the real production schema from S3 (`ETLConfig.final_path`),
  not a local path - so validation reflects the actual current state of the
  shared dataset, not whatever this machine happened to have cached.
- `src_edgar_incremental/manifests/` is disposable scratch space for the
  *current* run only, cleared at the start of every `run_pipeline.py` call
  (`clear_manifests()`). It is not a place intermediate results are meant to
  accumulate or be treated as a durable record - that's what S3 is for.

## What NOT to do

- Don't add a code path that writes a "final" or "incremental" table only to
  a local file and calls it done. If it doesn't end up in S3, downstream
  code has no way to find it.
- Don't read a local `data_cache/` copy as the ground truth for a
  correctness check (schema comparison, "does this company/year already
  exist" checks, etc.) - read S3.
- Don't let a scratch/manifests-style folder grow across runs. If a stage
  needs to persist something for debugging, keep 2-4 files at most and
  clear old ones before writing new ones (see `clear_manifests()` for the
  pattern).
