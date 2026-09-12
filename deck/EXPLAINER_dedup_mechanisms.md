# How the two dedup mechanisms actually work

Read from the implementation, not the docs. All line numbers current as of this writing.

---

## 1. Adjacent exact-repeat prevention at ingestion

Two separate pieces of code do this, and they are **not** the same logic calling
through to one shared function — they were written independently, at different
points in the pipeline, against different data shapes.

### `collapse_adjacent_duplicates()` — the ingestion-time guard

`DataPipeline/src_edgar_incremental/clean_and_split.py:72-83`

```python
def collapse_adjacent_duplicates(sentences: list[str]) -> list[str]:
    out = []
    for s in sentences:
        if out and out[-1] == s:
            continue
        out.append(s)
    return out
```

Called from `clean_and_split_section()` (line 91), which is invoked once per
`(docID, section)` inside the main `run()` loop (lines 96-98).

**What "adjacent" means, precisely:** literal list-adjacency in an in-memory
Python list. This function runs on the raw output of `split_sentences()` for
*one section's text*, **before `sentenceID`s are even assigned** — those get
generated later, in `run()` at line 108. So "adjacent" isn't a `sentenceID`
comparison at all; it's "the immediately preceding element of this section's
own sentence list." It only ends up meaning "consecutive sentence position
within the same document+section" as a side effect of being called once per
section — the function itself has no concept of document or section IDs.

**The comparison:** exact string equality, `out[-1] == s` (line 80). No
`.strip()`, no `.lower()`, no hashing. Two sentences differing only in
whitespace or case would not be caught.

**Why it structurally cannot touch a distant repeat:** it only ever compares
element `i` to element `i-1`. There is no lookup table, no memory of anything
seen earlier than the immediately preceding line. Two occurrences of the same
sentence with *anything at all* between them — even one intervening sentence
— cannot trigger the drop. This isn't an incidental limitation; it's the
entire mechanism. The module's own docstring names the deliberately-untouched
case directly: the same compliance sentence reused across two different debt
instruments or two different lawsuits (Category C on slide 8) survives by
design, because nothing here looks past the immediate neighbor.

### `cleanup_adjacent_duplicates.py` — the one-off cleanup that removed 123 rows

`DataPipeline/src_aws_etl/etl/cleanup_adjacent_duplicates.py`, `find_adjacent_duplicate_ids()` (lines 41-62)

```python
ordered = (
    df.select(["docID", "section_name", "sentenceID", "sentence"])
    .with_columns(pl.col("sentenceID").str.extract(r"_(\d+)$", 1).cast(pl.Int64).alias("s_idx"))
    .sort(["docID", "section_name", "s_idx"])
)
...
for row in ordered.iter_rows(named=True):
    key = (row["docID"], row["section_name"])
    if key == prev_key and row["sentence"] == prev_sentence:
        to_drop.append(row["sentenceID"])
    else:
        prev_sentence = row["sentence"]
    prev_key = key
```

**Different implementation, same rule.** This one operates on an
already-materialized Polars DataFrame of the production table — not an
in-memory list mid-parse. It explicitly reconstructs sentence order by
extracting the numeric suffix off `sentenceID` and sorting on
`(docID, section_name, s_idx)`, then walks the sorted rows comparing each to
the previous one within the same `(docID, section_name)` key. Same exact-string
comparison, same "adjacent = nothing intervening" semantics — but it is not a
call into `collapse_adjacent_duplicates()`; it's a second, independently
written pass over already-embedded production data, needed because the
ingestion-time guard didn't exist yet when the first 614,910 rows were built.
`DataPipeline/analytics/duplicate_sentence_analysis.md` (lines 39-50, 86, 108)
documents both as separate deliverables: an initial group-level estimate put
the count at ~76 rows; the actual pairwise-adjacent script found 123
(614,910 → 614,787), which is now the schema-verified number on slide 8.

**Bottom line:** the ingestion-time function and the one-off cleanup script
enforce the identical rule (drop exact matches to the immediately-preceding
sentence, nothing more), independently coded, so the corpus can't regress to
the pre-cleanup state through new incremental ingestion even though the two
code paths never actually share a function call.

---

## 2. Union dedup by lowest distance

This is actually two stacked passes at two different granularities, both using
the same tie-break rule.

### Stage A — hit-level dedup, `s3_retriever.py:465-527`, `_deduplicate_hits()`

```python
groups = defaultdict(list)
for hit in all_hits:
    key = (hit.sentence_id, hit.embedding_id)
    groups[key].append(hit)

for (sentence_id, embedding_id), hits in groups.items():
    best = min(hits, key=lambda h: h.distance)
    best.sources = {h.source for h in hits}
    best.variant_ids = {h.variant_id for h in hits}
    deduped.append(best)
```

`all_hits` is the pool assembled in `retrieve()` (lines 240-257): the base
query's filtered hits, the base query's global (open) hits, and every query
variant's filtered hits, all concatenated before this function runs. Group key
is `(sentence_id, embedding_id)` — not `sentence_id` alone, because "one
sentence can have multiple embeddings from different runs" (the code's own
comment at line 469). Winner: `min(..., key=distance)`.

### Stage B — sentence-record dedup, after window expansion, `sentence_expander.py:490-595`, `_deduplicate_sentences()`

After each surviving hit gets expanded to its ±3 neighboring sentences,
records are re-grouped by `(sentence_id, cik_int, report_year, section_name)`
(line 528), sorted by `parent_hit_distance` (line 551), and the first
(lowest-distance) record wins (`best = group_recs[0]`, line 554).

### What happens to the losers

Both stages do the same thing, and it's more than "keep the best, discard the
rest":

- **`sources`** and **`variant_ids`** — set-union across *every* hit in the
  group, not just the winner's own values (`s3_retriever.py:505-507`,
  `sentence_expander.py:556-570`). A losing duplicate's provenance isn't
  thrown away; it's folded into the surviving record's set fields.
- **`is_core_hit`** (Stage B only) — an OR across the group:
  `any_core_hit = any(rec.is_core_hit ...)`. If *any* losing duplicate was a
  core hit, the surviving record inherits that flag, even if the winning
  (lowest-distance) copy itself wasn't. This is spelled out directly in the
  module's own docstring (lines 26-32): "aggregation: sources, variant_ids,
  is_core_hit (OR operation)."
- Everything else about a losing duplicate — its own distance value, its own
  individual source label in isolation — is discarded once folded in.

**What the aggregation buys:** without it, a sentence that happened to surface
through five different variant queries but scored best on the sixth would look,
downstream, exactly like a sentence that only ever matched once. The `sources`/
`variant_ids` union preserves "this evidence was independently corroborated by
N different query angles" as a signal that survives the dedup, even though
only one physical copy of the sentence makes it into the assembled context.

**Why lowest-distance, not first-seen or highest-frequency:** the in-code
justification is direct but modest, not an argued design decision. Both files
state it as a one-liner: `sentence_expander.py:494-495` — "keep the version
from the hit with the best (lowest) distance. This ensures we use the
highest-quality evidence for each sentence." `s3_retriever.py`'s own docstring
(lines 7-9) states the identical rule as a design-decision bullet. There is no
dedicated document weighing lowest-distance against first-seen-order or
cross-variant frequency as alternatives.

**The honest caveat, from the retrieval-improvement audit, not from either of
these two files:** `RETRIEVAL_IMPROVEMENT_STUDY.md` (section 2.1, lines
178-182) points out what this dedup rule doesn't do: the group key is identity
-based (`sentence_id` + location fields) — "nothing in the pipeline ever
compares sentence text." The same sentence recurring verbatim across filing
years carries a *different* `sentence_id` each time, survives this dedup
entirely, and — because near-duplicate boilerplate scores near-identically in
cosine space — both copies tend to land adjacent in the ranking, consuming two
of the context budget's slots for one fact. Section 3.3 (lines 491-499)
proposes adding a normalized-text key to close that gap; it isn't built yet.
So the honest framing is: lowest-distance solves "which physical copy of this
exact sentence-ID is the best evidence," and does nothing for "these are two
different sentence-IDs that happen to say the same thing" — that's the
boilerplate-crowding problem slide 8 is about, and it's a distinct mechanism
from this one.
