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

    [ ] STEP 0   Split the retrieve timer; measure variant-gen vs S3-query time (>=10 runs)
    [ ] GATE     Record S = s3_query_ms. S>2500 proceed to change 3. 1500-2500 proceed,
                 lower expectations. S<1500 ABANDON change 3 and log why.
    [ ] CHANGE 1 Component reuse in orchestrator (task #19). Independent of the gate.
    [ ] CHANGE 2 api_service.py: async def -> def on query_endpoint
    [ ] CHANGE 4a Progress events through supply_lines on_progress callback
    [ ] CHANGE 3 Concurrent retrieval  [ONLY IF GATE PASSED]
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
