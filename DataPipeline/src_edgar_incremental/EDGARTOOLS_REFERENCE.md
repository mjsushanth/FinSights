# edgartools reference — ground-truth notes, not guessed patterns

Everything below was verified this session against the actually-installed
package (`edgartools==5.43.0`, in the `finsight-venv` conda env) by reading
its source directly and running real network experiments against SEC EDGAR
(scripts in the session scratchpad, not checked in). Library: 2.5k GitHub
stars, 4,058 commits, actively maintained (github.com/dgunning/edgartools).
Do not trust docstring examples blindly — one was stale/aspirational (see
"Gotcha 1" below); always spot-check against the real installed version.

## Setup

```python
from edgar import Company, set_identity

set_identity("Your Name your.email@example.com")  # REQUIRED by SEC, no key/signup
```
SEC requires an identifying email on every request. No API key, no signup,
no separate rate-limit tier — just this string. Setting it resets any open
httpx clients internally so it takes effect immediately.

## Core objects

```python
c = Company(320193)          # by CIK (int) or ticker (str), e.g. Company("AAPL")
c.name, c.cik, c.sic, c.tickers   # verified: 'Apple Inc.', 320193, '3571', ['AAPL']

filings = c.get_filings(form="10-K").filter(filing_date="2020-01-01:2021-12-31")
f = filings.latest()         # or filings[0], or iterate

f.accession_no    # '0000320193-21-000105'
f.form             # '10-K'  (or '10-K/A' for amendments - see Gotcha 2)
f.filing_date      # date filed with SEC
f.report_date      # the fiscal period end date (this is what should map to report_year)
f.filing_url       # stable public https://www.sec.gov/Archives/... URL to the
                    # actual filing document - use this for source_file_path,
                    # never a local absolute path (that was the #1 anti-pattern
                    # in the old src_legacy_bs4_scraper/DataLoading_S3.py)

tenk = f.obj()      # parses into a TenK object (edgar.company_reports.ten_k.TenK)
```

## Section extraction — the actual API, verified live

```python
tenk.items            # ['Item 1', 'Item 1A', ..., 'Item 16'] - canonical order,
                       # verified: Apple FY2021 10-K returns all 22 standard items

tenk.sections          # dict[str, Section] - REAL keys observed:
                       # 'part_i_item_1', 'part_i_item_1a', 'part_i_item_1b',
                       # 'part_i_item_2', ..., 'part_ii_item_7', ...,
                       # 'part_iv_item_16'  (part_<roman>_item_<n>[letter])

tenk.sections['part_i_item_1a'].text()   # clean prose, item header included
                       # verified: 66,749 chars / 9,659 words for Apple FY2021
                       # Item 1A - no HTML tags, no manual BeautifulSoup needed

tenk['Item 1A']        # bracket access also works (same underlying data)
tenk.risk_factors       # convenience property for Item 1A specifically
tenk.business           # Item 1
tenk.management_discussion  # Item 7
```

Section boundary detection is genuinely robust — the source
(`edgar/company_reports/ten_k.py`) handles bold-paragraph fallback, table-cell
detection, a "Cross Reference Index" format some companies (e.g. GE) use
instead of standard Item headings, and fixes a real reported bug (GH #821:
Goldman Sachs 10-K had Item 1 mis-mapped to the wrong Part). This is a much
stronger foundation than hand-rolled regex/BS4 section splitting.

### Gotcha 1 — docstring examples don't always match runtime keys
The `TenK.sections` docstring shows friendly names as an example
(`'business'`, `'risk_factors'`, `'mda'`), but the **actual dict keys
returned for a real filing use the `part_i_item_1a` style**, not the friendly
names. Verified by running it live - `tenk.sections.get('risk_factors')`
returns `None`; `tenk.sections.get('part_i_item_1a')` returns the section.
Always use the `.items` list or bracket notation (`tenk['Item 1A']`) if you
want a stable, version-tolerant lookup instead of hardcoding raw dict keys.

### Gotcha 2 — 10-K/A amendments can have partial item coverage
Verified live: Tesla's `2021-12-31` 10-K/A (`tsla-10ka`, accession
`0001564590-22-016871`) returned only **6 items**, not the full 22 - an
amendment typically only refiles the specific items being corrected. Two
options: filter amendments out entirely (`get_filings(form="10-K",
amendments=False)`, confirmed supported) if you only want full annual
reports, or handle variable/partial item counts gracefully (the TenK class
already does - it just returns fewer items, does not error).

### Gotcha 3 — page-footer boilerplate leaks into section text
Verified live on Apple Item 1A: a sentence-split pass produced
`"Apple Inc. | 2021 Form 10-K | 7 Global markets for the Company's..."` -
a page footer ("Company | Year Form 10-K | page#") got concatenated into the
following sentence because the source HTML doesn't add a paragraph break
there. Needs a cleaning regex before/after sentence splitting (see PLAN.md).

### Gotcha 4 — "Item X." headers cause false sentence splits
A naive sentence splitter treats `"Item 1A."` as its own one-token sentence
(the period after a short all-caps/numeral token looks like a sentence end).
**The old codebase already solved this** -
`src_legacy_bs4_scraper/extract_and_convert.py:85` has a
`normalize_item_periods()` regex (`r'(?i)\bItem\s+(\d+[A-Za-z]?)\.'` ->
`r'Item \1'`) that strips the trailing period from item headers before
splitting. Reuse this exact technique rather than reinventing it.

### Gotcha 5 — some older filings (~2010-2018) use a THIRD key style, and
even bracket access can mis-map content
Confirmed live on a real full-history pull (Northrop Grumman FY2010,
Caterpillar FY2016/FY2017): `tenk.sections` for these older filings returns
neither the modern `part_i_item_1a` style nor clean friendly names, but a
sparse set like `{'risk_factors', 'business', 'properties',
'legal_proceedings', 'financial_statements', ...}` covering only a handful
of items (6 out of 22 for the NOC filing; 2 out of 22 for both Caterpillar
filings) - the rest are simply absent from the dict, not present under a
different key. Worse, bracket access (`tenk["Item 1A"]`) returns a plain
`str` for these filings (not a `Section` object with `.text()`), and the
returned text did not clearly correspond to the requested item (e.g.
`tenk["Item 1A"]` returned prose that reads like M&A/organization content,
not risk factors) - this looks like a genuine edge case in edgartools'
older-filing parsing (possibly related to the "Cross Reference Index"
format mentioned in the source), not something worth building bespoke
per-era key-mapping logic to chase for a handful of filings. Impact
observed: 3 of 80 filings (3.75%) in a 2006-2025 full-history pull came
back with ~0 usable sections and were dropped entirely (not present with
empty rows - just absent) - logged clearly by Stage 2's per-filing
coverage line, not a silent failure. Documented here rather than "fixed"
since the cost of handling every historical filing-format quirk isn't
proportionate to 3 missing company-years out of a much larger, otherwise
clean pull.

## Filtering filings (verified supported)

```python
c.get_filings(form="10-K")                                  # by form
c.get_filings(form=["10-K", "10-K/A"])                        # multiple forms
c.get_filings(form="10-K", amendments=False)                  # exclude amendments
c.get_filings(form="10-K").filter(filing_date="2023-01-01:")  # open-ended range
c.get_filings(form="10-K").filter(filing_date=("2023-01-01", "2023-12-31"))
c.get_filings(form="10-K", year=2023, quarter=4)               # year/quarter
filings.latest()            # most recent match
filings.head(10) / .next() / .previous()   # pagination for large result sets
```

## Observed performance (real network calls, this session)

Single company + single filing fetch + parse: ~0.2-1.7s (network-bound,
dominated by the initial company/filing-index lookup; parsing itself is
near-instant, ~0.01-0.16s per section since HTML is fetched once and cached
on the Filing object). Three companies' 2022 10-Ks fetched + parsed
sequentially: 6.17s total. For full context: a full pass over the 21 curated
companies at ~1-3s per filing-year is on the order of minutes, not hours -
budget accordingly in PLAN.md's stage timing.

## What edgartools does NOT give you directly

- Sentence-level splitting - it gives clean section **text**, not
  pre-split sentences. Needs a lightweight sentence splitter afterward
  (see Gotcha 4; a simple regex splitter is enough, no need for the full
  `nltk` dependency we deliberately dropped from the lean environment).
- `has_numbers` / `has_comparison` / `likely_kpi` style feature flags -
  not provided by the library, must be computed downstream (see PLAN.md;
  note the OLD codebase never actually computed these either — they are
  permanent `None` placeholders in `src_aws_etl/etl/merge_pipeline.py`,
  confirmed by direct inspection of the real production parquet showing
  `False`/`True` values instead - those came from a separate, undocumented
  bulk process, not from this ETL path. Real opportunity to finally
  implement this properly rather than perpetuate nulls.)
