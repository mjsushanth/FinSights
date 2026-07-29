# Git History Cleanup Plan — purge bulk data blobs

**Written:** 2026-07-29. **Status:** PLAN ONLY. Nothing rewritten yet.
**Context:** `.git` is **2.6 GB** for a repo whose actual code and docs are ~220 MB. The bloat is
historical data blobs — SEC index TSVs and regenerated parquet tables — that are no longer
tracked or no longer belong in git. Sole owner, no collaborators, no coordination needed.

---

## 1. Findings

### Where the 2.6 GB actually is
Total blob content across all history: **2,132.6 MB**.

| Category | Size | Blobs | Notes |
|---|---|---|---|
| `INDICES/*.tsv` | **1,439.5 MB** | 40 | **67% of everything.** SEC quarterly index files |
| `meta_embeds/*.parquet` | 191.8 MB | 4 | Stage 2 table, untracked earlier today |
| everything else (code/docs) | 222.6 MB | 1,157 | **the part worth keeping** |
| other data files (csv/json/ndjson) | 123.3 MB | 198 | goldp3 analysis dumps, merged CSVs |
| `stage1_facts/*.parquet` | 117.0 MB | 4 | Stage 1 table, still tracked |
| other parquet | 34.4 MB | 46 | samples, test exports |
| notebooks | 4.0 MB | 56 | keep |

### Repository shape — unusually favourable for a rewrite
```
branches:  2   (main @ c2425e6, revival/aws-infra @ 766ade2)
tags:      0
stashes:   0
commits:   423 total (main 406, revival/aws-infra 421)
PRs:       1, merged, from 2025-10-24 (git-test-branch)
git:       2.54.0     uv: available     free disk: 506 GB
```
No tags, no stashes, two branches, one long-merged PR. This is about as clean a rewrite
target as exists.

### The critical safety finding
**No commit consists solely of purge-candidate files.** Verified by walking all 423 commits and
comparing each commit's total file count against its purge-candidate count — zero matches. So
**no commit becomes empty**, and every commit message survives. All 423 commits stay. (We will
still pass `--prune-empty=never` as belt-and-braces.)

---

## 2. What gets purged — by risk tier

### Tier 1 — ZERO RISK: 1,657 MB
Nothing here is reachable from the working tree or lost by purging.

| Path | Size | Why it is safe |
|---|---|---|
| `datasets/INDICES/*.tsv` + `DataPipeline/datasets/INDICES/*.tsv` | 1,439.5 MB | **Not tracked at HEAD (0 files), absent from disk in both locations, already gitignored** (`.gitignore:176 datasets/`). Pure dead weight. |
| `ModelPipeline/finrag_ml_tg1/data_cache/meta_embeds/*.parquet` | 191.8 MB | Untracked + gitignored earlier today. On disk. **In S3**: `ML_EMBED_ASSETS/EMBED_META_FACT/` (62.0 MB). |
| `DataPipeline/datasets/MERGED_EXTRACTED_FILINGS/10-K_merged.csv` | 18.4 MB | Not tracked at HEAD. Regenerable ETL intermediate. |
| `datasets/EXTRACTED_FILINGS/10-K/10-K_merged.csv` | 7.5 MB | Not tracked at HEAD. Old path, superseded. |

### Tier 2 — LOW RISK: 117 MB (needs untracking first)
| Path | Size | Why it is safe |
|---|---|---|
| `ModelPipeline/finrag_ml_tg1/data_cache/stage1_facts/finrag_fact_sentences.parquet` | 117.0 MB history (37.5 MB current) | **Still tracked at HEAD.** But S3 holds three copies: `DATA_MERGE_ASSETS/FINRAG_FACT_SENTENCES/` (35.8 MB), an `ARCHIVE_DATA/` snapshot (35.8 MB), and a `PREDEV_BACKUPS/` pre-rebuild copy (23.9 MB). Regenerable by `data_preparation.py`. |

Must be `git rm --cached` + gitignored **before** the rewrite, exactly as done for `meta_embeds`,
so HEAD is already clean and the rewrite is purely historical.

### Tier 3 — YOUR CALL: ~75 MB (tracked, no S3 backup)
Not included unless you say so. These are the only judgement calls.

| Path | Size | Consideration |
|---|---|---|
| `data_cache/analysis_exports/goldp3_views/*.json` + `qa_manual_exports/` | ~50 MB, 29 tracked files | goldp3 gold-test analysis dumps. **No S3 copy.** Already excluded from the graphify corpus as non-code. Evidence of past evaluation work — you may want them. |
| `DataPipeline/data_cache/samples/sec_filings_small_full.parquet` | 16.5 MB | Tracked sample dataset. **No S3 copy.** May be used by tests/demos. |
| `DataPipeline/src_aws_etl/data_exports_testing/finrag_sec_incremental_stg_data.parquet` | 8.9 MB | Tracked test export. S3 has a same-named file but only 0.1 MB — **different content**, so not a real backup. |

### Projected outcome
| | `.git` size |
|---|---|
| now | 2.6 GB |
| Tier 1 + 2 | **~0.6-0.7 GB** (-75%) |
| Tier 1 + 2 + 3 | **~0.5-0.6 GB** (-80%) |

---

## 3. Procedure

### Step 0 — BACKUP (non-negotiable)
Two independent backups before anything else. A mirror clone captures every ref and object; a
bundle is a single portable file.

```bash
cd "<parent of FinSights>"
git clone --mirror FinSights FinSights-BACKUP-20260729.git
cd FinSights
git bundle create ../FinSights-BACKUP-20260729.bundle --all
git rev-list --all --count          # record: 423
git rev-parse main revival/aws-infra # record both SHAs
```
Verify the backup is real before proceeding: `git -C ../FinSights-BACKUP-20260729.git rev-list --all --count`
must also print 423. **Do not delete these until the pushed result is verified and you have
worked in the repo for a few days.**

### Step 1 — install the tool
`git-filter-repo` is the Git project's own recommended replacement for `filter-branch` (single
pass, ~10x faster, safer defaults).
```bash
uv tool install git-filter-repo
git filter-repo --version
```

### Step 2 — untrack Tier 2 (and Tier 3 if chosen), commit
```bash
git rm --cached ModelPipeline/finrag_ml_tg1/data_cache/stage1_facts/finrag_fact_sentences.parquet
# append to .gitignore, with a comment pointing at the S3 source of truth
git add .gitignore && git commit -m "Untrack Stage 1 fact sentences parquet; S3 is source of truth"
```

### Step 3 — write the paths file
`/tmp/purge-paths.txt` (glob lines handle the two INDICES locations):
```
glob:datasets/INDICES/*.tsv
glob:DataPipeline/datasets/INDICES/*.tsv
ModelPipeline/finrag_ml_tg1/data_cache/meta_embeds/finrag_fact_sentences_meta_embeds.parquet
ModelPipeline/finrag_ml_tg1/data_cache/stage1_facts/finrag_fact_sentences.parquet
DataPipeline/datasets/MERGED_EXTRACTED_FILINGS/10-K_merged.csv
datasets/EXTRACTED_FILINGS/10-K/10-K_merged.csv
```

### Step 4 — dry run, inspect, then rewrite
```bash
# analysis only, writes a report, changes nothing
git filter-repo --analyze
less .git/filter-repo/analysis/path-all-sizes.txt

# the rewrite
git filter-repo \
  --paths-from-file /tmp/purge-paths.txt \
  --invert-paths \
  --prune-empty never \
  --force
```
- `--invert-paths` = remove these paths rather than keep only them
- `--prune-empty never` = **keep every commit even if it becomes empty**, so no commit message
  is ever lost (verified unnecessary here, but free insurance)
- `--force` = required because this is an existing checkout, not a fresh clone. Only safe
  because Step 0 is done.

filter-repo writes `.git/filter-repo/commit-map` — the old-SHA to new-SHA mapping. Keep it.

### Step 5 — verify BEFORE pushing
```bash
git rev-list --all --count                    # MUST be 423
git log --oneline -5                          # messages intact, content sane
git ls-tree -r HEAD --name-only | wc -l       # tracked file count sane
git log --all --oneline -- 'datasets/INDICES/*.tsv' | wc -l   # MUST be 0
git count-objects -vH                         # size-pack should be far smaller
ls -la ModelPipeline/finrag_ml_tg1/data_cache/stage1_facts/   # local file still present
```
Also confirm the code is untouched: `git log --oneline -- ModelPipeline/finrag_ml_tg1/platform_core/embedding_generation.py`
should still show its full history.

### Step 6 — local GC
```bash
git reflog expire --expire=now --all
git gc --prune=now --aggressive
du -sh .git
```

### Step 7 — re-add remote and force-push
filter-repo **deletes the `origin` remote on purpose** so you cannot accidentally push before
inspecting. Re-add it, and drop the stale `upstream` while we are here.
```bash
git remote add origin https://github.com/mjsushanth/FinSights.git
git remote remove upstream          # dead link to the old org
git push --force origin main
git push --force origin refs/heads/revival/aws-infra
```

### Step 8 — GitHub-side reclamation
Local shrink is immediate; **GitHub's is not.** You cannot trigger GC yourself. Unreachable
objects are collected on GitHub's own schedule (hours to days). The one merged PR from
2025-10-24 keeps a `refs/pull/1/head` ref alive, which can pin some old objects indefinitely —
merged PRs cannot be deleted, so if the remote size does not drop, **opening a GitHub support
request asking them to run GC is the recommended route**.

---

## 4. What changes, and what breaks

| | Effect |
|---|---|
| Commit messages | **preserved, all 423** |
| Commit SHAs | **all change** from the first rewritten commit onward |
| Code and docs | untouched |
| Working-tree files | untouched (purged files stay on disk; they are gitignored) |
| Any link referencing an old commit SHA | **breaks** — old permalinks, pinned references |
| Other clones of this repo | become invalid; re-clone rather than pull |
| `main` and `revival/aws-infra` | both must be force-pushed |

The SHA change is the only real consequence. Since this is a solo repo with no open PRs and no
tags, the practical blast radius is any external permalink you may have shared (e.g. in a course
submission) — worth a moment's thought before proceeding.

---

## 5. Rollback

Complete and cheap, as long as Step 0 was done:
```bash
# option A: restore from the mirror
cd "<parent>" && rm -rf FinSights && git clone FinSights-BACKUP-20260729.git FinSights

# option B: restore from the bundle
git clone FinSights-BACKUP-20260729.bundle FinSights-restored

# option C: push the backup back over the remote
git -C FinSights-BACKUP-20260729.git push --force --mirror https://github.com/mjsushanth/FinSights.git
```
Option C matters: because the backup is a `--mirror`, it can restore the remote to its exact
pre-rewrite state, including all original SHAs.

---

## 6. Recommendation

Proceed with **Tier 1 + Tier 2** — 1,774 MB purged, `.git` from 2.6 GB to roughly 0.6 GB, and
every byte removed is either absent from disk, already gitignored, or holding three copies in S3.

Tier 3 is genuinely optional and I would default to **keeping** the goldp3 analysis dumps
(~50 MB) since they have no S3 backup and represent real evaluation work. The two stray test
parquets (25 MB) are safer to drop but the saving is marginal.

Sources consulted: [git-tower on filter-repo](https://www.git-tower.com/learn/git/faq/git-filter-repo),
[GitHub community discussion on triggering GC](https://github.com/orgs/community/discussions/190183),
[GitHub blog on GC at scale](https://github.blog/engineering/architecture-optimization/scaling-gits-garbage-collection/),
[DeployHQ on removing large files](https://www.deployhq.com/git/removing-large-files-from-git-history).
