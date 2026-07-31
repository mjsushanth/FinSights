# Duplicate-sentence analysis: findings and decision

**Date**: 2026-07-27
**Origin**: a skeptical data-quality pass on `finrag_fact_sentences.parquet`
(see `02_data_quality_deep_dive.ipynb`) surfaced ~24,000 `(company, year,
sentence)` triples appearing more than once. This document is the follow-up
investigation into what those duplicates actually are, and what (if
anything) was done about them.

## The question

A duplicate sentence count on its own doesn't say whether the data has a
real problem. Two very different things produce the same symptom:
- the same real sentence genuinely appearing twice in the source filing
  (e.g. a company reuses identical boilerplate legal language for two
  separate disclosures)
- a genuine extraction/splitting artifact producing a spurious repeat

Only the second is a data quality bug. The fix has to distinguish between
them, not react to the raw count.

## Method

For each duplicate group, reconstructed the sentence order within its
`(docID, section_name)` using the numeric suffix of `sentenceID`, then read
the actual neighboring sentences around each occurrence - not just the
duplicated text in isolation - to judge whether the two occurrences sit in
genuinely different real context (implying real, separate content) or are
essentially the same extraction event happening twice.

## Three populations, not one

Classified every duplicate group in the full table (614,910 rows at the
time of this analysis) into three categories:

| Category | Definition | Groups | Excess rows |
|---|---|---|---|
| **A - short/extreme-repeat fragments** | <=4 words, appears >=10x within one company-year | 29 | 1,356 |
| **B - immediately-adjacent exact repeats** | the exact same sentence at two (or more) consecutive `sentenceID` positions, nothing between them | 63 (precise pairwise count: 123 rows) | ~76 (rough group-level estimate; see note) |
| **C - distant, separately-occurring repeats** | the same sentence text appearing in two unrelated, non-adjacent locations | 6,537 | 8,464 |

Note on the Category B count: the table above's "63 groups / ~76 rows" figure
came from an initial group-level heuristic (flag a whole group if *any* pair
within it was adjacent). The actual cleanup script walks through each
section in order and removes only a sentence that is a literal repeat of
the one immediately preceding it - a stricter, precise definition - which
found **123 rows** to remove, not 76. The group-level estimate undercounted
because a few groups had more than one genuinely-adjacent pair inside a
larger set of otherwise-distant occurrences. The 123 figure, from the
actual implementation, is the trustworthy one.

**Category C is 85% of all "duplicate" rows** - by far the majority - and
is real content, not noise.

### Category A - example (not touched)

`"GENWORTH FINANCIAL, INC."` appears 118 times within Genworth's FY2023
filing alone. Neighbor inspection: every single occurrence is immediately
followed by `"NOTES TO CONSOLIDATED FINANCIAL STATEMENTS Years Ended..."`,
with completely different real financial-statement content before and
after each time. This is a page/table header from a 100+ page footnote
section, extracted once per page - not a sentence.

**Decision: left untouched.** Deleting it would require a heuristic
("short + appears very often") that risks catching a genuine short
sentence that happens to also mention the company name in a real context.
Flagging it (a boolean column) was considered and explicitly rejected per
the project owner's instruction to avoid growing the schema for this. No
schema or data change was made for this category.

### Category B - example (fixed)

Tesla FY2024, Item 1A: `"We are highly dependent on the services of Elon
Musk, Technoking of Tesla and our Chief Executive Officer."` appeared at
two *consecutive* sentence positions (163 and 164), with nothing in
between - the same real risk-factor sentence, back to back, is not how a
10-K is actually written. Confirmed as a formatting/extraction artifact
(most likely a bolded pull-quote immediately followed by identical body
text, or a double-processing edge case), not a repeated disclosure.

**Decision: removed.** No legitimate reason exists for a sentence to
immediately repeat itself with zero content between the two occurrences,
so this is safe to treat as noise.

### Category C - example (left alone, deliberately)

Johnson & Johnson FY2023, Item 8: `"Lawsuits primarily have been filed in
state courts in Pennsylvania, California, and Missouri."` appears once
inside a mesh-litigation discussion, and again ~330 sentences later inside
a completely separate Risperdal-litigation discussion. Same standard legal
disclosure sentence, genuinely reused across two distinct, real matters.

Visa FY2023, Item 8: `"As of September 30, 2023, the Company was in
compliance with all related covenants."` appears once under Senior Notes
and again under the Credit Facility - the same compliance boilerplate,
genuinely applied to two different real debt instruments.

**Decision: left completely untouched.** These are not duplicates in any
meaningful sense - removing either instance would delete real,
distinctly-attributable information and make it impossible to retrieve the
sentence in the context of both disclosures it actually belongs to.

## What was actually done

1. **`DataPipeline/src_aws_etl/etl/cleanup_adjacent_duplicates.py`** (new,
   one-off but re-runnable) - read the production table from S3, removed
   the 123 Category-B rows, wrote the cleaned table back to S3, and synced
   both local `data_cache/` mirrors. Net: 614,910 -> 614,787 rows.
2. **`DataPipeline/src_edgar_incremental/clean_and_split.py`** - added
   `collapse_adjacent_duplicates()` to Stage 3, so future edgartools
   fetches don't reintroduce this pattern. Deliberately narrow: it only
   drops a sentence identical to the one immediately before it within the
   same section - it cannot touch a Category C-style distant repeat, by
   construction.
3. **No schema change.** `likely_kpi`/`has_numbers`/`has_comparison` stay
   as they are; no new boilerplate-flag column was added, per explicit
   instruction to avoid complicating the schema for this.
4. **Categories A and C were not modified** - flagged here as documented,
   known, and deliberately-preserved characteristics of the data, not
   defects requiring a fix.

## If this needs revisiting later

- Category A (1,356 rows, 0.22% of the table) is a real, if small,
  quality consideration for whatever eventually builds embeddings from
  this table (Phase 4) - worth excluding short repeated-header sentences
  from the embedding/index step specifically, without touching the raw
  fact table's completeness. Not acted on here; noted for that later
  stage instead.
- Category C should not be "fixed" - any future work that's tempted to
  deduplicate sentence text globally should read this document first.
